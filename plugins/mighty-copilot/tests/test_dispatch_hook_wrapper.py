"""The hook command is a sh wrapper that answers for the Python process behind it when that fails,
is killed or runs past its limit: it refuses one of this plugin's workers, refuses any other
caller's dispatch of an implementer where `.mightymodels` exists at the project directory, and
lets every other dispatch through."""

import json
import os
import re
from pathlib import Path

import pytest
from mightymodels.commands.tests.hook_wrappers import (
    CUT_OFF_SECONDS,
    HUNG,
    STATE_DIRECTORY,
    Outcome,
    Wrapped,
    WrapperScript,
    launcher_running,
)

WRAPPER = Path(__file__).parent.parent.joinpath('bin', 'mightymodels-dispatch-hook')
HOOKS = Path(__file__).parent.parent.joinpath('hooks', 'hooks.json')
LIMIT_VARIABLE = 'MIGHTYMODELS_DISPATCH_SECONDS'
DISPATCH = WrapperScript(
    path=WRAPPER, launcher_variable='MIGHTYMODELS_DISPATCH_LAUNCHER', limit_variable=LIMIT_VARIABLE
)
DEFAULT_LIMIT = re.compile(rf'\$\{{{LIMIT_VARIABLE}:-(?P<seconds>\d+)\}}')
WORKER_INPUT = (
    '{"agent_type": "mightymodels:workers:engineer", "tool_input": {"subagent_type": "x"}}'
)
MAIN_INPUT = '{"tool_name": "Agent", "tool_input": {"subagent_type": "x"}}'
COMPACT_WORKER_INPUT = '{"agent_type":"mightymodels:workers:engineer","tool_input":{}}'
PADDED_WORKER_INPUT = '{"agent_type" : "mightymodels:workers:engineer", "tool_input": {}}'
SPREAD_WORKER_INPUT = '{\n\t"agent_type"\t:\n\t"mightymodels:workers:engineer"\n}'
UNREADABLE_WORKER_INPUT = '{"agent_type": "mightymodels:workers:engineer"'
UNREADABLE_COMPACT_WORKER_INPUT = '{"agent_type":"mightymodels:workers:engineer"'
UNREADABLE_MAIN_INPUT = '{"tool_name": "Agent"'
OTHER_PLUGIN_INPUT = '{"agent_type": "other:engineer", "tool_input": {"subagent_type": "x"}}'
BARE_CALLER_INPUT = '{"agent_type": "engineer", "tool_input": {"subagent_type": "x"}}'
UNREADABLE_BARE_CALLER_INPUT = '{"agent_type": "engineer"'
PREFIX_IN_TARGET_INPUT = (
    '{"agent_type": "other:engineer", '
    '"tool_input": {"subagent_type": "mightymodels:review:qualitylens"}}'
)
PREFIX_IN_PROMPT_INPUT = (
    '{"tool_input": {"subagent_type": "x", "prompt": "ask mightymodels:workers:engineer"}}'
)
ENGINEER_INPUT = '{"tool_input": {"subagent_type": "mightymodels:workers:engineer"}}'
IMPLEMENTER_INPUTS = (
    pytest.param(ENGINEER_INPUT, id='engineer'),
    pytest.param('{"tool_input":{"subagent_type":"architect"}}', id='bare-architect-compact'),
    pytest.param(
        '{"agent_type": 7, "tool_input": {"subagent_type" : "mightymodels:workers:intern"}}',
        id='intern-padded-caller-a-number',
    ),
    pytest.param(
        '{"agent_type": "general-purpose", '
        '"tool_input": {"subagent_type": "mightymodels:workers:architect"}}',
        id='architect-by-a-built-in',
    ),
)
NO_IMPLEMENTER_INPUTS = (
    pytest.param(MAIN_INPUT, id='unknown-type'),
    pytest.param(
        '{"tool_input": {"subagent_type": "mightymodels:review:fact-checker"}}', id='fact-checker'
    ),
    pytest.param(
        '{"tool_input": {"subagent_type": "x", "prompt": "\\"subagent_type\\": \\"engineer\\""}}',
        id='implementer-only-in-prompt',
    ),
    pytest.param('{"tool_input": {"subagent_type": "engineers"}}', id='a-longer-name'),
)
DENIED_ON_FAILURE = 2
COULD_NOT_RUN = 'mightymodels: the dispatch hook could not run, so '
NOT_CHECKED = f'{COULD_NOT_RUN}this dispatch was not checked'
FAILURES = {
    'exit-1': 'exit 1',
    'exit-2': 'echo partial; echo rejected >&2; exit 2',
    'killed': 'kill -9 $$',
    'missing': None,
}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path.joinpath('project')
    directory.mkdir()
    return directory


