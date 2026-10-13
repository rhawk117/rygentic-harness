import json
import os
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels.core.database import DATABASE_NAME, open_database
from mightymodels.core.repository_key import local_key
from mightymodels.core.tests.support import GitRunner
from mightymodels.core.workspace import (
    EXCLUDE_LINE,
    STATE_DIRECTORY,
    NotARepositoryError,
    find_root,
    git_at,
)
from mightymodels.tools.row_types import ROW_TYPES
from mightymodels.tools.tests.support import StateServer

type MasterRow = dict[str, str | None]


class TestFindRoot:
    def test_uses_claude_project_dir_when_set(self, tmp_path: Path) -> None:
        project = tmp_path.joinpath('project')

        assert find_root({'CLAUDE_PROJECT_DIR': str(project)}, tmp_path) == project

    @pytest.mark.parametrize(
        'environ',
        [pytest.param({}, id='unset'), pytest.param({'CLAUDE_PROJECT_DIR': ''}, id='empty')],
    )
    def test_falls_back_to_the_working_directory(
        self, environ: dict[str, str], tmp_path: Path
    ) -> None:
        assert find_root(environ, tmp_path) == tmp_path

    def test_lookup_from_the_process_environment(
        self, repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(repository))
        monkeypatch.chdir(tmp_path)

        assert find_root(os.environ, Path.cwd()) == repository

    def test_lookup_from_the_process_working_directory(
        self, repository: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv('CLAUDE_PROJECT_DIR', raising=False)
        monkeypatch.chdir(repository)

        assert find_root(os.environ, Path.cwd()) == repository.resolve()


class TestOpenRepository:
    def exclude_lines(self, repository: Path) -> list[str]:
        exclude = repository.joinpath('.git', 'info', 'exclude')
        return exclude.read_text(encoding='utf-8').splitlines()

    @pytest.fixture
    def worktree(self, repository: Path, tmp_path: Path, git: GitRunner) -> Path:
        git(
            repository,
            '-c',
            'user.name=t',
            '-c',
            'user.email=t@t',
            'commit',
            '--allow-empty',
            '-m',
            'init',
        )
        linked = tmp_path.joinpath('worktree')
        git(repository, 'worktree', 'add', '--quiet', str(linked), '-b', 'other')
        return linked

    @pytest.fixture
    def exclude_without_a_trailing_newline(self, repository: Path) -> None:
        repository.joinpath('.git', 'info', 'exclude').write_text('*.log', encoding='utf-8')

    def test_creates_the_database(self, data_directory: Path, state_server: StateServer) -> None:
        state_server.connect()

        assert data_directory.joinpath(DATABASE_NAME).is_file()

    def test_excludes_the_state_directory_from_git(
        self, repository: Path, state_server: StateServer
    ) -> None:
        state_server.connect()

        assert EXCLUDE_LINE in self.exclude_lines(repository)

    def test_excluded_state_does_not_show_in_git_status(
        self, repository: Path, state_server: StateServer, git: GitRunner
    ) -> None:
        state_server.connect()

        assert git(repository, 'status', '--porcelain') == ''

    def test_is_idempotent(self, repository: Path, state_server: StateServer) -> None:
        state_server.connect()
        state_server.connect()

        assert self.exclude_lines(repository).count(EXCLUDE_LINE) == 1

    @pytest.mark.usefixtures('exclude_without_a_trailing_newline')
    def test_keeps_existing_exclude_lines_without_a_trailing_newline(
        self, repository: Path, state_server: StateServer
    ) -> None:
        state_server.connect()

        assert self.exclude_lines(repository) == ['*.log', EXCLUDE_LINE]

    def test_linked_worktree_writes_to_the_common_git_dir(
        self, repository: Path, worktree: Path, data_directory: Path
    ) -> None:
        StateServer(root=worktree, data_directory=data_directory).connect()

        assert EXCLUDE_LINE in self.exclude_lines(repository)
        assert data_directory.joinpath(DATABASE_NAME).is_file()


class TestOpenDatabase:
    TABLES_SNAPSHOT = Path(__file__).parent.joinpath('fixtures', 'database-tables.json')
    MASTER_ROWS = sql.text('SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name')

    @pytest.fixture
    def master_rows_of_a_fresh_database(self, tmp_path: Path) -> list[MasterRow]:
        database_file = tmp_path.joinpath('fresh', DATABASE_NAME)
        opening = open_database(database_file, local_key(tmp_path), ROW_TYPES)
        with opening as opened, opened.engine.connect() as connection:
            return [dict(row) for row in connection.execute(self.MASTER_ROWS).mappings()]

    @pytest.fixture
    def data_directory_with_url_characters(self, tmp_path: Path) -> Path:
        return tmp_path.joinpath('odd?mode=memory#cache')

    def test_finds_the_database_in_a_data_directory_whose_path_has_url_characters(
        self, data_directory_with_url_characters: Path, tmp_path: Path
    ) -> None:
        database = data_directory_with_url_characters.joinpath(DATABASE_NAME)

        with open_database(database, local_key(tmp_path), ROW_TYPES) as opened:
            located = opened.engine.url.database

        assert located == str(database)
        assert database.stat().st_size > 0
        assert [path.name for path in tmp_path.iterdir()] == [
            data_directory_with_url_characters.name
        ]

    def test_database_tables_of_a_fresh_database_equal_the_snapshot(
        self, master_rows_of_a_fresh_database: list[MasterRow]
    ) -> None:
        assert master_rows_of_a_fresh_database == json.loads(
            self.TABLES_SNAPSHOT.read_text(encoding='utf-8')
        )


class TestOutsideARepository:
    @pytest.fixture
    def outside(self, tmp_path: Path) -> Path:
        directory = tmp_path.joinpath('outside')
        directory.mkdir()
        return directory

    def test_refuses_a_directory_outside_a_repository(self, outside: Path) -> None:
        refusal = git_at(outside).refusal()

        assert isinstance(refusal, NotARepositoryError)
        assert refusal.root == outside
        assert not outside.joinpath(STATE_DIRECTORY).exists()
