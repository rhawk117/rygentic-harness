"""The main-thread hook command is a sh wrapper that answers for the Python process behind it when
that fails, is killed or runs past its limit. Where `.mightymodels` exists at the project
directory it lets an edit by a caller that is no plugin worker go ahead with one line saying it
was not checked, and refuses that caller's Bash command when `git` and then `push` follow the
command's opening quote. It lets every other call through in silence."""

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

WRAPPER = Path(__file__).parent.parent.joinpath('bin', 'mightymodels-main-thread-hook')
HOOKS = Path(__file__).parent.parent.joinpath('hooks', 'hooks.json')
LIMIT_VARIABLE = 'MIGHTYMODELS_MAIN_THREAD_SECONDS'
MAIN_THREAD = WrapperScript(
    path=WRAPPER,
    launcher_variable='MIGHTYMODELS_MAIN_THREAD_LAUNCHER',
    limit_variable=LIMIT_VARIABLE,
)
DEFAULT_LIMIT = re.compile(rf'\$\{{{LIMIT_VARIABLE}:-(?P<seconds>\d+)\}}')
DENIED_ON_FAILURE = 2
COULD_NOT_RUN = 'mightymodels: the main-thread hook could not run, so '
PUSH_REFUSED = (
    f'{COULD_NOT_RUN}it cannot tell whether the landing is proven and this push is refused'
)
EDIT_NOT_CHECKED = f'{COULD_NOT_RUN}this edit was not checked against an unclosed ticket'
SILENT = Outcome(code=0, stdout='', stderr='')
PUSH = '{"tool_name": "Bash", "tool_input": {"command": "git push"}}'
EDIT = '{"tool_name": "Edit", "tool_input": {"file_path": "/work/src/queue.py"}}'
PUSHES = (
    pytest.param(PUSH, id='plain'),
    pytest.param('{"tool_name":"Bash","tool_input":{"command":"git push"}}', id='compact'),
    pytest.param(
        '{\n\t"tool_name"\t:\n\t"Bash",\n"tool_input": {"command": "git push"}}', id='spread'
    ),
    pytest.param(
        '{"tool_name": "Bash", "tool_input": {"command": "git -C ../checkout push"}}',
        id='another-directory',
    ),
    pytest.param(
        '{"tool_name": "Bash", "tool_input": {"command": "uv run pytest && git push origin"}}',
        id='chained',
    ),
    pytest.param(
        '{"tool_name": "Bash", "tool_input": {"command": "cd x\\ngit push"}}',
        id='after-an-escaped-newline',
    ),
    pytest.param(
        '{"tool_input": {"description": "land", "command": "git push"}, "tool_name": "Bash"}',
        id='tool-name-last',
    ),
    pytest.param(
        '{"agent_type": "general-purpose", "tool_name": "Bash", '
        '"tool_input": {"command": "git push"}}',
        id='by-a-built-in',
    ),
    pytest.param(
        '{"agent_type": 7, "tool_name": "Bash", "tool_input": {"command": "git push"}}',
        id='caller-a-number',
    ),
    pytest.param(
        '{"tool_name": "Bash", "tool_input": {"command": "echo \\"git push\\""}}',
        id='the-text-of-a-push',
    ),
    pytest.param('{"tool_name": "Bash", "tool_input": {"command": "git push"', id='unreadable'),
)
EDITS = (
    pytest.param(EDIT, id='edit'),
    pytest.param('{"tool_name":"Write","tool_input":{"file_path":"/work/a.py"}}', id='write'),
    pytest.param(
        '{"tool_name": "Edit", "tool_input": {"file_path": "/work/a.md", '
        '"new_string": "\\"tool_name\\": \\"Bash\\", \\"command\\": \\"git push\\""}}',
        id='an-edit-whose-text-holds-a-bash-push',
    ),
    pytest.param(
        '{"agent_type": "other:engineer", "tool_name": "Write", '
        '"tool_input": {"file_path": "/work/a.py"}}',
        id='by-another-plugins-agent',
    ),
    pytest.param('{"tool_name": "Edit"', id='unreadable'),
)
LET_THROUGH = (
    pytest.param(
        '{"tool_name": "Bash", "tool_input": {"command": "uv run pytest"}}', id='bash-with-no-push'
    ),
    pytest.param('{"tool_name": "Bash", "tool_input": {"command": "git status"}}', id='git-alone'),
    pytest.param('{"tool_name": "Bash", "tool_input": {"command": "pushd src"}}', id='push-alone'),
    pytest.param(
        '{"agent_type": "mightymodels:workers:engineer", "tool_name": "Bash", '
        '"tool_input": {"command": "git push"}}',
        id='a-plugin-workers-push',
    ),
    pytest.param(
        '{"agent_type":"mightymodels:workers:engineer","tool_name":"Edit",'
        '"tool_input":{"file_path":"/work/a.py"}}',
        id='a-plugin-workers-edit',
    ),
    pytest.param(
        '{"agent_type" : "mightymodels:triage:code-scout", "tool_name": "Write", '
        '"tool_input": {"file_path": "/work/a.py"}}',
        id='a-plugin-workers-write',
    ),
    pytest.param('{"tool_name": "Read", "tool_input": {"file_path": "/work/a.py"}}', id='a-read'),
    pytest.param(
        '{"tool_name": "Agent", "tool_input": {"prompt": "then git push"}}', id='a-dispatch'
    ),
    pytest.param('', id='empty'),
)
FAILURES = {
    'exit-1': 'exit 1',
    'exit-2': 'echo partial; exit 2',
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
        script=MAIN_THREAD,
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
        script=MAIN_THREAD, launcher=launcher_running(tmp_path, body), project=project, limit=limit
    )