@pytest.fixture
def project_with_state(project: Path) -> Path:
    project.joinpath(STATE_DIRECTORY).mkdir()
    return project


@pytest.fixture(params=FAILURES, ids=list(FAILURES))
def failing(request: pytest.FixtureRequest, tmp_path: Path, project_with_state: Path) -> Wrapped:
    return Wrapped(
        script=DISPATCH,
        launcher=launcher_running(tmp_path, FAILURES[request.param]),
        project=project_with_state,
    )


@pytest.fixture(
    params=[
        pytest.param(('exit 1', None), id='crashed'),
        pytest.param((HUNG, CUT_OFF_SECONDS), id='hung'),
    ]
)
def broken(request: pytest.FixtureRequest, tmp_path: Path, project: Path) -> Wrapped:
    body, limit = request.param
    return Wrapped(
        script=DISPATCH, launcher=launcher_running(tmp_path, body), project=project, limit=limit
    )


class TestWrapperFile:
    def test_is_an_executable_posix_sh_script(self) -> None:
        assert os.access(WRAPPER, os.X_OK)
        assert WRAPPER.read_text(encoding='utf-8').splitlines()[0] == '#!/bin/sh'

    def test_its_own_limit_is_under_the_timeout_of_its_entry_in_hooks_json(self) -> None:
        limit = DEFAULT_LIMIT.search(WRAPPER.read_text(encoding='utf-8'))
        entries = json.loads(HOOKS.read_text(encoding='utf-8'))['hooks']['PreToolUse']
        (entry,) = [
            entry
            for group in entries
            for entry in group['hooks']
            if f'/{WRAPPER.name}"' in entry['command']
        ]

        assert limit is not None
        assert 0 < int(limit['seconds']) < entry['timeout']


class TestFailingLauncher:
    @pytest.mark.parametrize(
        'text',
        [
            pytest.param(WORKER_INPUT, id='spaced'),
            pytest.param(COMPACT_WORKER_INPUT, id='compact'),
            pytest.param(PADDED_WORKER_INPUT, id='padded'),
            pytest.param(SPREAD_WORKER_INPUT, id='spread-over-lines'),
            pytest.param(UNREADABLE_WORKER_INPUT, id='unreadable-spaced'),
            pytest.param(UNREADABLE_COMPACT_WORKER_INPUT, id='unreadable-compact'),
        ],
    )
    def test_input_naming_a_plugin_worker_exits_2_and_says_the_dispatch_is_refused(
        self, failing: Wrapped, text: str
    ) -> None:
        outcome = failing.run(text)

        assert outcome.code == DENIED_ON_FAILURE
        assert outcome.stdout == ''
        assert outcome.last_line() == f'{COULD_NOT_RUN}this subagent dispatch is refused'

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
    def test_input_naming_no_plugin_worker_and_no_implementer_exits_0_saying_it_was_not_checked(
        self, failing: Wrapped, text: str
    ) -> None:
        outcome = failing.run(text)

        assert (outcome.code, outcome.stdout) == (0, '')
        assert outcome.last_line() == NOT_CHECKED

    def test_what_the_launcher_wrote_on_standard_error_is_passed_through(
        self, tmp_path: Path, project: Path
    ) -> None:
        wrapped = Wrapped(
            script=DISPATCH,
            launcher=launcher_running(tmp_path, FAILURES['exit-2']),
            project=project,
        )

        assert wrapped.run(MAIN_INPUT).stderr.splitlines() == ['rejected', NOT_CHECKED]


