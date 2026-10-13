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
from mightymodels_plugin.cli import build_parser, main
from mightymodels_plugin.commands.session_start import ENV_FILE_VARIABLE
from mightymodels_plugin.core.data_directory import PLUGIN_DATA_VARIABLE, SESSION_DATA_VARIABLE
from mightymodels_plugin.core.database import BUSY_TIMEOUT, DATABASE_NAME, SCHEMA_VERSION, Database
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.core.workspace import PROJECT_DIR_VARIABLE, STATE_DIRECTORY
from mightymodels_plugin.tools.tests.slug_calls import SHOW, SLUG, VALIDATE, WRITE, slug_results
from mightymodels_plugin.tools.tests.state_location import (
    NOT_SET,
    PASSED,
    VERIFY_RUN,
    KeptFile,
    kept,
)
from mightymodels_plugin.tools.tests.support import StateServer, ToolCall, tree

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
    monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(subdirectory))
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


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    return tmp_path.joinpath('session-env.sh')


@pytest.fixture
def hook_env_file(data_directory: Path, env_file: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(PLUGIN_DATA_VARIABLE, str(data_directory))
    monkeypatch.setenv(ENV_FILE_VARIABLE, str(env_file))
    return env_file


class TestSessionStartExport:
    OTHER_EXPORT = 'export OTHER_PLUGIN_DATA=/elsewhere\n'

    @pytest.fixture
    def data_directory(self, tmp_path: Path) -> Path:
        return tmp_path.joinpath("the plugin's $data; directory")

    @pytest.fixture
    def hook_env_file_with_another_export(self, hook_env_file: Path) -> Path:
        hook_env_file.write_text(self.OTHER_EXPORT, encoding='utf-8')
        return hook_env_file

    @pytest.fixture
    def hook_env_file_with_no_final_newline(self, hook_env_file: Path) -> Path:
        hook_env_file.write_text(self.OTHER_EXPORT.removesuffix('\n'), encoding='utf-8')
        return hook_env_file

    @pytest.fixture
    def hook_env_file_with_the_export_and_no_final_newline(self, hook_env_file: Path) -> Path:
        main(SESSION_START)
        exported = hook_env_file.read_text(encoding='utf-8')
        hook_env_file.write_text(exported.removesuffix('\n'), encoding='utf-8')
        return hook_env_file

    def test_it_appends_one_shell_quoted_export_of_the_data_directory_and_nothing_else(
        self, data_directory: Path, hook_env_file: Path, tmp_path: Path
    ) -> None:
        code = main(SESSION_START)
        exported = hook_env_file.read_text(encoding='utf-8')

        assert code == PASSED
        assert exported.count('\n') == 1
        assert shlex.split(exported) == ['export', f'{SESSION_DATA_VARIABLE}={data_directory}']
        assert set(tree(tmp_path)) == {hook_env_file.name}

    def test_it_keeps_what_the_env_file_already_exports(
        self, hook_env_file_with_another_export: Path, data_directory: Path
    ) -> None:
        main(SESSION_START)
        exports = hook_env_file_with_another_export.read_text(encoding='utf-8')
        kept_line, exported = exports.splitlines(keepends=True)

        assert kept_line == self.OTHER_EXPORT
        assert shlex.split(exported) == ['export', f'{SESSION_DATA_VARIABLE}={data_directory}']

    def test_run_twice_it_appends_the_export_once(
        self, data_directory: Path, hook_env_file_with_another_export: Path
    ) -> None:
        main(SESSION_START)
        main(SESSION_START)
        exports = hook_env_file_with_another_export.read_text(encoding='utf-8').splitlines()

        assert exports[0] == self.OTHER_EXPORT.strip()
        assert [shlex.split(line) for line in exports[1:]] == [
            ['export', f'{SESSION_DATA_VARIABLE}={data_directory}']
        ]

    @pytest.mark.parametrize(
        'runs',
        [
            pytest.param(1, id='no-final-newline-run-once'),
            pytest.param(2, id='no-final-newline-run-twice'),
        ],
    )
    def test_after_a_line_with_no_newline_it_exports_once_on_a_line_of_its_own(
        self, runs: int, data_directory: Path, hook_env_file_with_no_final_newline: Path
    ) -> None:
        for _ in range(runs):
            main(SESSION_START)
        exports = hook_env_file_with_no_final_newline.read_text(encoding='utf-8')
        kept_line, exported = exports.splitlines(keepends=True)

        assert kept_line == self.OTHER_EXPORT
        assert shlex.split(exported) == ['export', f'{SESSION_DATA_VARIABLE}={data_directory}']

    def test_it_appends_no_second_copy_of_an_export_with_no_final_newline(
        self, data_directory: Path, hook_env_file_with_the_export_and_no_final_newline: Path
    ) -> None:
        main(SESSION_START)
        exports = hook_env_file_with_the_export_and_no_final_newline.read_text(encoding='utf-8')

        assert [shlex.split(line) for line in exports.splitlines()] == [
            ['export', f'{SESSION_DATA_VARIABLE}={data_directory}']
        ]

    @pytest.mark.usefixtures('hook_env_file')
    def test_it_prints_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(SESSION_START)

        assert capsys.readouterr() == ('', '')


class TestSessionStartExportWithALineBoundaryInTheName:
    LINE_BOUNDARIES = (
        pytest.param('\n', id='newline-in-the-name'),
        pytest.param('\x0c', id='form-feed-in-the-name'),
        pytest.param('\r', id='carriage-return-in-the-name'),
    )

    @pytest.fixture(params=LINE_BOUNDARIES)
    def data_directory(self, request: pytest.FixtureRequest, tmp_path: Path) -> Path:
        return tmp_path.joinpath(f'the plugin{request.param}data directory')

    @pytest.fixture
    def env_file_after_one_run(self, hook_env_file: Path) -> KeptFile:
        main(SESSION_START)
        return kept(hook_env_file)

    def test_a_second_run_leaves_the_env_file_as_the_first_run_left_it_holding_one_export(
        self, data_directory: Path, env_file_after_one_run: KeptFile
    ) -> None:
        main(SESSION_START)

        assert env_file_after_one_run.is_as_it_was()
        assert shlex.split(env_file_after_one_run.content.decode()) == [
            'export',
            f'{SESSION_DATA_VARIABLE}={data_directory}',
        ]


class TestSessionStartWithAVariableMissing:
    @pytest.fixture
    def without_a_data_directory(self, env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PLUGIN_DATA_VARIABLE, raising=False)
        monkeypatch.setenv(ENV_FILE_VARIABLE, str(env_file))

    @pytest.fixture
    def without_an_env_file(self, data_directory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PLUGIN_DATA_VARIABLE, str(data_directory))
        monkeypatch.delenv(ENV_FILE_VARIABLE, raising=False)

    @pytest.mark.usefixtures('without_a_data_directory')
    def test_without_a_data_directory_it_skips_naming_the_variable_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(SESSION_START)

        assert code == PASSED
        assert f'{SKIPPED}{PLUGIN_DATA_VARIABLE} {NOT_SET}' in capsys.readouterr().err
        assert tree(tmp_path) == {}

    @pytest.mark.usefixtures('without_an_env_file')
    def test_without_an_env_file_it_skips_naming_the_variable_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(SESSION_START)

        assert code == PASSED
        assert f'{SKIPPED}{ENV_FILE_VARIABLE} is not set' in capsys.readouterr().err
        assert tree(tmp_path) == {}


class TestTheSessionStartHook:
    HOOKS = PLUGIN.joinpath('hooks', 'hooks.json')

    @pytest.fixture
    def session_after_the_hook(
        self, approved_command: StateServer, hook_env_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> StateServer:
        main(SESSION_START)
        _, assignment = shlex.split(hook_env_file.read_text(encoding='utf-8'))
        name, _, value = assignment.partition('=')
        monkeypatch.delenv(PLUGIN_DATA_VARIABLE)
        monkeypatch.setenv(name, value)
        monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(approved_command.root))
        return approved_command

    @pytest.mark.usefixtures('first_commit')
    def test_with_what_the_hook_exported_verify_run_opens_the_database_the_server_wrote(
        self, session_after_the_hook: StateServer, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)
        (status,) = slug_results(session_after_the_hook, STATUS)

        assert code == PASSED
        assert capsys.readouterr().out.startswith('I1 pass ')
        assert [command['state'] for command in status.structured_content['commands']] == [
            'pass task expect=0'
        ]

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
