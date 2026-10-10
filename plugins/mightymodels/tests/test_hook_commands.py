"""The hook commands the plugin registers: what hooks.json runs, and what each one does.

A hook command runs `main` with the hook's JSON on standard input and the variables Claude Code
sets for a hook. Each exits 0 whatever happens, since a hook that exits 2 can keep a subagent
from stopping or a compaction from running; only the completion gate answers a block, on
standard output.
"""

import asyncio
import io
import json
import os
import shlex
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pytest
import sqlalchemy as sql
from mightymodels_plugin.cli import build_parser, main
from mightymodels_plugin.commands.session_start import ENV_FILE_VARIABLE
from mightymodels_plugin.core.data_directory import PLUGIN_DATA_VARIABLE, SESSION_DATA_VARIABLE
from mightymodels_plugin.core.database import DATABASE_NAME, Database
from mightymodels_plugin.core.declarative import REPORT_LIMIT
from mightymodels_plugin.core.repository_key import spool_file_prefix
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import PROJECT_DIR_VARIABLE, Workspace
from mightymodels_plugin.tools.similarity.schema import SimilarityKind
from mightymodels_plugin.tools.similarity.spool import SPOOL_DIRECTORY, SPOOL_FILE_BYTES
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow
from mightymodels_plugin.tools.task.schema import Implementer, TaskStart
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.tests.support import (
    StateServer,
    ToolCall,
    repository_key_of,
    text_of,
)
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

PLUGIN = Path(__file__).parent.parent
HOOKS = PLUGIN.joinpath('hooks', 'hooks.json')
BIN = PLUGIN.joinpath('bin')
PLUGIN_ROOT = '${CLAUDE_PLUGIN_ROOT}'
SUBCOMMANDS_OF_WRAPPERS_WITHOUT_ARGUMENTS = MappingProxyType(
    {'mightymodels-dispatch-hook': 'dispatch-hook'}
)

SKIPPED = 'mightymodels hook did nothing: '
SLUG = 'retry-queue'
TICKET = Slug(SLUG)
OTHER_SLUG = 'retry-queue-again'
BRANCH = 'fix/retry'
REPORT = '<report><verdict>VERIFIED</verdict><findings>the drain loop sleeps</findings></report>'
SEARCH: ToolCall = ('similarity', {'action': 'search', 'query': 'the drain loop sleeps'})
SCOUTS = ('mightymodels:code-scout', 'mightymodels:web-scout')
IMPLEMENTERS = ('mightymodels:engineer', 'mightymodels:architect')
OTHER_AGENTS = (
    'mightymodels:qualitylens',
    'mightymodels:wingman',
    'code-scout',
    'engineer',
    'other:engineer',
    'general-purpose',
    '',
)
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': BRANCH,
        'context': ['drain loop sleeps between batches'],
    }
)
DONE_WITH_A_COMMIT = '## ASKED\nobjective: drain\n\n## DONE\ncommit: 0123abc\n'
DONE_WITHOUT_A_COMMIT = '## ASKED\nobjective: drain\n\n## DONE\nI did it.\n'
UNREADABLE_INPUTS = (
    pytest.param('', id='empty'),
    pytest.param('not json', id='not-json'),
    pytest.param('[]', id='not-an-object'),
)


def hook_input(event: str, agent_type: str | None = None, **given: object) -> str:
    fields = {'hook_event_name': event, 'session_id': 's1', 'cwd': '/ignored'}
    return json.dumps(fields | ({} if agent_type is None else {'agent_type': agent_type}) | given)


def scout_stop(agent_type: str = 'mightymodels:code-scout', **given: object) -> str:
    stop = {'agent_id': 'a1b2', 'stop_hook_active': False, 'last_assistant_message': REPORT}
    return hook_input('SubagentStop', agent_type, **(stop | given))


def implementer_stop(agent_type: str = 'mightymodels:engineer', **given: object) -> str:
    stop = {'stop_hook_active': False, 'last_assistant_message': 'done'}
    return hook_input('SubagentStop', agent_type, **(stop | given))


