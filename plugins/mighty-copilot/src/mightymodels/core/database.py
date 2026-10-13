"""The state database in the plugin data directory: one engine and one session factory per owner.

Whoever opens it holds it for as long as it runs, the server for its lifespan and `verify run`
for its one command, and the engine is disposed when that owner lets go. The file is
`DATABASE_NAME` in the plugin data directory, outside every repository, and it holds the rows of
all of them. A `Database` is that file as one repository sees it: it carries the repository's key,
and each domain's repository writes and reads rows under that key and no other. Deleting the file
resets the state of every repository.

`open_database` is the only way to a `Database`, and it creates the table of every row type its
owner hands in, by name, whatever else the owner has imported. This module names no row type:
every owner hands in `ROW_TYPES` from `tools/row_types.py`, so none opens a database with a
table missing, and a domain's `tables.py` adds a table only by adding its row type there.
The FTS5 index over the similarity table is created by DDL that its `tables.py` registers on the
same `create_all`, so it too waits for the stamp check.

The file is stamped with `SCHEMA_VERSION`, kept in SQLite's `user_version`. A file that holds
nothing is stamped before its tables are created. A file with any other stamp is refused by name
and left as it was: there is no migration, and tables of another shape would be read wrong. An
unstamped file that already holds tables is such a file, and a database an earlier version kept
inside a repository is one.

Two processes can open one new file at the same moment: the server and `verify run` of one
session, or two sessions. So the open takes SQLite's write lock before it reads the stamp and
holds it to the last `CREATE`, and whoever comes second waits `BUSY_TIMEOUT` for it and then
finds the stamp and the tables there. The lock is a transaction on the file itself and nothing
is kept beside it. The driver begins no transaction ahead of a `PRAGMA` or a `CREATE`, so on
that one connection it is told to begin none at all and the open sends `BEGIN IMMEDIATE` by
name. SQLAlchemy's transaction around it still sends the `COMMIT`, or the `ROLLBACK` that leaves
a refused file unwritten.

A database error met during the open, such as a file that is not a database or a lock nobody
gave up in time, leaves as a `DatabaseOpenError` that names the file and the cause. It is a
`StateError`, so the edge shows it to its caller as a refusal. An error the owner raises while
it holds the database leaves as itself.

SQLite checks a foreign key only on a connection that asks it to, so every connection of the
engine asks as it opens. A row whose parent is missing is then refused when its transaction
commits.

Every session of every repository writes this one file, so it is kept in SQLite's write-ahead
log mode, where a read does not wait for a write, and every connection waits `BUSY_TIMEOUT`, ten
seconds, for another session's write before its own is refused as locked. A transaction holds
rows only and no command runs inside one, so a wait is as long as the commits queued ahead, and
ten seconds covers several of them on a slow disk while a call still answers. The mode is kept in
the file's header and setting it writes the file, so it is set only once the stamp is accepted:
a refused file is not written at all. SQLite does not change the mode inside a transaction, and
outside one it refuses at once, with no wait, while another connection holds the write lock. So
the open asks for `locking_mode = EXCLUSIVE` before its commit, which keeps the lock past the
commit, and for `NORMAL` again before it sets the mode, which gives the lock up once that
statement has written the header. On a file already in the mode the three statements change
nothing. While a session has the file open, a `-wal` and a `-shm` file sit beside it.

No read returns more rows as a repository's history grows, and none answers from a part of what
it was asked for without saying so. A `ReadLimit` is the most rows one read returns, and the read
asks for one row more to learn whether there were more. A read of everything a ticket, a run or an
investigation holds is refused with `ReadLimitError` once there are more. A read of a repository's
history returns its newest rows as a `Latest`, which says whether older ones were left out.

A write is held to the limit of the read that returns its rows, so nothing the plugin stores makes
a ticket, a run or an investigation unreadable. A repository writes its rows, counts what the
owner then holds and raises `WriteLimitError` when that is past the limit, which rolls the
transaction back: a refused batch stores none of its rows. The count is read after the write on
purpose. The driver begins SQLite's transaction at a session's first write and not at a read
before it, so only a count taken after the write is read under the write lock, where no other
session can add a row between the count and the commit.
"""

from collections.abc import Generator, Sequence, Sized
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import sqlalchemy as sql
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.event import listen
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from mightymodels.core.declarative import Base
from mightymodels.core.errors import StateError
from mightymodels.core.repository_key import RepositoryKey

type RowTypes = tuple[type[Base], ...]

DATABASE_NAME = 'mightymodels.db'
SCHEMA_VERSION = 1
UNSTAMPED = 0
STORED_VERSION = 'PRAGMA user_version'
STAMP = f'{STORED_VERSION} = {SCHEMA_VERSION}'
STORED_OBJECTS = 'SELECT count(*) FROM sqlite_master'
ENFORCE_FOREIGN_KEYS = 'PRAGMA foreign_keys = ON'
KEEP_A_WRITE_AHEAD_LOG = 'PRAGMA journal_mode = WAL'
DRIVER_BEGINS_NOTHING = 'AUTOCOMMIT'
TAKE_THE_WRITE_LOCK = 'BEGIN IMMEDIATE'
KEEP_THE_LOCK_PAST_THE_COMMIT = 'PRAGMA locking_mode = EXCLUSIVE'
GIVE_THE_LOCK_UP_AFTER_THE_NEXT_STATEMENT = 'PRAGMA locking_mode = NORMAL'
BUSY_TIMEOUT = timedelta(seconds=10)


