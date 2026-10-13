import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import pytest
from mightymodels_plugin.cli import main
from mightymodels_plugin.core.data_directory import (
    PLUGIN_DATA_VARIABLE,
    SESSION_DATA_VARIABLE,
    data_directory_from,
)
from mightymodels_plugin.core.database import (
    DATABASE_NAME,
    SCHEMA_VERSION,
    SchemaVersionError,
    open_database,
)
from mightymodels_plugin.core.repository_key import local_key
from mightymodels_plugin.core.workspace import PROJECT_DIR_VARIABLE, STATE_DIRECTORY
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.tests.slug_calls import SHOW, SLUG, VALIDATE, WRITE, slug_results
from mightymodels_plugin.tools.tests.state_location import (
    NOT_SET,
    REJECTED,
    VERIFY_RUN,
    KeptFile,
    kept,
)
from mightymodels_plugin.tools.tests.support import StateServer, text_of, tree

TOOL_NAMES = [
    'close',
    'contract',
    'crashout',
    'failed_fix',
    'investigation',
    'review',
    'similarity',
    'snapshot',
    'task',
    'ticket',
]
OLD_TABLES = (
    'CREATE TABLE tickets (slug VARCHAR NOT NULL, status VARCHAR NOT NULL, PRIMARY KEY (slug))',
    "INSERT INTO tickets VALUES ('retry-queue', 'staged')",
    'CREATE TABLE contract_commands (slug VARCHAR NOT NULL, command_id VARCHAR NOT NULL)',
    "INSERT INTO contract_commands VALUES ('retry-queue', 'I1')",
)
NOT_A_REPOSITORY = 'is not inside a git repository'
NEEDS_GIT = 'this needs git and no git executable is on PATH'


def sqlite_file(file: Path, statements: Sequence[str]) -> Path:
    file.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(file)) as connection:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    return file


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedStart:
    server: StateServer
    top: Path
    files_before: dict[str, bytes]

    def created_nothing(self) -> bool:
        return tree(self.top) == self.files_before


