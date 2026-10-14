"""Where the state is kept: the database in the plugin data directory, the tree at the toplevel.

Both edges are asked here, the server through a tool call and `verify run` through its exit code
and standard error, and so is the SessionStart command that tells the second where the first
keeps its database.
"""

import json
import shlex
import sqlite3
import sys
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest
from mightymodels.cli import build_parser, main
from mightymodels.core.data_directory import SESSION_DATA_VARIABLE
from mightymodels.core.database import BUSY_TIMEOUT, DATABASE_NAME, SCHEMA_VERSION, Database
from mightymodels.core.tests.support import GitRunner
from mightymodels.core.workspace import STATE_DIRECTORY
from mightymodels.tools.tests.slug_calls import SHOW, SLUG, VALIDATE, WRITE, slug_results
from mightymodels.tools.tests.state_location import (
    PASSED,
    VERIFY_RUN,
)
from mightymodels.tools.tests.support import StateServer, ToolCall, tree

SQLITE_HEADER = b'SQLite format 3\x00'
SESSION_START = ('session-start',)
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
PLUGIN = Path(__file__).parent.parent
APPROVE: ToolCall = (
    'contract',
    {
        'action': 'approve',
        'commands': [{'id': 'I1', 'argv': [sys.executable, '-c', 'pass'], 'approved_by': 'user'}],
    },
)
STATUS: ToolCall = ('contract', {'action': 'status'})
SKIPPED = 'mightymodels hook did nothing: '


def sqlite_files_below(top: Path) -> list[str]:
    return [name for name, content in tree(top).items() if content.startswith(SQLITE_HEADER)]


@pytest.fixture
def subdirectory(repository: Path) -> Path:
    below = repository.joinpath('src', 'queue')
    below.mkdir(parents=True)
    return below


