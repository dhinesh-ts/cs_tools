from typing import List
import json

from typer import Argument as A_, Option as O_
import typer

from cs_tools.helpers.cli_ux import _csv, console, frontend, RichGroup, RichCommand
from cs_tools.thoughtspot import ThoughtSpot
from cs_tools.settings import TSConfig
from cs_tools._enums import GUID


def _all_user_content(user: GUID, ts: ThoughtSpot):
    """
    Return all content owned by this user.
    """
    types = (
        'QUESTION_ANSWER_BOOK',
        'PINBOARD_ANSWER_BOOK',
        'LOGICAL_TABLE',
        'TAG',
        'DATA_SOURCE'
    )
    content = []

    for metadata_type in types:
        offset = 0

        while True:
            r = ts.api._metadata.list(type=metadata_type, batchsize=500, offset=offset)
            data = r.json()
            offset += len(data)

            for metadata in data['headers']:
                if metadata['author'] == user:
                    metadata['type'] = metadata_type
                    content.append(metadata)

            if data['isLastBatch']:
                break

    return content


app = typer.Typer(
    help="""
    Transfer ownership of all objects from one user to another.
    """,
    cls=RichGroup
)


@app.command(cls=RichCommand)
@frontend
def transfer(
    from_: str=A_(..., metavar='FROM', help='username of the current content owner'),
    to_: str=A_(..., metavar='TO', help='username to transfer content to'),
    tag: List[str]=O_(None, callback=_csv, help='if specified, only move content marked with one or more of these tags'),
    guids: List[str]=O_(None, callback=_csv, help='if specified, only move specific objects'),
    **frontend_kw
):
    """
    Transfer ownership of objects from one user to another.

    Tags and GUIDs constraints are applied in OR fashion.
    """
    cfg = TSConfig.from_cli_args(**frontend_kw, interactive=True)
    ids = set()

    with ThoughtSpot(cfg) as ts:

        if tag is not None or guids is not None:
            user = ts.user.get(from_)
            content = _all_user_content(user=user['id'], ts=ts)

            if tag is not None:
                ids.update([_['id'] for _ in content if set([t['name'] for t in _['tags']]).intersection(set(tag))])

            if guids is not None:
                ids.update([_['id'] for _ in content if _['id'] in guids])

        amt = len(ids) if ids else 'all'

        with console.status(f'[bold green]\nTransferring {amt} objects from "{from_}" to "{to_}"[/]'):
            try:
                r = ts.api.user.transfer_ownership(
                        fromUserName=from_,
                        toUserName=to_,
                        objectsID=ids
                    )
            except Exception:
                json_msg = r.json()['debug']
                msg = json.loads(json_msg)  # uhm, lol?
                console.print(f'[red]Failed. {msg[-1]}[/]')
            else:
                console.print('[green]Success![/]')
