import asyncio
import sqlite3
from collections.abc import Generator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from enum import StrEnum, auto
from pathlib import Path
from types import MappingProxyType

import pytest
import sqlalchemy as sql
from mcp import Client
from mcp.types import CallToolResult, TextContent, Tool
from sqlalchemy import event  # noqa: ICN003 - event is a submodule that sqlalchemy's top level does not export, so ty refuses it through the alias
from sqlalchemy.orm import Session, SessionTransaction

from mightymodels_plugin.core.data_directory import SESSION_DATA_VARIABLE, DataDirectory
from mightymodels_plugin.core.database import DATABASE_NAME, Database, open_database
from mightymodels_plugin.core.declarative import Base
from mightymodels_plugin.core.edge import exclude_state_from_git
from mightymodels_plugin.core.repository_key import RepositoryKey, local_key
from mightymodels_plugin.core.workspace import (
    PROJECT_DIR_VARIABLE,
    Checkout,
    Git,
    Workspace,
    git_at,
    workspace_at,
)
from mightymodels_plugin.server import build_server
from mightymodels_plugin.tools.row_types import ROW_TYPES

type ToolCall = tuple[str, dict[str, object]]
type RowValues = Mapping[str, object]

SELECT = 'SELECT'
EXPLAINED = 'EXPLAIN QUERY PLAN '
FILLERS = MappingProxyType({str: 'x', int: 1, bool: True, object: ()})
FILES_OF_AN_OPEN_DATABASE = frozenset(
    {DATABASE_NAME, f'{DATABASE_NAME}-wal', f'{DATABASE_NAME}-shm'}
)


class ActivityKind(StrEnum):
    TRANSACTION_OPENED = auto()
    ENGINE_DISPOSED = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseEvent:
    kind: ActivityKind
    engine: sql.Engine


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseActivity:
    events: list[DatabaseEvent] = field(default_factory=list)

    def record_transaction(self, session: Session, transaction: SessionTransaction) -> None:
        if transaction.parent is not None:
            return
        engine = session.get_bind().engine
        self.events.append(DatabaseEvent(kind=ActivityKind.TRANSACTION_OPENED, engine=engine))

    def record_disposal(self, engine: sql.Engine) -> None:
        self.events.append(DatabaseEvent(kind=ActivityKind.ENGINE_DISPOSED, engine=engine))

    def kinds(self) -> list[ActivityKind]:
        return [recorded.kind for recorded in self.events]

    def engines(self) -> set[sql.Engine]:
        return {recorded.engine for recorded in self.events}