@dataclass(slots=True, kw_only=True, frozen=True)
class Hook:
    repository: Path
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]

    def run(self, command: str, text: str) -> tuple[int, str, str]:
        self.monkeypatch.setattr(sys, 'stdin', io.StringIO(text))
        code = main([command])
        captured = self.capsys.readouterr()
        return code, captured.out, captured.err


@pytest.fixture
def hook(
    in_the_repository: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Hook:
    return Hook(repository=in_the_repository, monkeypatch=monkeypatch, capsys=capsys)


@pytest.fixture
def in_the_repository(
    repository: Path, data_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setenv(PLUGIN_DATA_VARIABLE, str(data_directory))
    monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(repository))
    return repository


@pytest.fixture
def spool(data_directory: Path) -> Path:
    return data_directory.joinpath(SPOOL_DIRECTORY)


def hooks_registered() -> list[tuple[str, str, str]]:
    registered = json.loads(HOOKS.read_text(encoding='utf-8'))['hooks']
    return [
        (event, group.get('matcher', ''), entry['command'])
        for event, groups in registered.items()
        for group in groups
        for entry in group['hooks']
    ]


class TestHooksJson:
    @pytest.fixture(params=hooks_registered(), ids=lambda registered: registered[2].split('/')[-1])
    def command(self, request: pytest.FixtureRequest) -> list[str]:
        return shlex.split(request.param[2].replace(PLUGIN_ROOT, str(PLUGIN)))

    def test_every_command_names_a_script_in_bin(self, command: list[str]) -> None:
        script = Path(command[0])

        assert script.parent == BIN
        assert script.is_file()

    def test_every_command_names_a_subcommand_the_parser_accepts(self, command: list[str]) -> None:
        script = Path(command[0])
        wrapped = SUBCOMMANDS_OF_WRAPPERS_WITHOUT_ARGUMENTS.get(script.name)
        subcommand = command[1] if wrapped is None else wrapped

        assert build_parser().parse_args([subcommand]).command == subcommand
        assert wrapped is None or wrapped in script.read_text(encoding='utf-8')

    def test_the_events_are_the_ones_the_behaviours_need(self) -> None:
        events = {event for event, _, _ in hooks_registered()}

        assert events == {'SessionStart', 'PreToolUse', 'PostToolUse', 'SubagentStop', 'PreCompact'}

    def test_the_subagent_hooks_are_matched_on_the_agent_types_they_serve(self) -> None:
        matchers = {
            command.split()[-1]: matcher
            for event, matcher, command in hooks_registered()
            if event == 'SubagentStop'
        }

        assert matchers == {
            'subagent-record': '^mightymodels:(code-scout|web-scout)$',
            'completion-gate': '^mightymodels:(engineer|architect)$',
        }


class TestSessionBootstrap:
    @pytest.fixture
    def env_file(
        self, tmp_path: Path, data_directory: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Path:
        file = tmp_path.joinpath('session-env.sh')
        monkeypatch.setenv(PLUGIN_DATA_VARIABLE, str(data_directory))
        monkeypatch.setenv(ENV_FILE_VARIABLE, str(file))
        return file

    def test_it_appends_the_export_of_the_data_directory(
        self, env_file: Path, data_directory: Path, hook: Hook
    ) -> None:
        code, out, err = hook.run('session-start', '{}')

        assert (code, out, err) == (0, '', '')
        assert shlex.split(env_file.read_text(encoding='utf-8')) == [
            'export',
            f'{SESSION_DATA_VARIABLE}={data_directory}',
        ]

    def test_it_appends_no_second_copy_of_a_line_already_there(
        self, env_file: Path, hook: Hook
    ) -> None:
        hook.run('session-start', '{}')
        once = env_file.read_text(encoding='utf-8')
        hook.run('session-start', '{}')

        assert env_file.read_text(encoding='utf-8') == once


class TestSubagentRecorder:
    @pytest.fixture(params=SCOUTS)
    def scout(self, request: pytest.FixtureRequest) -> str:
        return request.param

    @pytest.fixture
    def renames(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
        done: list[tuple[str, str]] = []
        replace = Path.replace

        def recording_replace(source: Path, target: Path) -> Path:
            done.append((source.name, Path(target).name))
            return replace(source, target)

        monkeypatch.setattr(Path, 'replace', recording_replace)
        return done

    @pytest.fixture
    def recorded(self, scout: str, hook: Hook, spool: Path) -> tuple[int, Path]:
        code, _, _ = hook.run('subagent-record', scout_stop(scout))
        return code, spool

    def test_a_scout_report_leaves_one_file_named_by_the_prefix_of_the_key(
        self, recorded: tuple[int, Path], repository_workspace: Workspace
    ) -> None:
        code, spool = recorded
        prefix = spool_file_prefix(repository_key_of(repository_workspace))
        (file,) = spool.iterdir()

        assert code == 0
        assert file.name.startswith(prefix)
        assert file.suffix == '.json'
        assert len(file.name) > len(prefix) + len('.json')

    def test_the_file_is_written_under_another_suffix_and_renamed(
        self, scout: str, hook: Hook, renames: list[tuple[str, str]]
    ) -> None:
        hook.run('subagent-record', scout_stop(scout))
        ((written, final),) = renames

        assert not written.endswith('.json')
        assert final.endswith('.json')
        assert Path(final).stem == Path(written).stem

    @pytest.mark.usefixtures('recorded')
    def test_the_server_takes_it_in_on_its_next_tool_call(
        self, state_server: StateServer, repository_database: Database, spool: Path
    ) -> None:
        (searched,) = state_server.call(SEARCH)
        with repository_database.transaction() as session:
            stored = session.execute(sql.select(ScoutReportRow.report, ScoutReportRow.target)).one()

        assert SimilarityKind.SCOUT_REPORT in text_of(searched)
        assert stored.report == REPORT
        assert stored.target.endswith('a1b2')
        assert list(spool.iterdir()) == []

    @pytest.mark.parametrize('agent_type', OTHER_AGENTS)
    def test_another_agent_type_writes_nothing(
        self, agent_type: str, hook: Hook, spool: Path
    ) -> None:
        code, out, err = hook.run('subagent-record', scout_stop(agent_type))

        assert (code, out, err) == (0, '', '')
        assert not spool.exists()

    @pytest.mark.parametrize('text', UNREADABLE_INPUTS)
    def test_input_it_cannot_read_writes_nothing_and_says_why(
        self, text: str, hook: Hook, spool: Path
    ) -> None:
        code, out, err = hook.run('subagent-record', text)

        assert (code, out) == (0, '')
        assert err.startswith(f'{SKIPPED}the hook input is not a JSON object')
        assert not spool.exists()

    @pytest.mark.parametrize('message', [None, '', '   '])
    def test_a_stop_with_no_final_message_writes_nothing_and_says_why(
        self, message: str | None, hook: Hook, spool: Path
    ) -> None:
        text = hook_input('SubagentStop', SCOUTS[0], last_assistant_message=message)

        code, _, err = hook.run('subagent-record', text)

        assert code == 0
        assert 'no report to keep' in err
        assert not spool.exists()

    def test_a_report_the_server_could_not_take_in_is_not_written(
        self, hook: Hook, spool: Path
    ) -> None:
        text = scout_stop(last_assistant_message='x' * SPOOL_FILE_BYTES)

        code, _, err = hook.run('subagent-record', text)

        assert code == 0
        assert str(SPOOL_FILE_BYTES) in err
        assert not spool.exists()


def scout_handback(agent_type: str = 'mightymodels:code-scout', **given: object) -> str:
    handback = {
        'agent_id': 'a1b2',
        'tool_name': 'SubagentHandback',
        'tool_input': {'message': REPORT},
    }
    return hook_input('PostToolUse', agent_type, **(handback | given))


class TestSubagentHandback:
    @pytest.fixture(params=SCOUTS)
    def scout(self, request: pytest.FixtureRequest) -> str:
        return request.param

    def test_the_hook_is_matched_on_the_tool_and_runs_the_subcommand(self) -> None:
        (registered,) = [
            (matcher, command.split()[-1])
            for event, matcher, command in hooks_registered()
            if event == 'PostToolUse'
        ]

        assert registered == ('SubagentHandback', 'subagent-handback')

    def test_the_message_is_left_as_one_file_and_nothing_is_said(
        self, scout: str, hook: Hook, spool: Path
    ) -> None:
        code, out, err = hook.run('subagent-handback', scout_handback(scout))
        (file,) = spool.iterdir()
        content = json.loads(file.read_text(encoding='utf-8'))

        assert (code, out, err) == (0, '', '')
        assert file.suffix == '.json'
        assert (content['report'], content['target']) == (REPORT, f'{scout.split(":")[1]} a1b2')

    @pytest.mark.usefixtures('in_the_repository')
    def test_the_server_stores_the_handed_back_report_and_not_the_closing_text(
        self,
        scout: str,
        hook: Hook,
        state_server: StateServer,
        repository_database: Database,
        spool: Path,
    ) -> None:
        hook.run('subagent-handback', scout_handback(scout))
        hook.run('subagent-record', scout_stop(scout, last_assistant_message='Done.'))

        state_server.call(SEARCH)
        with repository_database.transaction() as session:
            (stored,) = session.scalars(sql.select(ScoutReportRow.report))

        assert stored == REPORT
        assert list(spool.iterdir()) == []

    @pytest.mark.parametrize('agent_type', OTHER_AGENTS)
    def test_another_agent_type_writes_nothing(
        self, agent_type: str, hook: Hook, spool: Path
    ) -> None:
        code, out, err = hook.run('subagent-handback', scout_handback(agent_type))

        assert (code, out, err) == (0, '', '')
        assert not spool.exists()

    @pytest.mark.parametrize(
        'tool_input',
        [
            pytest.param({}, id='no-message'),
            pytest.param({'message': None}, id='null'),
            pytest.param({'message': ''}, id='empty'),
            pytest.param({'message': '  \n'}, id='blank'),
            pytest.param({'message': 7}, id='number'),
            pytest.param({'message': ['report']}, id='list'),
            pytest.param('report', id='tool-input-is-text'),
            pytest.param(None, id='tool-input-is-null'),
        ],
    )
    def test_a_message_that_is_missing_blank_or_not_text_writes_nothing_and_says_why(
        self, tool_input: object, hook: Hook, spool: Path
    ) -> None:
        code, out, err = hook.run('subagent-handback', scout_handback(tool_input=tool_input))

        assert (code, out) == (0, '')
        assert 'no report to keep' in err
        assert not spool.exists()

    @pytest.mark.parametrize('text', UNREADABLE_INPUTS)
    def test_input_it_cannot_read_writes_nothing_and_says_why(
        self, text: str, hook: Hook, spool: Path
    ) -> None:
        code, out, err = hook.run('subagent-handback', text)

        assert (code, out) == (0, '')
        assert err.startswith(f'{SKIPPED}the hook input is not a JSON object')
        assert not spool.exists()

    def test_a_message_too_long_for_the_server_is_not_written(
        self, hook: Hook, spool: Path
    ) -> None:
        text = scout_handback(tool_input={'message': 'x' * SPOOL_FILE_BYTES})

        code, out, err = hook.run('subagent-handback', text)

        assert (code, out) == (0, '')
        assert str(SPOOL_FILE_BYTES) in err
        assert not spool.exists()

    @pytest.mark.parametrize(
        'shape', ['a\n"', '\U0001f600'], ids=['newlines-and-quotes', 'four-byte-characters']
    )
    def test_a_message_of_the_report_limit_is_written_whatever_its_characters(
        self, shape: str, hook: Hook, spool: Path
    ) -> None:
        message = (shape * REPORT_LIMIT)[:REPORT_LIMIT]

        code, _, err = hook.run(
            'subagent-handback', scout_handback(tool_input={'message': message})
        )
        (file,) = spool.iterdir()

        assert (code, err) == (0, '')
        assert json.loads(file.read_text(encoding='utf-8'))['report'] == message


class TestTheStateOfATicket:
    @pytest.fixture
    def on_the_branch(
        self,
        in_the_repository: Path,
        ticket_service: TicketService,
        git: Callable[..., str],
    ) -> Slug:
        git(in_the_repository, 'symbolic-ref', 'HEAD', f'refs/heads/{BRANCH}')
        ticket_service.write(TICKET, ANSWERS)
        ticket_service.validate(TICKET)
        return TICKET

    @pytest.fixture
    def engineer_on_t1(self, on_the_branch: Slug, task_service: TaskService) -> None:
        task_service.start(
            on_the_branch, 'T1', TaskStart(by=Implementer.ENGINEER, owned=('src/queue.py',))
        )

    @pytest.fixture
    def brief(self, repository_workspace: Workspace) -> Path:
        return repository_workspace.task_brief(TICKET, 1)

    def write_brief(self, brief: Path, text: str) -> None:
        brief.parent.mkdir(parents=True, exist_ok=True)
        brief.write_text(text, encoding='utf-8')


@pytest.mark.usefixtures('engineer_on_t1')
class TestCompletionGate(TestTheStateOfATicket):
    def test_without_a_brief_it_blocks_naming_the_task_and_the_missing_brief(
        self, hook: Hook
    ) -> None:
        code, out, err = hook.run('completion-gate', implementer_stop())
        decision = json.loads(out)

        assert (code, err) == (0, '')
        assert decision['decision'] == 'block'
        assert 'T1' in decision['reason']
        assert 'task-01.md is missing' in decision['reason']

    def test_with_a_done_half_naming_no_commit_it_blocks_naming_what_is_missing(
        self, hook: Hook, brief: Path
    ) -> None:
        self.write_brief(brief, DONE_WITHOUT_A_COMMIT)

        _, out, _ = hook.run('completion-gate', implementer_stop())
        reason = json.loads(out)['reason']

        assert 'T1' in reason
        assert 'has no DONE half naming a commit' in reason

    def test_a_second_stop_after_the_block_is_let_through(self, hook: Hook) -> None:
        first = hook.run('completion-gate', implementer_stop())
        second = hook.run('completion-gate', implementer_stop(stop_hook_active=True))

        assert json.loads(first[1])['decision'] == 'block'
        assert second == (0, '', '')

    def test_with_a_done_half_naming_a_commit_it_lets_the_stop_through(
        self, hook: Hook, brief: Path
    ) -> None:
        self.write_brief(brief, DONE_WITH_A_COMMIT)

        assert hook.run('completion-gate', implementer_stop()) == (0, '', '')

    def test_a_worker_that_started_nothing_is_let_through(self, hook: Hook) -> None:
        assert hook.run('completion-gate', implementer_stop('mightymodels:architect')) == (
            0,
            '',
            '',
        )

    @pytest.mark.parametrize('agent_type', OTHER_AGENTS)
    def test_another_agent_type_is_let_through(self, agent_type: str, hook: Hook) -> None:
        assert hook.run('completion-gate', implementer_stop(agent_type)) == (0, '', '')

    @pytest.mark.parametrize('text', UNREADABLE_INPUTS)
    def test_unreadable_input_is_let_through_and_says_why(self, text: str, hook: Hook) -> None:
        code, out, err = hook.run('completion-gate', text)

        assert (code, out) == (0, '')
        assert err.startswith(SKIPPED)

    def test_off_the_ticket_branch_it_does_nothing(
        self, hook: Hook, git: Callable[..., str]
    ) -> None:
        git(hook.repository, 'symbolic-ref', 'HEAD', 'refs/heads/elsewhere')

        assert hook.run('completion-gate', implementer_stop()) == (0, '', '')


def snapshot_files(repository: Path) -> list[str]:
    handoffs = repository.joinpath('.mightymodels', SLUG, 'handoffs')
    return sorted(path.name for path in handoffs.glob('*')) if handoffs.exists() else []


@pytest.mark.usefixtures('on_the_branch')
class TestPreCompactSnapshot(TestTheStateOfATicket):
    @pytest.mark.parametrize('trigger', ['manual', 'auto'])
    def test_it_writes_the_snapshot_of_the_ticket_on_the_checked_out_branch(
        self, trigger: str, hook: Hook
    ) -> None:
        code, out, err = hook.run('pre-compact', hook_input('PreCompact', trigger=trigger))
        record = json.loads(
            hook.repository.joinpath('.mightymodels', SLUG, 'handoffs', 'snapshot.json').read_text(
                encoding='utf-8'
            )
        )

        assert (code, out, err) == (0, '', '')
        assert snapshot_files(hook.repository) == ['snapshot.json', 'snapshot.md']
        assert record['slug'] == SLUG
        assert record['repository']['branch'] == BRANCH

    def test_on_another_branch_it_writes_nothing(self, hook: Hook, git: Callable[..., str]) -> None:
        git(hook.repository, 'symbolic-ref', 'HEAD', 'refs/heads/elsewhere')

        assert hook.run('pre-compact', hook_input('PreCompact')) == (0, '', '')
        assert snapshot_files(hook.repository) == []

    def test_with_a_detached_head_it_writes_nothing(
        self, hook: Hook, git: Callable[..., str]
    ) -> None:
        git(
            hook.repository,
            '-c',
            'user.name=t',
            '-c',
            'user.email=t@example.com',
            'commit',
            '--allow-empty',
            '-q',
            '-m',
            'base',
        )
        git(hook.repository, 'checkout', '-q', '--detach')

        assert hook.run('pre-compact', hook_input('PreCompact')) == (0, '', '')
        assert snapshot_files(hook.repository) == []

    def test_with_two_tickets_on_the_branch_it_writes_nothing(
        self, hook: Hook, ticket_service: TicketService
    ) -> None:
        other = Slug(OTHER_SLUG)
        ticket_service.write(other, ANSWERS)
        ticket_service.validate(other)

        assert hook.run('pre-compact', hook_input('PreCompact')) == (0, '', '')
        assert snapshot_files(hook.repository) == []
        assert not hook.repository.joinpath('.mightymodels', OTHER_SLUG, 'handoffs').exists()


def database_with_another_schema_version(data_directory: Path) -> None:
    data_directory.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(data_directory.joinpath(DATABASE_NAME))) as connection:
        connection.execute('CREATE TABLE other (x INTEGER)')
        connection.execute('PRAGMA user_version = 99')


INPUTS = MappingProxyType(
    {
        'session-start': '{}',
        'subagent-record': scout_stop(),
        'completion-gate': implementer_stop(),
        'pre-compact': hook_input('PreCompact'),
    }
)


class TestWhenAHookCannotWork:
    @pytest.fixture
    def without_a_data_directory(
        self, in_the_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Path:
        monkeypatch.delenv(PLUGIN_DATA_VARIABLE)
        monkeypatch.setenv(ENV_FILE_VARIABLE, str(tmp_path.joinpath('session-env.sh')))
        return in_the_repository

    @pytest.fixture
    def outside_a_repository(
        self, in_the_repository: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Path:
        outside = in_the_repository.parent.joinpath('outside')
        outside.mkdir()
        monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(outside))
        return outside

    @pytest.fixture
    def with_a_refused_database(self, data_directory: Path) -> Path:
        database_with_another_schema_version(data_directory)
        return data_directory.joinpath(DATABASE_NAME)

    @pytest.mark.usefixtures('without_a_data_directory')
    @pytest.mark.parametrize('command', INPUTS)
    def test_without_a_data_directory_it_exits_0_blocking_nothing_and_says_why(
        self, command: str, hook: Hook
    ) -> None:
        code, out, err = hook.run(command, INPUTS[command])

        assert (code, out) == (0, '')
        assert err.startswith(f'{SKIPPED}{PLUGIN_DATA_VARIABLE} is not set')

    @pytest.mark.usefixtures('outside_a_repository')
    @pytest.mark.parametrize('command', ['subagent-record', 'completion-gate', 'pre-compact'])
    def test_outside_a_git_repository_it_exits_0_blocking_nothing_and_says_why(
        self, command: str, hook: Hook, data_directory: Path
    ) -> None:
        code, out, err = hook.run(command, INPUTS[command])

        assert (code, out) == (0, '')
        assert 'is not inside a git repository' in err
        assert not data_directory.joinpath(SPOOL_DIRECTORY).exists()

    @pytest.mark.usefixtures('with_a_refused_database')
    @pytest.mark.parametrize('command', ['completion-gate', 'pre-compact'])
    def test_with_a_refused_database_it_exits_0_blocking_nothing_and_says_why(
        self, command: str, hook: Hook
    ) -> None:
        code, out, err = hook.run(command, INPUTS[command])

        assert (code, out) == (0, '')
        assert 'schema version 99' in err


WRAPPER = BIN.joinpath('mightymodels-hook')
LAUNCHER_VARIABLE = 'MIGHTYMODELS_HOOK_LAUNCHER'
FAILING_LAUNCHERS = MappingProxyType(
    {
        'exit-1': 'exit 1',
        'exit-2': 'echo partial; echo rejected >&2; exit 2',
        'killed': 'kill -9 $$',
    }
)


@dataclass(slots=True, kw_only=True, frozen=True)
class WrapperOutcome:
    code: int
    stdout: str
    stderr: str


async def spawn_wrapper(launcher: Path, *arguments: str) -> WrapperOutcome:
    process = await asyncio.create_subprocess_exec(
        WRAPPER,
        *arguments,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, LAUNCHER_VARIABLE: str(launcher)},
    )
    stdout, stderr = await process.communicate()
    return WrapperOutcome(
        code=process.returncode or 0, stdout=stdout.decode(), stderr=stderr.decode()
    )


class TestHookWrapper:
    @pytest.fixture(params=FAILING_LAUNCHERS)
    def failing_launcher(self, request: pytest.FixtureRequest, tmp_path: Path) -> Path:
        return self.launcher(tmp_path, FAILING_LAUNCHERS[request.param])

    @pytest.fixture
    def echoing_launcher(self, tmp_path: Path) -> Path:
        return self.launcher(tmp_path, 'echo "ran $*"')

    def launcher(self, directory: Path, body: str) -> Path:
        file = directory.joinpath('launcher')
        file.write_text(f'#!/bin/sh\n{body}\n', encoding='utf-8')
        file.chmod(0o755)
        return file

    def test_is_an_executable_posix_sh_script(self) -> None:
        assert os.access(WRAPPER, os.X_OK)
        assert WRAPPER.read_text(encoding='utf-8').splitlines()[0] == '#!/bin/sh'

    def test_a_launcher_that_fails_leaves_exit_0_and_no_output_and_says_which_hook(
        self, failing_launcher: Path
    ) -> None:
        outcome = asyncio.run(spawn_wrapper(failing_launcher, 'completion-gate'))

        assert (outcome.code, outcome.stdout) == (0, '')
        assert outcome.stderr.endswith('completion-gate could not run\n')

    def test_a_launcher_that_succeeds_has_its_output_and_arguments_passed_through(
        self, echoing_launcher: Path
    ) -> None:
        outcome = asyncio.run(spawn_wrapper(echoing_launcher, 'pre-compact'))

        assert outcome == WrapperOutcome(code=0, stdout='ran pre-compact\n', stderr='')
