import json
import sqlite3
import sys
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels_plugin.core.database import (
    DATABASE_NAME,
    KEEP_A_WRITE_AHEAD_LOG,
    TAKE_THE_WRITE_LOCK,
    DatabaseOpenError,
    open_database,
    write_lock_held,
)
from mightymodels_plugin.core.process import CompletedRun, RunOutcome, process_runner
from mightymodels_plugin.core.repository_key import local_key
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.tests.support import FILES_OF_AN_OPEN_DATABASE, tree
from sqlalchemy.exc import OperationalError

PROCESSES = 6
ROUNDS = 10
OPEN_AT_THE_RELEASE = """
import json
import sys
import time
from pathlib import Path

from mightymodels_plugin.core.database import open_database
from mightymodels_plugin.core.repository_key import local_key
from mightymodels_plugin.tools.row_types import ROW_TYPES

database_file = Path(sys.argv[1])
time.sleep(max(0.0, float(sys.argv[2]) - time.time()))
with (
    open_database(database_file, local_key(database_file.parent), ROW_TYPES) as opened,
    opened.engine.connect() as connection,
):
    tables = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'")
    print(json.dumps(sorted(tables.scalars())))
"""


def takes_the_write_lock(database_file: Path) -> bool:
    with closing(sqlite3.connect(database_file, timeout=0)) as another:
        try:
            another.execute(TAKE_THE_WRITE_LOCK)
        except sqlite3.OperationalError:
            return False
        return another.in_transaction


@dataclass(slots=True, kw_only=True, frozen=True)
class LockWatch:
    database_file: Path
    statements: list[str] = field(default_factory=list)
    refused_another: list[str] = field(default_factory=list)

    def record(self, statement: str) -> None:
        self.statements.append(statement)
        if not takes_the_write_lock(self.database_file):
            self.refused_another.append(statement)


@pytest.fixture
def database_file(data_directory: Path) -> Path:
    return data_directory.joinpath(DATABASE_NAME)


class TestProcessesThatOpenOneFreshFileTogether:
    LEAD = timedelta(seconds=1)
    TIMEOUT = 30
    FTS_INDEX = 'similarity_index'
    WHOLE_SCHEMA = frozenset({FTS_INDEX, *(row_type.__tablename__ for row_type in ROW_TYPES)})

    @pytest.fixture(params=range(ROUNDS))
    def opened_together(self, database_file: Path) -> list[RunOutcome]:
        release = time.time() + self.LEAD.total_seconds()
        argv = [sys.executable, '-c', OPEN_AT_THE_RELEASE, str(database_file), str(release)]
        runner = process_runner()
        with ThreadPoolExecutor(max_workers=PROCESSES) as launches:
            runs = [
                launches.submit(runner.run, argv, timeout=self.TIMEOUT) for _ in range(PROCESSES)
            ]
        return [run.result() for run in runs]

    def reports_the_whole_schema(self, run: RunOutcome) -> bool:
        exited_zero = isinstance(run, CompletedRun) and run.exit == 0
        return exited_zero and set(json.loads(run.stdout)) >= self.WHOLE_SCHEMA

    def test_every_process_exits_zero_with_the_sixteen_tables_and_the_fts_index(
        self, opened_together: list[RunOutcome]
    ) -> None:
        without_the_schema = [
            run for run in opened_together if not self.reports_the_whole_schema(run)
        ]

        assert len(opened_together) == PROCESSES
        assert without_the_schema == []


class TestTheWriteLockOfAFirstOpen:
    @pytest.fixture
    def engine(self, database_file: Path) -> Generator[sql.Engine]:
        database_file.parent.mkdir()
        engine = sql.create_engine(sql.URL.create('sqlite', database=str(database_file)))
        yield engine
        engine.dispose()

    @pytest.fixture
    def watch(self, engine: sql.Engine, database_file: Path) -> LockWatch:
        watch = LockWatch(database_file=database_file)
        with engine.connect() as pooled:
            driver_connection = pooled.connection.driver_connection
            assert isinstance(driver_connection, sqlite3.Connection)
            driver_connection.set_trace_callback(watch.record)
        with write_lock_held(engine) as connection:
            connection.exec_driver_sql('CREATE TABLE made_under_the_lock (id INTEGER)')
        return watch

    def test_no_other_connection_takes_it_from_the_begin_until_the_log_mode_is_set(
        self, watch: LockWatch
    ) -> None:
        begun = watch.statements.index(TAKE_THE_WRITE_LOCK)
        mode_set = watch.statements.index(KEEP_A_WRITE_AHEAD_LOG)

        assert watch.refused_another == watch.statements[begun + 1 : mode_set + 1]

    @pytest.mark.usefixtures('repository_database')
    def test_another_connection_takes_it_without_a_wait_once_the_open_returns(
        self, database_file: Path
    ) -> None:
        assert takes_the_write_lock(database_file)


class TestAFileThatIsNotADatabase:
    CONTENT = b'these bytes are not a database ' * 64
    CAUSE = 'file is not a database'

    @pytest.fixture
    def not_a_database(self, database_file: Path) -> Path:
        database_file.parent.mkdir()
        database_file.write_bytes(self.CONTENT)
        return database_file

    @pytest.fixture
    def refusal(self, not_a_database: Path, tmp_path: Path) -> DatabaseOpenError:
        with (
            pytest.raises(DatabaseOpenError) as refused,
            open_database(not_a_database, local_key(tmp_path), ROW_TYPES),
        ):
            pass
        return refused.value

    def test_opening_it_is_refused_with_the_file_and_the_cause(
        self, refusal: DatabaseOpenError, not_a_database: Path
    ) -> None:
        assert refusal.database_file == not_a_database
        assert str(refusal) == (
            f'{not_a_database} could not be opened as the state database: {self.CAUSE}'
        )
        assert refusal.__cause__ is refusal.cause

    @pytest.mark.usefixtures('refusal')
    def test_it_is_left_as_it_was_with_nothing_beside_it(self, not_a_database: Path) -> None:
        assert not_a_database.read_bytes() == self.CONTENT
        assert list(not_a_database.parent.iterdir()) == [not_a_database]


class TestAnOpenDatabase:
    def test_a_database_error_its_caller_raises_leaves_as_itself(
        self, database_file: Path, tmp_path: Path
    ) -> None:
        with (
            pytest.raises(OperationalError, match='no such table'),
            open_database(database_file, local_key(tmp_path), ROW_TYPES) as opened,
            opened.transaction() as session,
        ):
            session.execute(sql.text('SELECT * FROM no_such_table'))

    @pytest.mark.usefixtures('repository_database')
    def test_its_directory_holds_the_file_and_what_sqlite_keeps_beside_it_and_no_other(
        self, data_directory: Path
    ) -> None:
        held = set(tree(data_directory))

        assert DATABASE_NAME in held
        assert held <= FILES_OF_AN_OPEN_DATABASE
