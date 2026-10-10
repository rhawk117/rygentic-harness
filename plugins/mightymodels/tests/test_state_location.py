"""Where the state is kept: the database in the plugin data directory, the tree at the toplevel.

Both edges are asked here, the server through a tool call and `verify run` through its exit code
and standard error, and so is the SessionStart command that tells the second where the first
keeps its database.
"""

import json
import shlex
import sqlite3
import sys
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest
from mcp.types import CallToolResult
from mightymodels_plugin.cli import build_parser, main
from mightymodels_plugin.commands.session_start import ENV_FILE_VARIABLE
from mightymodels_plugin.core.data_directory import (
    PLUGIN_DATA_VARIABLE,
    SESSION_DATA_VARIABLE,
    data_directory_from,
)
from mightymodels_plugin.core.database import (
    BUSY_TIMEOUT,
    DATABASE_NAME,
    SCHEMA_VERSION,
    Database,
    SchemaVersionError,
    open_database,
)
from mightymodels_plugin.core.repository_key import local_key
from mightymodels_plugin.core.workspace import PROJECT_DIR_VARIABLE, STATE_DIRECTORY
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.tests.support import StateServer, ToolCall, text_of, tree

type GitRunner = Callable[..., str]

SLUG = 'retry-queue'
PASSED, REJECTED = 0, 2
SQLITE_HEADER = b'SQLite format 3\x00'
VERIFY_RUN = ('verify', 'run', '--slug', SLUG, '--all')
SESSION_START = ('session-start',)
PLUGIN = Path(__file__).parent.parent
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
WRITE: ToolCall = (
    'ticket',
    {
        'action': 'write',
        'fields': {
            'summary': 'Retry queue drains slowly',
            'scope': 'med',
            'compaction': False,
            'branch': 'fix/retry-queue',
            'context': ['drain loop sleeps between batches'],
        },
    },
)
VALIDATE: ToolCall = ('ticket', {'action': 'validate'})
SHOW: ToolCall = ('ticket', {'action': 'show'})
APPROVE: ToolCall = (
    'contract',
    {
        'action': 'approve',
        'commands': [{'id': 'I1', 'argv': [sys.executable, '-c', 'pass'], 'approved_by': 'user'}],
    },
)
STATUS: ToolCall = ('contract', {'action': 'status'})
OLD_TABLES = (
    'CREATE TABLE tickets (slug VARCHAR NOT NULL, status VARCHAR NOT NULL, PRIMARY KEY (slug))',
    "INSERT INTO tickets VALUES ('retry-queue', 'staged')",
    'CREATE TABLE contract_commands (slug VARCHAR NOT NULL, command_id VARCHAR NOT NULL)',
    "INSERT INTO contract_commands VALUES ('retry-queue', 'I1')",
)
SKIPPED = 'mightymodels hook did nothing: '
NOT_SET = 'is not set, so there is no plugin data directory'
NOT_A_REPOSITORY = 'is not inside a git repository'
NEEDS_GIT = 'this needs git and no git executable is on PATH'


def slug_results(server: StateServer, *calls: ToolCall) -> list[CallToolResult]:
    return server.call(*((name, {'slug': SLUG, **arguments}) for name, arguments in calls))


def sqlite_file(file: Path, statements: Sequence[str]) -> Path:
    file.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(file)) as connection:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    return file


def sqlite_files_below(top: Path) -> list[str]:
    return [name for name, content in tree(top).items() if content.startswith(SQLITE_HEADER)]


@dataclass(slots=True, kw_only=True, frozen=True)
class KeptFile:
    file: Path
    content: bytes

    def is_as_it_was(self) -> bool:
        return self.file.read_bytes() == self.content

    def has_nothing_beside_it(self) -> bool:
        return list(self.file.parent.iterdir()) == [self.file]


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedStart:
    server: StateServer
    top: Path
    files_before: dict[str, bytes]

    def created_nothing(self) -> bool:
        return tree(self.top) == self.files_before


def kept(file: Path) -> KeptFile:
    return KeptFile(file=file, content=file.read_bytes())


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

    @pytest.mark.usefixtures('approved_command', 'session_in_the_repository')
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

    @pytest.mark.usefixtures('hook_env_file')
    def test_it_prints_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(SESSION_START)

        assert capsys.readouterr() == ('', '')


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
