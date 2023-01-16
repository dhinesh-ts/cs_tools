from ipaddress import IPv4Address
from typing import Union, Dict, Any
import datetime as dt
import pathlib
import logging
import json
import re

from pydantic.types import DirectoryPath, FilePath
from awesomeversion import AwesomeVersion
from pydantic import validator, AnyHttpUrl, BaseModel
import httpx
import toml

from cs_tools._version import __version__
from cs_tools.errors import ConfigDoesNotExist
from cs_tools.const import APP_DIR
from cs_tools import utils

log = logging.getLogger(__name__)


class _meta_config(BaseModel):
    """

    [default]
    config = 'my-config-name'

    [latest_release]
    version = v104
    published_at = 10202019210
    """
    default_config_name: str = None
    latest_release_version: str = None
    latest_release_date: dt.date = None
    _meta_fp: pathlib.Path = APP_DIR / ".meta-config.toml"

    @classmethod
    def load(cls):
        fp = cls._meta_fp
        data = {}

        if not fp.exists():
            fp.touch()

        try:
            disk = toml.load(fp)
            data["default_config_name"] = disk["default"]["config"]
            data["latest_release_version"] = disk["latest_release"].get("version", None)
            data["latest_release_date"] = disk["latest_release"].get("published_at", None)
        except Exception:
            log.debug("failed to load the full meta config", exc_info=True)

        # constants
        EPOCH = dt.date(2012, 6, 1)
        NOW = dt.datetime.now()
        ONE_DAY = 86400  # seconds

        # predicates to check
        have_not_checked_today = (NOW - dt.datetime.fromtimestamp(fp.stat().st_mtime)).total_seconds() > ONE_DAY
        has_data = fp.stat().st_size
        local_lt_remote = AwesomeVersion(__version__) <= AwesomeVersion(data.get("latest_release_version", "9.9.9"))
        remote_gt_5days = (NOW.date() - data.get("latest_release_date", EPOCH)).total_seconds() > ONE_DAY * 5

        # fetch latest remote version
        if have_not_checked_today and has_data and local_lt_remote and remote_gt_5days:
            release_url = "https://api.github.com/repos/thoughtspot/cs_tools/releases/latest"

            try:
                r = httpx.get(release_url, timeout=1).json()
                data["latest_release_version"] = r["name"]
                data["latest_release_date"] = dt.datetime.strptime(r["published_at"], "%Y-%m-%dT%H:%M:%SZ").date()
                cls(**data).save()
            except httpx.TimeoutException:
                log.info("fetching latest CS Tools release version timed out")
            except Exception as e:
                log.info(f"could not fetch release url: {e}")

        return cls(**data)

    def save(self) -> None:
        data = {
            "default": {"config": self.default_config_name},
            "latest_release": {"version": self.latest_release_version, "published_at": self.latest_release_date},
        }

        self._meta_fp.write_text(toml.dumps(data))

    def newer_version_string(self) -> str:
        if AwesomeVersion(__version__) >= AwesomeVersion(self.latest_release_version or "0.0.0"):
            return ""
        url = f"https://github.com/thoughtspot/cs_tools/releases/tag/{self.latest_release_version}"
        return f"[green]Newer version available![/] [cyan][link={url}]{self.latest_release_version}[/][/]"


class Settings(BaseModel):
    """
    Base class for settings management and validation.
    """

    class Config:
        json_encoders = {FilePath: lambda v: v.resolve().as_posix(), DirectoryPath: lambda v: v.resolve().as_posix()}


class TSCloudURL(str):
    """
    Validator to match against a ThoughtSpot cloud URL.
    """

    REGEX = re.compile(r"(?:https:\/\/)?(.*\.thoughtspot\.cloud)(?:\/.*)?")

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise TypeError("string required")

        m = cls.REGEX.fullmatch(v)

        if not m:
            raise ValueError("invalid thoughtspot cloud url")

        return cls(f"{m.group(1)}")


class HostConfig(Settings):
    host: Union[AnyHttpUrl, IPv4Address, TSCloudURL]
    port: int = None
    disable_ssl: bool = False
    disable_sso: bool = False

    @property
    def fullpath(self):
        host = self.host
        port = self.port

        if not host.startswith("http"):
            host = f"https://{host}"

        if port:
            port = f":{port}"
        else:
            port = ""

        return f"{host}{port}"

    @validator("host")
    def cast_as_str(v: Any) -> str:
        """
        Converts arguments to a string.
        """
        if hasattr(v, "host"):
            return f"{v.scheme}://{v.host}"

        return str(v)


class AuthConfig(Settings):
    username: str
    password: str = None


class CSToolsConfig(Settings):
    name: str
    thoughtspot: HostConfig
    auth: Dict[str, AuthConfig]
    syncer: Dict[str, FilePath] = None
    verbose: bool = False
    temp_dir: DirectoryPath = APP_DIR

    @validator("syncer")
    def resolve_path(v: Any) -> str:
        if v is None or isinstance(v, dict):
            return v
        return {k: pathlib.Path(f).resolve() for k, f in v.items()}

    @classmethod
    def get_default_config_name(cls) -> str:
        """ """
        return _meta_config.load().default_config_name

    def dict(self) -> Any:
        """
        Wrapper around model.dict to handle path types.
        """
        data = super().json()
        data = json.loads(data)
        return data

    @classmethod
    def from_toml(cls, fp: pathlib.Path, *, verbose: bool = None, temp_dir: pathlib.Path = None) -> "CSToolsConfig":
        """
        Read in a ts-config.toml file.

        Parameters
        ----------
        fp : pathlib.Path
          location of the config toml on disk

        verbose, temp_dir
          overrides the settings found in the config file
        """
        try:
            data = toml.load(fp)
        except FileNotFoundError:
            raise ConfigDoesNotExist(name=fp.stem.replace("cluster-cfg_", ""))

        if data.get("name") is None:
            data["name"] = fp.stem.replace("cluster-cfg_", "")

        # overrides
        if verbose is not None:
            data["verbose"] = verbose

        if temp_dir is not None:
            data["temp_dir"] = temp_dir

        return cls.parse_obj(data)

    @classmethod
    def from_command(cls, config: str = None, **passthru) -> "CSToolsConfig":
        """
        Read in a ts-config.toml file by its name.

        If no file is provided, we attempt to check for the default
        configuration.

        Parameters
        ----------
        config: str
          name of the configuration file
        """
        if config is None:
            meta = _meta_config.load(config)
            config = meta["default"]["config"]

        return cls.from_toml(APP_DIR / f"cluster-cfg_{config}.toml", **passthru)

    @classmethod
    def from_parse_args(cls, name: str, *, validate: bool = True, **passthru) -> "CSToolsConfig":
        """
        Validate initial input from config.create or config.modify.
        """
        _pw = passthru.get("password")
        _syncers = [syncer.split("://") for syncer in passthru.get("syncer", [])]

        data = {
            "name": name,
            "verbose": passthru.get("verbose"),
            "temp_dir": passthru.get("temp_dir"),
            "thoughtspot": {
                "host": passthru["host"],
                "port": passthru.get("port"),
                "disable_ssl": passthru.get("disable_ssl"),
                "disable_sso": passthru.get("disable_sso"),
            },
            "auth": {
                "frontend": {
                    "username": passthru["username"],
                    "password": utils.obscure(_pw).decode() if _pw is not None else _pw,
                }
            },
            "syncer": {proto: definition_fp for (proto, definition_fp) in _syncers},
        }

        return cls.parse_obj(data) if validate else cls.construct(**data)