class TestImplementerTargetOfAnotherCaller:
    @pytest.mark.usefixtures('project_with_state')
    @pytest.mark.parametrize('text', IMPLEMENTER_INPUTS)
    def test_where_the_project_has_a_state_directory_it_exits_2_and_says_why(
        self, broken: Wrapped, text: str
    ) -> None:
        outcome = broken.run(text)

        assert outcome.code == DENIED_ON_FAILURE
        assert outcome.stdout == ''
        assert outcome.last_line().startswith(
            f'{COULD_NOT_RUN}it cannot tell whether a task is started and this dispatch of the '
        )
        assert outcome.last_line().endswith(' is refused')

    def test_where_the_project_has_no_state_directory_it_exits_0(self, broken: Wrapped) -> None:
        outcome = broken.run(ENGINEER_INPUT)

        assert (outcome.code, outcome.stdout) == (0, '')
        assert outcome.last_line() == NOT_CHECKED

    @pytest.mark.parametrize('text', NO_IMPLEMENTER_INPUTS)
    def test_a_target_that_is_no_implementer_exits_0_whatever_the_project_holds(
        self, failing: Wrapped, text: str
    ) -> None:
        outcome = failing.run(text)

        assert (outcome.code, outcome.stdout) == (0, '')
        assert outcome.last_line() == NOT_CHECKED


class TestHungLauncher:
    @pytest.fixture
    def hung(self, tmp_path: Path, project_with_state: Path) -> Wrapped:
        return Wrapped(
            script=DISPATCH,
            launcher=launcher_running(tmp_path, HUNG),
            project=project_with_state,
            limit=CUT_OFF_SECONDS,
        )

    def test_a_plugin_worker_is_refused_once_the_limit_has_passed(self, hung: Wrapped) -> None:
        assert hung.run(WORKER_INPUT).code == DENIED_ON_FAILURE

    def test_a_dispatch_that_is_no_implementers_goes_ahead_once_the_limit_has_passed(
        self, hung: Wrapped
    ) -> None:
        outcome = hung.run(MAIN_INPUT)

        assert (outcome.code, outcome.stdout) == (0, '')
        assert outcome.last_line() == NOT_CHECKED


class TestWorkingDirectoryAsTheProject:
    def test_without_the_project_variable_the_state_directory_is_looked_for_where_it_runs(
        self, tmp_path: Path, project_with_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project_with_state)
        wrapped = Wrapped(
            script=DISPATCH, launcher=launcher_running(tmp_path, 'exit 1'), project=None
        )

        assert wrapped.run(ENGINEER_INPUT).code == DENIED_ON_FAILURE


class TestSucceedingLauncher:
    @pytest.mark.parametrize('text', [WORKER_INPUT, MAIN_INPUT])
    def test_passes_the_launchers_stdout_through(
        self, tmp_path: Path, project: Path, text: str
    ) -> None:
        launcher = launcher_running(tmp_path, 'printf \'{"decision": "%s"}\\n\' "$1"')

        assert Wrapped(script=DISPATCH, launcher=launcher, project=project).run(text) == Outcome(
            code=0, stdout='{"decision": "dispatch-hook"}\n', stderr=''
        )

    def test_passes_the_launchers_stderr_through(self, tmp_path: Path, project: Path) -> None:
        launcher = launcher_running(tmp_path, 'echo "{}"; echo two tickets >&2')

        assert Wrapped(script=DISPATCH, launcher=launcher, project=project).run(
            MAIN_INPUT
        ) == Outcome(code=0, stdout='{}\n', stderr='two tickets\n')

    def test_keeps_the_hook_input_for_the_launcher(self, tmp_path: Path, project: Path) -> None:
        launcher = launcher_running(tmp_path, 'cat')

        assert Wrapped(script=DISPATCH, launcher=launcher, project=project).run(
            WORKER_INPUT
        ).stdout == (f'{WORKER_INPUT}\n')

    def test_prints_nothing_when_the_launcher_prints_nothing(
        self, tmp_path: Path, project: Path
    ) -> None:
        launcher = launcher_running(tmp_path, 'exit 0')

        assert Wrapped(script=DISPATCH, launcher=launcher, project=project).run(
            WORKER_INPUT
        ) == Outcome(code=0, stdout='', stderr='')