class DatabaseOpenError(StateError):
    def __init__(self, database_file: Path, cause: DBAPIError) -> None:
        super().__init__(f'{database_file} could not be opened as the state database: {cause.orig}')
        self.database_file = database_file
        self.cause = cause


class SchemaVersionError(StateError):
    def __init__(self, database_file: Path, found: int) -> None:
        super().__init__(
            f'{database_file} holds schema version {found} and this plugin reads version '
            f'{SCHEMA_VERSION}; the file is left as it is, and moving it away lets the plugin '
            'start an empty database'
        )
        self.database_file = database_file
        self.found = found


class ReadLimitError(StateError):
    def __init__(self, owner: str, *, rows: int, kept: str) -> None:
        super().__init__(
            f'{owner} holds more than {rows} {kept}, the most one read returns; the read is '
            'refused, because an answer from a part of them would be wrong'
        )
        self.owner = owner
        self.rows = rows
        self.kept = kept


class WriteLimitError(StateError):
    def __init__(self, owner: str, *, rows: int, kept: str) -> None:
        super().__init__(
            f'{owner} would hold more than {rows} {kept}, the most one read returns; the write '
            'is refused and none of it is stored, so what is held stays readable'
        )
        self.owner = owner
        self.rows = rows
        self.kept = kept


@dataclass(slots=True, kw_only=True, frozen=True)
class Latest[Row]:
    rows: tuple[Row, ...]
    older_left_out: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadLimit:
    rows: int
    kept: str

    @property
    def fetched(self) -> int:
        return self.rows + 1

    def error(self, fetched: Sized, *, owner: str) -> ReadLimitError | None:
        if len(fetched) <= self.rows:
            return None
        return ReadLimitError(owner, rows=self.rows, kept=self.kept)

    def write_error(self, held: int, *, owner: str) -> WriteLimitError | None:
        if held <= self.rows:
            return None
        return WriteLimitError(owner, rows=self.rows, kept=self.kept)

    def latest[Row](self, newest_first: Sequence[Row]) -> Latest[Row]:
        return Latest(
            rows=tuple(reversed(newest_first[: self.rows])),
            older_left_out=len(newest_first) > self.rows,
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class Database:
    engine: sql.Engine
    sessions: sessionmaker[Session]
    repository_key: RepositoryKey

    @contextmanager
    def transaction(self) -> Generator[Session]:
        with self.sessions.begin() as session:
            yield session


def enforce_foreign_keys(connection: DBAPIConnection, _entry: ConnectionPoolEntry) -> None:
    cursor = connection.cursor()
    cursor.execute(ENFORCE_FOREIGN_KEYS)
    cursor.close()


def stamp_a_file_that_holds_nothing(connection: sql.Connection) -> None:
    is_stamped = connection.exec_driver_sql(STORED_VERSION).scalar_one() != UNSTAMPED
    holds_something = connection.exec_driver_sql(STORED_OBJECTS).scalar_one() > 0
    if is_stamped or holds_something:
        return
    connection.exec_driver_sql(STAMP)


def schema_version_error(
    connection: sql.Connection, database_file: Path
) -> SchemaVersionError | None:
    found = connection.exec_driver_sql(STORED_VERSION).scalar_one()
    return None if found == SCHEMA_VERSION else SchemaVersionError(database_file, found)


@contextmanager
def database_errors_refused(database_file: Path) -> Generator[None]:
    try:
        yield
    except DBAPIError as error:
        raise DatabaseOpenError(database_file, error) from error


@contextmanager
def write_lock_held(engine: sql.Engine) -> Generator[sql.Connection]:
    with engine.connect().execution_options(isolation_level=DRIVER_BEGINS_NOTHING) as connection:
        with connection.begin():
            connection.exec_driver_sql(TAKE_THE_WRITE_LOCK)
            yield connection
            connection.exec_driver_sql(KEEP_THE_LOCK_PAST_THE_COMMIT)
        connection.exec_driver_sql(GIVE_THE_LOCK_UP_AFTER_THE_NEXT_STATEMENT)
        connection.exec_driver_sql(KEEP_A_WRITE_AHEAD_LOG)


@contextmanager
def open_database(
    database_file: Path, repository_key: RepositoryKey, row_types: RowTypes
) -> Generator[Database]:
    database_file.parent.mkdir(parents=True, exist_ok=True)
    engine = sql.create_engine(
        sql.URL.create('sqlite', database=str(database_file)),
        connect_args={'timeout': BUSY_TIMEOUT.total_seconds()},
    )
    listen(engine, 'connect', enforce_foreign_keys)
    tables = [Base.metadata.tables[row_type.__tablename__] for row_type in row_types]
    try:
        with database_errors_refused(database_file), write_lock_held(engine) as connection:
            stamp_a_file_that_holds_nothing(connection)
            if (error := schema_version_error(connection, database_file)) is not None:
                raise error
            Base.metadata.create_all(connection, tables=tables)
        yield Database(engine=engine, sessions=sessionmaker(engine), repository_key=repository_key)
    finally:
        engine.dispose()