class TestWrapperFile:
    def test_is_an_executable_posix_sh_script(self) -> None:
        assert os.access(WRAPPER, os.X_OK)
        assert WRAPPER.read_text(encoding='utf-8').splitlines()[0] == '#!/bin/sh'

    def test_its_own_limit_is_under_the_timeout_of_its_entry_in_hooks_json(self) -> None:
        limit = DEFAULT_LIMIT.search(WRAPPER.read_text(encoding='utf-8'))
        groups = json.loads(HOOKS.read_text(encoding='utf-8'))['hooks']['PreToolUse']
        (group,) = [
            group
            for group in groups
            if any(f'/{WRAPPER.name}"' in entry['command'] for entry in group['hooks'])
        ]
        (entry,) = group['hooks']

        assert group['matcher'] == 'Edit|Write|Bash'
        assert limit is not None
        assert 0 < int(limit['seconds']) < entry['timeout']


class TestFailingLauncher:
    @pytest.mark.parametrize('text', PUSHES)
    def test_a_bash_command_with_git_and_then_push_exits_2_and_says_the_push_is_refused(
        self, failing: Wrapped, text: str
    ) -> None:
        outcome = failing.run(text)

        assert (outcome.code, outcome.stdout) == (DENIED_ON_FAILURE, '')
        assert outcome.last_line() == PUSH_REFUSED

    @pytest.mark.parametrize('text', EDITS)
    def test_an_edit_exits_0_with_one_line_for_the_user_saying_it_was_not_checked(
        self, failing: Wrapped, text: str
    ) -> None:
        outcome = failing.run(text)

        assert outcome.code == 0
        assert outcome.stdout.count('\n') == 1
        assert json.loads(outcome.stdout) == {'systemMessage': EDIT_NOT_CHECKED}

    @pytest.mark.parametrize('text', LET_THROUGH)
    def test_any_other_call_exits_0_and_prints_nothing(self, failing: Wrapped, text: str) -> None:
        outcome = failing.run(text)

        assert (outcome.code, outcome.stdout) == (0, '')

    def test_what_the_launcher_wrote_on_standard_error_is_passed_through(
        self, tmp_path: Path, project_with_state: Path
    ) -> None:
        wrapped = Wrapped(
            script=MAIN_THREAD,
            launcher=launcher_running(tmp_path, 'echo rejected >&2; exit 2'),
            project=project_with_state,
        )

        assert wrapped.run(PUSH).stderr.splitlines() == ['rejected', PUSH_REFUSED]