class TestAnOldDatabaseInTheRepository:
    @pytest.fixture
    def old_database(self, repository: Path) -> KeptFile:
        return kept(sqlite_file(repository.joinpath(STATE_DIRECTORY, DATABASE_NAME), OLD_TABLES))

    def test_the_server_does_not_read_its_rows_and_leaves_it_as_it_was(
        self, old_database: KeptFile, state_server: StateServer
    ) -> None:
        shown, written, validated = slug_results(state_server, SHOW, WRITE, VALIDATE)

        assert f'{SLUG} is not staged' in text_of(shown)
        assert (written.is_error, validated.is_error) == (False, False)
        assert old_database.is_as_it_was()

    @pytest.mark.usefixtures('session_in_the_repository')
    def test_verify_run_does_not_read_its_rows_and_leaves_it_as_it_was(
        self, old_database: KeptFile, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == REJECTED
        assert f'{SLUG} has no approved commands' in capsys.readouterr().err
        assert old_database.is_as_it_was()


class TestASchemaVersionMismatch:
    ANOTHER_VERSION = SCHEMA_VERSION + 1
    MISMATCHES = (
        pytest.param(
            (f'PRAGMA user_version = {ANOTHER_VERSION}',), ANOTHER_VERSION, id='another-version'
        ),
        pytest.param(
            ('PRAGMA journal_mode = WAL', f'PRAGMA user_version = {ANOTHER_VERSION}'),
            ANOTHER_VERSION,
            id='another-version-in-write-ahead-log-mode',
        ),
        pytest.param(OLD_TABLES, 0, id='unstamped-with-tables'),
    )

    @pytest.fixture
    def mismatched(self, request: pytest.FixtureRequest, data_directory: Path) -> KeptFile:
        return kept(sqlite_file(data_directory.joinpath(DATABASE_NAME), request.param))

    @pytest.mark.parametrize(('mismatched', 'found'), MISMATCHES, indirect=['mismatched'])
    def test_opening_is_refused_with_the_file_and_the_version_found(
        self, mismatched: KeptFile, found: int, tmp_path: Path
    ) -> None:
        with (
            pytest.raises(SchemaVersionError) as refused,
            open_database(mismatched.file, local_key(tmp_path), ROW_TYPES),
        ):
            pass

        assert (refused.value.database_file, refused.value.found) == (mismatched.file, found)
        assert mismatched.is_as_it_was()
        assert mismatched.has_nothing_beside_it()

    @pytest.mark.parametrize(('mismatched', 'found'), MISMATCHES, indirect=['mismatched'])
    def test_the_server_refuses_every_call_with_text_naming_the_file(
        self, mismatched: KeptFile, found: int, state_server: StateServer, repository: Path
    ) -> None:
        (written,) = slug_results(state_server, WRITE)

        assert written.is_error
        assert f'{mismatched.file} holds schema version {found}' in text_of(written)
        assert mismatched.is_as_it_was()
        assert mismatched.has_nothing_beside_it()
        assert not repository.joinpath(STATE_DIRECTORY).exists()

    @pytest.mark.usefixtures('session_in_the_repository')
    @pytest.mark.parametrize(('mismatched', 'found'), MISMATCHES, indirect=['mismatched'])
    def test_verify_run_refuses_on_standard_error_naming_the_file(
        self, mismatched: KeptFile, found: int, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == REJECTED
        assert f'{mismatched.file} holds schema version {found}' in capsys.readouterr().err
        assert mismatched.is_as_it_was()
        assert mismatched.has_nothing_beside_it()


class TestWithNoDataDirectory:
    UNSET = (pytest.param({}, id='unset'), pytest.param({PLUGIN_DATA_VARIABLE: ''}, id='empty'))

    @pytest.fixture
    def refused_start(
        self, request: pytest.FixtureRequest, repository: Path, tmp_path: Path
    ) -> RefusedStart:
        data_directory = data_directory_from(request.param, PLUGIN_DATA_VARIABLE)
        server = StateServer(root=repository, data_directory=data_directory)
        return RefusedStart(server=server, top=tmp_path, files_before=tree(tmp_path))

    @pytest.fixture
    def session_without_the_export(
        self, repository: Path, data_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> RefusedStart:
        monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(repository))
        monkeypatch.setenv(PLUGIN_DATA_VARIABLE, str(data_directory))
        monkeypatch.delenv(SESSION_DATA_VARIABLE, raising=False)
        server = StateServer(root=repository, data_directory=data_directory)
        return RefusedStart(
            server=server, top=repository.parent, files_before=tree(repository.parent)
        )

    @pytest.mark.parametrize('refused_start', UNSET, indirect=True)
    def test_the_server_lists_its_tools_and_refuses_every_call_naming_the_variable(
        self, refused_start: RefusedStart
    ) -> None:
        listed = refused_start.server.tools()
        written, shown = slug_results(refused_start.server, WRITE, SHOW)

        assert sorted(listed) == TOOL_NAMES
        assert (written.is_error, shown.is_error) == (True, True)
        assert f'{PLUGIN_DATA_VARIABLE} {NOT_SET}' in text_of(written)
        assert refused_start.created_nothing()

    def test_verify_run_refuses_on_standard_error_naming_the_variable_the_hook_exports(
        self, session_without_the_export: RefusedStart, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == REJECTED
        assert f'error: {SESSION_DATA_VARIABLE} {NOT_SET}' in capsys.readouterr().err
        assert session_without_the_export.created_nothing()


class TestWithNoGitToplevel:
    @pytest.fixture
    def outside_a_repository(
        self, tmp_path: Path, data_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> RefusedStart:
        directory = tmp_path.joinpath('plain-directory')
        directory.mkdir()
        monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(directory))
        monkeypatch.setenv(SESSION_DATA_VARIABLE, str(data_directory))
        server = StateServer(root=directory, data_directory=data_directory)
        return RefusedStart(server=server, top=tmp_path, files_before=tree(tmp_path))

    @pytest.fixture
    def without_git(
        self, state_server: StateServer, data_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> RefusedStart:
        top = state_server.root.parent
        monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(state_server.root))
        monkeypatch.setenv(SESSION_DATA_VARIABLE, str(data_directory))
        monkeypatch.setenv('PATH', str(top.joinpath('no-binaries')))
        return RefusedStart(server=state_server, top=top, files_before=tree(top))

    def test_outside_a_repository_the_server_refuses_every_call_naming_the_directory(
        self, outside_a_repository: RefusedStart
    ) -> None:
        written, shown = slug_results(outside_a_repository.server, WRITE, SHOW)

        assert (written.is_error, shown.is_error) == (True, True)
        assert f'{outside_a_repository.server.root} {NOT_A_REPOSITORY}' in text_of(written)
        assert outside_a_repository.created_nothing()

    def test_outside_a_repository_verify_run_refuses_on_standard_error_naming_the_directory(
        self, outside_a_repository: RefusedStart, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == REJECTED
        assert f'{outside_a_repository.server.root} {NOT_A_REPOSITORY}' in capsys.readouterr().err
        assert outside_a_repository.created_nothing()

    def test_without_git_the_server_refuses_every_call_naming_git(
        self, without_git: RefusedStart
    ) -> None:
        written, shown = slug_results(without_git.server, WRITE, SHOW)

        assert (written.is_error, shown.is_error) == (True, True)
        assert NEEDS_GIT in text_of(written)
        assert without_git.created_nothing()

    def test_without_git_verify_run_refuses_on_standard_error_naming_git(
        self, without_git: RefusedStart, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == REJECTED
        assert f'error: {NEEDS_GIT}' in capsys.readouterr().err
        assert without_git.created_nothing()
