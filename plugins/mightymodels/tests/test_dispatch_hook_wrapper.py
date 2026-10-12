"""The hook command is a sh wrapper that denies one of this plugin's workers, and no other caller,
when the Python process behind it fails."""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

WRAPPER = Path(__file__).parent.parent.joinpath('bin', 'mightymodels-dispatch-hook')
LAUNCHER_VARIABLE = 'MIGHTYMODELS_DISPATCH_LAUNCHER'
WORKER_INPUT = (
    '{"agent_type": "mightymodels:workers:engineer", "tool_input": {"subagent_type": "x"}}'
)
MAIN_INPUT = '{"tool_name": "Agent", "tool_input": {"subagent_type": "x"}}'
COMPACT_WORKER_INPUT = '{"agent_type":"mightymodels:workers:engineer","tool_input":{}}'
UNREADABLE_WORKER_INPUT = '{"agent_type": "mightymodels:workers:engineer"'
UNREADABLE_COMPACT_WORKER_INPUT = '{"agent_type":"mightymodels:workers:engineer"'
UNREADABLE_MAIN_INPUT = '{"tool_name": "Agent"'
OTHER_PLUGIN_INPUT = '{"agent_type": "other:engineer", "tool_input": {"subagent_type": "x"}}'
BARE_CALLER_INPUT = '{"agent_type": "engineer", "tool_input": {"subagent_type": "x"}}'
UNREADABLE_BARE_CALLER_INPUT = '{"agent_type": "engineer"'
PREFIX_IN_TARGET_INPUT = (
    '{"agent_type": "other:engineer", '
    '"tool_input": {"subagent_type": "mightymodels:workers:engineer"}}'
)
PREFIX_IN_PROMPT_INPUT = (
    '{"tool_input": {"subagent_type": "x", "prompt": "ask mightymodels:workers:engineer"}}'
)
DENIED_ON_FAILURE = 2
FAILURES = {
    'exit-1': 'exit 1',
    'exit-2': 'echo partial; echo rejected >&2; exit 2',
    'killed': 'kill -9 $$',
    'missing': None,
}


@dataclass(slots=True, kw_only=True, frozen=True)
class Outcome:
    code: int
    stdout: str
    stderr: str


async def spawn_wrapper(launcher: Path, text: str) -> Outcome:
    process = await asyncio.create_subprocess_exec(
        WRAPPER,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, LAUNCHER_VARIABLE: str(launcher)},
    )
    stdout, stderr = await process.communicate(text.encode())
    return Outcome(code=process.returncode or 0, stdout=stdout.decode(), stderr=stderr.decode())


def run_wrapper(launcher: Path, text: str) -> Outcome:
    return asyncio.run(spawn_wrapper(launcher, text))


def launcher_running(directory: Path, body: str | None) -> Path:
    launcher = directory.joinpath('launcher')
    if body is not None:
        launcher.write_text(f'#!/bin/sh\n{body}\n', encoding='utf-8')
        launcher.chmod(0o755)
    return launcher


@pytest.fixture(params=FAILURES, ids=list(FAILURES))
def failing_launcher(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    return launcher_running(tmp_path, FAILURES[request.param])


class TestWrapperFile:
    def test_is_an_executable_posix_sh_script(self) -> None:
        assert os.access(WRAPPER, os.X_OK)
        assert WRAPPER.read_text(encoding='utf-8').splitlines()[0] == '#!/bin/sh'


class TestFailingLauncher:
    @pytest.mark.parametrize(
        'text',
        [
            pytest.param(WORKER_INPUT, id='spaced'),
            pytest.param(COMPACT_WORKER_INPUT, id='compact'),
            pytest.param(UNREADABLE_WORKER_INPUT, id='unreadable-spaced'),
            pytest.param(UNREADABLE_COMPACT_WORKER_INPUT, id='unreadable-compact'),
        ],
    )
    def test_input_naming_a_plugin_worker_exits_2_with_one_line_on_stderr(
        self, failing_launcher: Path, text: str
    ) -> None:
        outcome = run_wrapper(failing_launcher, text)

        assert outcome.code == DENIED_ON_FAILURE
        assert outcome.stdout == ''
        assert len(outcome.stderr.splitlines()) == 1
        assert 'dispatch hook could not run' in outcome.stderr

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param(MAIN_INPUT, id='no-agent-type'),
            pytest.param(UNREADABLE_MAIN_INPUT, id='unreadable-no-agent-type'),
            pytest.param('', id='empty'),
            pytest.param(OTHER_PLUGIN_INPUT, id='other-plugin'),
            pytest.param(BARE_CALLER_INPUT, id='bare-caller'),
            pytest.param(UNREADABLE_BARE_CALLER_INPUT, id='unreadable-bare-caller'),
            pytest.param(PREFIX_IN_TARGET_INPUT, id='prefix-only-in-target'),
            pytest.param(PREFIX_IN_PROMPT_INPUT, id='prefix-only-in-prompt'),
        ],
    )
    def test_input_naming_no_plugin_worker_exits_0_and_prints_nothing(
        self, failing_launcher: Path, text: str
    ) -> None:
        assert run_wrapper(failing_launcher, text) == Outcome(code=0, stdout='', stderr='')


class TestSucceedingLauncher:
    @pytest.mark.parametrize('text', [WORKER_INPUT, MAIN_INPUT])
    def test_passes_the_launchers_stdout_through(self, tmp_path: Path, text: str) -> None:
        launcher = launcher_running(tmp_path, 'printf \'{"decision": "%s"}\\n\' "$1"')

        assert run_wrapper(launcher, text) == Outcome(
            code=0, stdout='{"decision": "dispatch-hook"}\n', stderr=''
        )

    def test_keeps_the_hook_input_for_the_launcher(self, tmp_path: Path) -> None:
        launcher = launcher_running(tmp_path, 'cat')

        assert run_wrapper(launcher, WORKER_INPUT).stdout == f'{WORKER_INPUT}\n'

    def test_prints_nothing_when_the_launcher_prints_nothing(self, tmp_path: Path) -> None:
        launcher = launcher_running(tmp_path, 'exit 0')

        assert run_wrapper(launcher, WORKER_INPUT) == Outcome(code=0, stdout='', stderr='')
