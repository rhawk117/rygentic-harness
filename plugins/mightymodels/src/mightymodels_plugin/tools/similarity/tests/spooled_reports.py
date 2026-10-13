import json
from collections.abc import Mapping
from pathlib import Path

import sqlalchemy as sql

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.repository_key import RepositoryKey, spool_file_prefix
from mightymodels_plugin.tools.similarity.spool import REJECTED_DIRECTORY
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow
from mightymodels_plugin.tools.tests.support import ToolCall

type Report = Mapping[str, object]

OTHER_KEY = 'acme/gadgets'
REPORT_TEXT = 'the drain loop sleeps between every retry batch'
SEARCH: ToolCall = ('similarity', {'request': {'action': 'search', 'query': REPORT_TEXT}})
WORDS = 'the drain loop sleeps between every retry batch '


def words_of(length: int) -> str:
    return (WORDS * (length // len(WORDS) + 1))[:length]


def report_for(key: str, **given: object) -> Report:
    return {
        'repository_key': key,
        'scout': 'code-scout',
        'target': 'the drain loop',
        'report': REPORT_TEXT,
    } | given


def named(key: str, unique: str) -> str:
    return f'{spool_file_prefix(RepositoryKey(key))}{unique}.json'


def spooled(spool: Path, name: str, content: Report | bytes) -> Path:
    spool.mkdir(parents=True, exist_ok=True)
    file = spool.joinpath(name)
    file.write_bytes(content if isinstance(content, bytes) else json.dumps(content).encode())
    return file


def rejected_files(spool: Path) -> list[Path]:
    return sorted(spool.joinpath(REJECTED_DIRECTORY).glob('*'))


def scout_reports(database: Database) -> list[ScoutReportRow]:
    with database.transaction() as session:
        rows = list(session.scalars(sql.select(ScoutReportRow)))
        session.expunge_all()
    return rows