class TestProjectWithNoStateDirectory:
    @pytest.mark.parametrize('text', [pytest.param(PUSH, id='push'), pytest.param(EDIT, id='edit')])
    def test_a_push_and_an_edit_exit_0_and_print_nothing(self, broken: Wrapped, text: str) -> None:
        outcome = broken.run(text)

        assert (outcome.code, outcome.stdout) == (0, '')
        assert COULD_NOT_RUN not in outcome.stderr


class TestHungLauncher:
    @pytest.fixture
    def hung(self, tmp_path: Path, project_with_state: Path) -> Wrapped:
        return Wrapped(
            script=MAIN_THREAD,
            launcher=launcher_running(tmp_path, HUNG),
            project=project_with_state,
            limit=CUT_OFF_SECONDS,
        )

    def test_a_push_is_refused_once_the_limit_has_passed(self, hung: Wrapped) -> None:
        outcome = hung.run(PUSH)

        assert (outcome.code, outcome.stdout) == (DENIED_ON_FAILURE, '')
        assert outcome.last_line() == PUSH_REFUSED

    def test_an_edit_goes_ahead_once_the_limit_has_passed(self, hung: Wrapped) -> None:
        outcome = hung.run(EDIT)

        assert outcome.code == 0
        assert json.loads(outcome.stdout) == {'systemMessage': EDIT_NOT_CHECKED}

    def test_a_bash_command_with_no_push_goes_ahead_once_the_limit_has_passed(
        self, hung: Wrapped
    ) -> None:
        outcome = hung.run('{"tool_name": "Bash", "tool_input": {"command": "uv run pytest"}}')

        assert (outcome.code, outcome.stdout) == (0, '')


class TestWorkingDirectoryAsTheProject:
    def test_without_the_project_variable_the_state_directory_is_looked_for_where_it_runs(
        self, tmp_path: Path, project_with_state: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project_with_state)
        wrapped = Wrapped(
            script=MAIN_THREAD, launcher=launcher_running(tmp_path, 'exit 1'), project=None
        )

        assert wrapped.run(PUSH).code == DENIED_ON_FAILURE


class TestSucceedingLauncher:
    @pytest.mark.parametrize('text', [pytest.param(PUSH, id='push'), pytest.param(EDIT, id='edit')])
    def test_passes_the_launchers_stdout_through(
        self, tmp_path: Path, project_with_state: Path, text: str
    ) -> None:
        launcher = launcher_running(tmp_path, 'printf \'{"decision": "%s"}\\n\' "$1"')

        assert Wrapped(script=MAIN_THREAD, launcher=launcher, project=project_with_state).run(
            text
        ) == Outcome(code=0, stdout='{"decision": "main-thread-hook"}\n', stderr='')

    def test_passes_the_launchers_stderr_through(
        self, tmp_path: Path, project_with_state: Path
    ) -> None:
        launcher = launcher_running(tmp_path, 'echo "{}"; echo two tickets >&2')

        assert Wrapped(script=MAIN_THREAD, launcher=launcher, project=project_with_state).run(
            PUSH
        ) == Outcome(code=0, stdout='{}\n', stderr='two tickets\n')

    def test_keeps_the_hook_input_for_the_launcher(
        self, tmp_path: Path, project_with_state: Path
    ) -> None:
        launcher = launcher_running(tmp_path, 'cat')

        assert Wrapped(script=MAIN_THREAD, launcher=launcher, project=project_with_state).run(
            PUSH
        ).stdout == (f'{PUSH}\n')

    def test_prints_nothing_when_the_launcher_prints_nothing(
        self, tmp_path: Path, project_with_state: Path
    ) -> None:
        launcher = launcher_running(tmp_path, 'exit 0')

        assert (
            Wrapped(script=MAIN_THREAD, launcher=launcher, project=project_with_state).run(PUSH)
            == SILENT
        )
