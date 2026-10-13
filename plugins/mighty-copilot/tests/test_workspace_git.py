import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sql
from mcp.types import CallToolResult
from mightymodels.cli import main
from mightymodels.core.data_directory import SESSION_DATA_VARIABLE
from mightymodels.core.process import process_runner
from mightymodels.core.tests.support import GitRunner
from mightymodels.core.workspace import git_at, workspace_at
from mightymodels.tools.contract.repository import contract_store
from mightymodels.tools.contract.service import ContractService
from mightymodels.tools.task.tables import TransitionRow
from mightymodels.tools.tests.slug_calls import (
    SHOW,
    SLUG,
    START_REVIEW,
    TICKET,
    VALIDATE,
    WRITE,
    slug_results,
)
from mightymodels.tools.tests.support import (
    StateServer,
    ToolCall,
    text_of,
    tree,
    workspace_database,
)

PASSED, REJECTED = 0, 2
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
NEEDS_GIT = 'this needs git and no git executable is on PATH'
NOT_A_REPOSITORY = 'is not inside a git repository'
MARKER = 'ran.txt'
MARKER_COMMAND = {
    'id': 'I1',
    'argv': [sys.executable, '-c', f'from pathlib import Path; Path({MARKER!r}).write_text("ran")'],
    'approved_by': 'user',
}
START_TASK: ToolCall = (
    'task',
    {
        'action': 'start',
        'payload': {
            'task_id': 'T1',
            'change': {'by': 'engineer', 'owned': ['src/queue.py'], 'acceptance': ['AC-1']},
        },
    },
)
VERIFY_TASK: ToolCall = (
    'task',
    {'action': 'verify', 'payload': {'task_id': 'T1', 'change': {'commit': 'HEAD'}}},
)
READY: ToolCall = ('task', {'action': 'ready'})
APPROVE: ToolCall = ('contract', {'action': 'approve', 'commands': [MARKER_COMMAND]})
STATUS: ToolCall = ('contract', {'action': 'status'})


@dataclass(slots=True, kw_only=True, frozen=True)
class Project:
    server: StateServer
    data_directory: Path
    marker: Path

    def verify_a_started_task(self) -> CallToolResult:
        *_, verified = slug_results(self.server, WRITE, VALIDATE, START_TASK, VERIFY_TASK)
        return verified

    def transitions(self) -> list[tuple[str, str]]:
        query = sql.select(TransitionRow).order_by(TransitionRow.id)
        workspace = workspace_at(self.server.root)
        with (
            workspace_database(workspace, self.data_directory) as database,
            database.transaction() as session,
        ):
            return [(row.before, row.after) for row in session.scalars(query)]

    def command_states(self) -> list[str]:
        workspace = workspace_at(self.server.root)
        with workspace_database(workspace, self.data_directory) as database:
            status = ContractService(
                workspace=workspace,
                store=contract_store(database),
                git=git_at(self.server.root),
                processes=process_runner(),
            ).status(TICKET)
        return [command.state for command in status.commands]

    def created_files(self) -> dict[str, bytes]:
        return tree(self.server.root) | tree(self.data_directory)

    def results_of_the_other_actions(self) -> list[CallToolResult]:
        staged_then_asked = slug_results(self.server, WRITE, VALIDATE, START_TASK, READY, STATUS)
        return [*staged_then_asked[2:], *self.server.call(START_REVIEW)]


@pytest.fixture
def project(
    state_server: StateServer, data_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> Project:
    monkeypatch.chdir(str(state_server.root))
    monkeypatch.setenv(SESSION_DATA_VARIABLE, str(data_directory))
    slug_results(state_server, APPROVE)
    return Project(
        server=state_server,
        data_directory=data_directory,
        marker=state_server.root.joinpath(MARKER),
    )


class TestInsideARepository:
    IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')

    @pytest.fixture
    def first_commit(self, repository: Path, git: GitRunner) -> None:
        git(repository, *self.IDENTITY, 'commit', '--quiet', '--allow-empty', '-m', 'first commit')

    @pytest.mark.usefixtures('first_commit')
    def test_verify_run_runs_the_approved_command_where_git_answers(
        self, project: Project, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(['verify', 'run', '--slug', SLUG, '--all'])

        assert code == PASSED
        assert capsys.readouterr().out.startswith('I1 pass ')
        assert project.marker.read_text(encoding='utf-8') == 'ran'
        assert project.command_states() == ['pass task expect=0']


class TestWhenGitIsMissing:
    @pytest.fixture
    def project_without_git(
        self, project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Project:
        monkeypatch.setenv('PATH', str(tmp_path.joinpath('no-binaries')))
        return project

    def test_when_git_is_missing_the_server_lists_its_tools_and_refuses_every_ticket_call(
        self, project_without_git: Project
    ) -> None:
        listed = project_without_git.server.tools()
        refused = slug_results(project_without_git.server, WRITE, VALIDATE, SHOW)

        assert sorted(listed) == TOOL_NAMES
        assert [result.is_error for result in refused] == [True, True, True]
        assert [NEEDS_GIT in text_of(result) for result in refused] == [True, True, True]

    def test_when_git_is_missing_task_verify_is_refused_and_records_no_transition(
        self, project_without_git: Project
    ) -> None:
        verified = project_without_git.verify_a_started_task()

        assert verified.is_error
        assert NEEDS_GIT in text_of(verified)
        assert project_without_git.transitions() == []

    def test_when_git_is_missing_verify_run_is_refused_before_any_command_runs(
        self, project_without_git: Project, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(['verify', 'run', '--slug', SLUG, '--all'])

        assert code == REJECTED
        assert NEEDS_GIT in capsys.readouterr().err
        assert not project_without_git.marker.exists()
        assert project_without_git.command_states() == ['never-run']

    def test_when_git_is_missing_every_other_action_is_refused_the_same_way(
        self, project_without_git: Project
    ) -> None:
        refused = project_without_git.results_of_the_other_actions()

        assert [result.is_error for result in refused] == [True] * 4
        assert [NEEDS_GIT in text_of(result) for result in refused] == [True] * 4


class TestOutsideARepository:
    @pytest.fixture
    def state_server(self, tmp_path: Path, data_directory: Path) -> StateServer:
        directory = tmp_path.joinpath('plain-directory')
        directory.mkdir()
        return StateServer(root=directory, data_directory=data_directory)

    def test_outside_a_repository_task_verify_is_refused_and_nothing_is_created(
        self, project: Project
    ) -> None:
        verified = project.verify_a_started_task()

        assert verified.is_error
        assert NOT_A_REPOSITORY in text_of(verified)
        assert project.created_files() == {}

    def test_outside_a_repository_verify_run_is_refused_before_any_command_runs(
        self, project: Project, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(['verify', 'run', '--slug', SLUG, '--all'])

        assert code == REJECTED
        assert NOT_A_REPOSITORY in capsys.readouterr().err
        assert project.created_files() == {}

    def test_outside_a_repository_every_other_action_is_refused_the_same_way(
        self, project: Project
    ) -> None:
        refused = project.results_of_the_other_actions()

        assert [result.is_error for result in refused] == [True] * 4
        assert [NOT_A_REPOSITORY in text_of(result) for result in refused] == [True] * 4