@dataclass(slots=True, kw_only=True, frozen=True)
class SelectSent:
    sql: str
    parameters: tuple[object, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class SelectsSent:
    database_file: Path
    sent: list[SelectSent] = field(default_factory=list)

    def record(self, *, statement: str, parameters: Sequence[object], **_others: object) -> None:
        if statement.startswith(SELECT):
            self.sent.append(SelectSent(sql=statement, parameters=tuple(parameters)))

    def rows_fetched(self) -> list[int]:
        with closing(sqlite3.connect(self.database_file)) as connection:
            return [
                len(connection.execute(select.sql, select.parameters).fetchall())
                for select in self.sent
            ]

    def plan_steps(self) -> list[str]:
        with closing(sqlite3.connect(self.database_file)) as connection:
            return [
                str(step)
                for select in self.sent
                for *_, step in connection.execute(EXPLAINED + select.sql, select.parameters)
            ]


@contextmanager
def selects_sent_to(database: Database) -> Generator[SelectsSent]:
    selects = SelectsSent(database_file=Path(str(database.engine.url.database)))
    event.listen(database.engine, 'before_cursor_execute', selects.record, named=True)
    try:
        yield selects
    finally:
        event.remove(database.engine, 'before_cursor_execute', selects.record)


def table_of(row_type: type[Base]) -> sql.Table:
    return Base.metadata.tables[row_type.__tablename__]


def filled_row(row_type: type[Base], **given: object) -> RowValues:
    table = table_of(row_type)
    needed = (
        column
        for column in table.columns
        if column.server_default is None
        and not column.nullable
        and column is not table.autoincrement_column
    )
    return {column.name: FILLERS[column.type.python_type] for column in needed} | given


def tree(top: Path) -> dict[str, bytes]:
    files = (path for path in sorted(top.rglob('*')) if path.is_file())
    return {str(path.relative_to(top)): path.read_bytes() for path in files}


def stored_bytes(database: Database) -> bytes:
    data_directory = Path(str(database.engine.url.database)).parent
    return b''.join(tree(data_directory).values())


def text_of(result: CallToolResult) -> str:
    return ''.join(block.text for block in result.content if isinstance(block, TextContent))


@dataclass(slots=True, kw_only=True, frozen=True)
class StateServer:
    root: Path
    data_directory: DataDirectory

    async def served_name(self) -> str | None:
        async with Client(build_server(self.root, self.data_directory)) as client:
            return client.server_info.name if client.server_info else None

    async def served_tools(self) -> dict[str, Tool]:
        async with Client(build_server(self.root, self.data_directory)) as client:
            listed = await client.list_tools()
        return {tool.name: tool for tool in listed.tools}

    async def call_results(self, calls: Sequence[ToolCall]) -> list[CallToolResult]:
        async with Client(build_server(self.root, self.data_directory)) as client:
            return [await client.call_tool(name, arguments) for name, arguments in calls]

    def name(self) -> str | None:
        return asyncio.run(self.served_name())

    def tools(self) -> dict[str, Tool]:
        return asyncio.run(self.served_tools())

    def call(self, *calls: ToolCall) -> list[CallToolResult]:
        return asyncio.run(self.call_results(calls))

    def connect(self) -> None:
        self.call()

    def files_on_disk(self) -> dict[str, bytes]:
        if not isinstance(self.data_directory, Path):
            return tree(self.root)
        kept = tree(self.data_directory)
        return tree(self.root) | {f'{self.data_directory}/{name}': kept[name] for name in kept}


def repository_key_of(workspace: Workspace) -> RepositoryKey:
    checkout = git_at(workspace.root).checkout()
    if not isinstance(checkout, Checkout):
        return local_key(workspace.root)
    return checkout.repository_key()


@contextmanager
def workspace_database(workspace: Workspace, data_directory: Path) -> Generator[Database]:
    database_file = data_directory.joinpath(DATABASE_NAME)
    with open_database(database_file, repository_key_of(workspace), ROW_TYPES) as database:
        yield database


@pytest.fixture
def data_directory(tmp_path: Path) -> Path:
    return tmp_path.joinpath('plugin-data')


@pytest.fixture
def repository_git(repository: Path) -> Git:
    return git_at(repository)


@pytest.fixture
def repository_workspace(repository: Path, repository_git: Git) -> Workspace:
    exclude_state_from_git(repository_git)
    return workspace_at(repository)


@pytest.fixture
def repository_database(
    repository_workspace: Workspace, data_directory: Path
) -> Generator[Database]:
    with workspace_database(repository_workspace, data_directory) as database:
        yield database


@pytest.fixture
def session_in_the_repository(
    repository: Path, data_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(repository))
    monkeypatch.setenv(SESSION_DATA_VARIABLE, str(data_directory))


@pytest.fixture
def state_server(repository: Path, data_directory: Path) -> StateServer:
    return StateServer(root=repository, data_directory=data_directory)


@pytest.fixture
def connected_server(state_server: StateServer) -> StateServer:
    state_server.connect()
    return state_server


@pytest.fixture
def tree_after_the_connect(connected_server: StateServer) -> dict[str, bytes]:
    return connected_server.files_on_disk()


@pytest.fixture
def database_activity() -> Generator[DatabaseActivity]:
    activity = DatabaseActivity()
    event.listen(Session, 'after_transaction_create', activity.record_transaction)
    event.listen(sql.Engine, 'engine_disposed', activity.record_disposal)
    yield activity
    event.remove(Session, 'after_transaction_create', activity.record_transaction)
    event.remove(sql.Engine, 'engine_disposed', activity.record_disposal)
