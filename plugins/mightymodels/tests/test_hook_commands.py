"""The hook commands the plugin registers: what hooks.json runs, and what each one does.

A hook command runs `main` with the hook's JSON on standard input and the variables Claude Code
sets for a hook. Each exits 0 whatever happens, since a hook that exits 2 can keep a subagent
from stopping or a compaction from running; only the completion gate answers a block, on
standard output.
"""

import asyncio
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pytest
import sqlalchemy as sql
from mightymodels_plugin.cli import build_parser
from mightymodels_plugin.commands.session_start import ENV_FILE_VARIABLE
from mightymodels_plugin.commands.tests.hook_inputs import (
    OTHER_AGENTS,
    REPORT,
    SKIPPED,
    UNREADABLE_INPUTS,
    Hook,
    hook_input,
    scout_stop,
)
from mightymodels_plugin.core.data_directory import PLUGIN_DATA_VARIABLE, SESSION_DATA_VARIABLE
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.declarative import REPORT_LIMIT
from mightymodels_plugin.core.repository_key import spool_file_prefix
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.similarity.schema import SimilarityKind
from mightymodels_plugin.tools.similarity.spool import SPOOL_DIRECTORY, SPOOL_FILE_BYTES
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow
from mightymodels_plugin.tools.tests.support import (
    StateServer,
    ToolCall,
    repository_key_of,
    text_of,
)

PLUGIN = Path(__file__).parent.parent
HOOKS = PLUGIN.joinpath('hooks', 'hooks.json')
BIN = PLUGIN.joinpath('bin')
PLUGIN_ROOT = '${CLAUDE_PLUGIN_ROOT}'
SUBCOMMANDS_OF_WRAPPERS_WITHOUT_ARGUMENTS = MappingProxyType(
    {'mightymodels-dispatch-hook': 'dispatch-hook'}
)

SEARCH: ToolCall = (
    'similarity',
    {'request': {'action': 'search', 'query': 'the drain loop sleeps'}},
)
SCOUTS = ('mightymodels:code-scout', 'mightymodels:web-scout')
IMPLEMENTERS = ('mightymodels:engineer', 'mightymodels:architect')


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
