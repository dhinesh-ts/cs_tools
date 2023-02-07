import sysconfig
import platform
import logging
import pathlib
import sys
import os

from awesomeversion import AwesomeVersion
from rich.panel import Panel
import typer

from cs_tools.updater._bootstrapper import get_latest_cs_tools_release
from cs_tools._version import __version__
from cs_tools.settings import _meta_config
from cs_tools.updater import CSToolsVirtualEnvironment
from cs_tools.updater import FishPath, WindowsPath, UnixPath
from cs_tools.cli.ux import CSToolsOption as Opt
from cs_tools.cli.ux import CSToolsCommand
from cs_tools.cli.ux import CSToolsGroup
from cs_tools.cli.ux import rich_console
from cs_tools.const import APP_DIR

log = logging.getLogger(__name__)
meta = _meta_config()
app = typer.Typer(
    cls=CSToolsGroup,
    name="self",
    help=f"""
    Perform actions on CS Tools.

    {meta.newer_version_string()}
    """,
    invoke_without_command=True,
    no_args_is_help=True,
)


@app.command(cls=CSToolsCommand, name="upgrade", hidden=True)
@app.command(cls=CSToolsCommand)
def update(
    beta: bool = Opt(False, "--beta", help="pin your install to a pre-release build"),
    offline: pathlib.Path = Opt(
        None,
        help="install cs_tools from a distributable directory instead of from remote",
        metavar="cs_tools.zip",
    ),
    venv_name: str = Opt(None, "--venv-name", hidden=True),
):
    """
    Upgrade CS Tools.
    """
    if venv_name is not None:
        os.environ["CS_TOOLS_CONFIG_DIRNAME"] = venv_name

    venv = CSToolsVirtualEnvironment(find_links=offline)
    release = get_latest_cs_tools_release()
    requires = "cs_tools[cli]"

    if offline:
        log.info(f"Using the offline binary found at [b magenta]{offline}")
    else:
        log.info(f"Getting the latest CS Tools {'beta ' if beta else ''}release.")
        release = get_latest_cs_tools_release(allow_beta=beta)
        log.info(f"Found version: [b cyan]{release['tag_name']}")
        requires += f" @ https://github.com/thoughtspot/cs_tools/archive/{release['tag_name']}.zip"

        if AwesomeVersion(release["tag_name"]) <= AwesomeVersion(__version__):
            log.info("CS Tools is [b green]already up to date[/]!")
            raise typer.Exit(0)

    log.info("Upgrading CS Tools and its dependencies.")

    try:
        rc = venv.pip("install", requires)
        log.debug(rc)
    except RuntimeError:  # OSError when pip on Windows can't upgrade itself~
        pass


@app.command(cls=CSToolsCommand)
def info():
    """
    Get information on your install.
    """
    if platform.system() == "Windows":
        source = pathlib.Path(sys.executable).parent.joinpath("Activate.ps1")
    else:
        source = f"source {pathlib.Path(sys.executable).parent.joinpath('activate')}"

    rich_console.print(
        Panel.fit(
            f"\n           CS Tools: [b yellow]{__version__}[/]"
            f"\n     Python Version: [b yellow]Python {sys.version}[/]"
            f"\n        System Info: [b yellow]{platform.system()}[/] (detail: [b yellow]{platform.platform()}[/])"
            f"\n  Configs Directory: [b yellow]{APP_DIR}[/]"
            f"\nActivate VirtualEnv: [b yellow]{source}[/]"
            f"\n      Platform Tags: [b yellow]{sysconfig.get_platform()}[/]"
            f"\n",
            padding=(0, 4, 0, 4)
        )
    )


@app.command(cls=CSToolsCommand, hidden=True)
def pip():
    """
    Remove CS Tools.
    """
    # if venv_name is not None:
    #     os.environ["CS_TOOLS_CONFIG_DIRNAME"] = venv_name

    # venv = CSToolsVirtualEnvironment()
    # venv.pip()
    raise NotImplementedError("Not yet.")


@app.command(cls=CSToolsCommand, hidden=True)
def uninstall(
    delete_configs: bool = Opt(False, "--delete-configs", help="delete all the configurations in CS Tools directory")
):
    """
    Remove CS Tools.
    """
    raise NotImplementedError("Not yet.")