@pytest.fixture
def session_in_the_subdirectory(
    subdirectory: Path, data_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(str(subdirectory))
    monkeypatch.setenv(SESSION_DATA_VARIABLE, str(data_directory))


@pytest.fixture
def first_commit(repository: Path, git: GitRunner) -> None:
    git(repository, *IDENTITY, 'commit', '--quiet', '--allow-empty', '-m', 'first commit')


@pytest.fixture
def approved_command(state_server: StateServer) -> StateServer:
    slug_results(state_server, WRITE, VALIDATE, APPROVE)
    return state_server


class TestTheDatabaseFile:
    @pytest.fixture
    def busy_timeouts_of_two_connections(self, repository_database: Database) -> list[int]:
        engine = repository_database.engine
        with engine.connect() as one, engine.connect() as another:
            return [
                connection.exec_driver_sql('PRAGMA busy_timeout').scalar_one()
                for connection in (one, another)
            ]

    def test_the_server_creates_it_in_the_data_directory_and_none_in_the_repository(
        self, state_server: StateServer, repository: Path, data_directory: Path
    ) -> None:
        written, validated = slug_results(state_server, WRITE, VALIDATE)

        assert (written.is_error, validated.is_error) == (False, False)
        assert sqlite_files_below(data_directory) == [DATABASE_NAME]
        assert sqlite_files_below(repository) == []
        assert not repository.joinpath(STATE_DIRECTORY, DATABASE_NAME).exists()

    @pytest.mark.usefixtures('session_in_the_repository')
    def test_verify_run_creates_it_in_the_data_directory_and_none_in_the_repository(
        self, repository: Path, data_directory: Path
    ) -> None:
        main(VERIFY_RUN)

        assert sqlite_files_below(data_directory) == [DATABASE_NAME]
        assert sqlite_files_below(repository) == []

    @pytest.mark.usefixtures('connected_server')
    def test_a_new_file_is_stamped_with_the_schema_version(self, data_directory: Path) -> None:
        with closing(sqlite3.connect(data_directory.joinpath(DATABASE_NAME))) as connection:
            (stamp,) = connection.execute('PRAGMA user_version').fetchone()

        assert stamp == SCHEMA_VERSION

    @pytest.mark.usefixtures('connected_server')
    def test_an_opened_file_is_in_write_ahead_log_mode(self, data_directory: Path) -> None:
        with closing(sqlite3.connect(data_directory.joinpath(DATABASE_NAME))) as connection:
            (mode,) = connection.execute('PRAGMA journal_mode').fetchone()

        assert mode == 'wal'

    def test_every_connection_waits_the_stated_time_for_another_write(
        self, busy_timeouts_of_two_connections: list[int]
    ) -> None:
        stated_milliseconds = BUSY_TIMEOUT / timedelta(milliseconds=1)

        assert busy_timeouts_of_two_connections == [stated_milliseconds, stated_milliseconds]

    @pytest.mark.usefixtures('first_commit', 'approved_command', 'session_in_the_repository')
    def test_verify_run_opens_the_database_the_server_wrote(
        self, state_server: StateServer, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)
        (status,) = slug_results(state_server, STATUS)

        assert code == PASSED
        assert capsys.readouterr().out.startswith('I1 pass ')
        assert [command['state'] for command in status.structured_content['commands']] == [
            'pass task expect=0'
        ]


class TestStartingInASubdirectory:
    @pytest.fixture
    def server_in_the_subdirectory(self, subdirectory: Path, data_directory: Path) -> StateServer:
        return StateServer(root=subdirectory, data_directory=data_directory)

    def test_the_server_keeps_the_state_tree_at_the_git_toplevel(
        self, server_in_the_subdirectory: StateServer, repository: Path, subdirectory: Path
    ) -> None:
        written, validated = slug_results(server_in_the_subdirectory, WRITE, VALIDATE)

        assert (written.is_error, validated.is_error) == (False, False)
        assert repository.joinpath(STATE_DIRECTORY, SLUG, 'ticket.yml').is_file()
        assert not subdirectory.joinpath(STATE_DIRECTORY).exists()

    def test_a_server_at_the_toplevel_shows_what_one_in_the_subdirectory_staged(
        self, server_in_the_subdirectory: StateServer, state_server: StateServer
    ) -> None:
        slug_results(server_in_the_subdirectory, WRITE, VALIDATE)
        (shown,) = slug_results(state_server, SHOW)

        assert not shown.is_error
        assert shown.structured_content['unit']['slug'] == SLUG

    @pytest.mark.usefixtures('approved_command', 'session_in_the_subdirectory')
    def test_verify_run_finds_the_toplevel_and_the_contract_approved_there(
        self, subdirectory: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == PASSED
        assert capsys.readouterr().out.startswith('I1 pass ')
        assert not subdirectory.joinpath(STATE_DIRECTORY).exists()


class TestAnOriginThatIsNotExactlyAnOwnerAndAName:
    ORIGINS = (
        pytest.param('https://gitlab.com/group/sub/name.git', id='subgroup-path'),
        pytest.param('https://git.example.com/name.git', id='one-name'),
        pytest.param('/srv/git/acme/widgets.git', id='local-path'),
        pytest.param('file:///srv/git/acme/widgets.git', id='file-url'),
    )

    @pytest.fixture(params=ORIGINS)
    def repository(self, request: pytest.FixtureRequest, repository: Path, git: GitRunner) -> Path:
        git(repository, 'remote', 'add', 'origin', request.param)
        return repository

    def test_the_server_answers_its_calls(self, state_server: StateServer) -> None:
        written, validated, shown = slug_results(state_server, WRITE, VALIDATE, SHOW)

        assert (written.is_error, validated.is_error, shown.is_error) == (False, False, False)
        assert shown.structured_content['unit']['slug'] == SLUG

    @pytest.mark.usefixtures('approved_command', 'session_in_the_repository')
    def test_verify_run_runs_the_command_the_server_approved(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == PASSED
        assert capsys.readouterr().out.startswith('I1 pass ')


class TestTheSessionStartHook:
    HOOKS = PLUGIN.joinpath('hooks', 'hooks.json')

    def test_the_plugin_registers_this_command_as_its_one_session_start_hook(self) -> None:
        hooks = json.loads(self.HOOKS.read_text(encoding='utf-8'))['hooks']
        (matched,) = hooks['SessionStart']
        (hook,) = matched['hooks']
        launcher, *arguments = shlex.split(hook['command'])

        assert set(hooks) == {
            'SessionStart',
            'PreToolUse',
            'PostToolUse',
            'SubagentStop',
            'PreCompact',
        }
        assert (hook['type'], launcher) == ('command', '${CLAUDE_PLUGIN_ROOT}/bin/mightymodels')
        assert build_parser().parse_args(arguments).command == 'session-start'
