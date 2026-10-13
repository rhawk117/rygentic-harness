import json
from pathlib import Path

import pytest
from mightymodels.commands.tests.hook_inputs import (
    OTHER_AGENTS,
    SKIPPED,
    UNREADABLE_INPUTS,
    Hook,
    dispatch,
    hook_input,
    implementer_stop,
)
from mightymodels.core.data_directory import PLUGIN_DATA_VARIABLE
from mightymodels.core.slug import Slug
from mightymodels.core.tests.support import GitRunner
from mightymodels.core.workspace import Workspace
from mightymodels.tools.task.schema import Implementer, Status, TaskMark, TaskStart
from mightymodels.tools.task.service import TaskService
from mightymodels.tools.ticket.schema import TicketAnswers
from mightymodels.tools.ticket.service import TicketService

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
OTHER_SLUG = 'retry-queue-again'
BRANCH = 'fix/retry'
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


class TestTheStateOfATicket:
    @pytest.fixture
    def on_the_branch(
        self,
        hook_repository: Path,
        ticket_service: TicketService,
        git: GitRunner,
    ) -> Slug:
        git(hook_repository, 'symbolic-ref', 'HEAD', f'refs/heads/{BRANCH}')
        ticket_service.write(TICKET, ANSWERS)
        ticket_service.validate(TICKET)
        return TICKET

    @pytest.fixture
    def engineer_on_t1(self, on_the_branch: Slug, task_service: TaskService) -> None:
        task_service.start(
            on_the_branch,
            'T1',
            TaskStart(by=Implementer.ENGINEER, owned=('src/queue.py',), acceptance=('AC-1',)),
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
        self, hook_command: Hook
    ) -> None:
        code, out, err = hook_command.run('completion-gate', implementer_stop())
        decision = json.loads(out)

        assert (code, err) == (0, '')
        assert decision['decision'] == 'block'
        assert 'T1' in decision['reason']
        assert 'task-01.md is missing' in decision['reason']

    def test_with_a_done_half_naming_no_commit_it_blocks_naming_what_is_missing(
        self, hook_command: Hook, brief: Path
    ) -> None:
        self.write_brief(brief, DONE_WITHOUT_A_COMMIT)

        _, out, _ = hook_command.run('completion-gate', implementer_stop())
        reason = json.loads(out)['reason']

        assert 'T1' in reason
        assert 'has no DONE half naming a commit' in reason

    def test_a_second_stop_after_the_block_is_let_through(self, hook_command: Hook) -> None:
        first = hook_command.run('completion-gate', implementer_stop())
        second = hook_command.run('completion-gate', implementer_stop(stop_hook_active=True))

        assert json.loads(first[1])['decision'] == 'block'
        assert second == (0, '', '')

    def test_it_finds_the_ticket_under_the_payload_cwd_not_the_process_directory(
        self, hook_command: Hook, tmp_path: Path
    ) -> None:
        elsewhere = tmp_path.joinpath('elsewhere')
        elsewhere.mkdir()
        hook_command.monkeypatch.chdir(elsewhere)

        under_the_process_directory = hook_command.run('completion-gate', implementer_stop())
        under_the_payload_cwd = hook_command.run(
            'completion-gate', implementer_stop(cwd=str(hook_command.repository))
        )

        assert under_the_process_directory[0:2] == (0, '')
        assert json.loads(under_the_payload_cwd[1])['decision'] == 'block'

    def test_with_a_done_half_naming_a_commit_it_lets_the_stop_through(
        self, hook_command: Hook, brief: Path
    ) -> None:
        self.write_brief(brief, DONE_WITH_A_COMMIT)

        assert hook_command.run('completion-gate', implementer_stop()) == (0, '', '')

    def test_a_worker_that_started_nothing_is_let_through(self, hook_command: Hook) -> None:
        assert hook_command.run(
            'completion-gate', implementer_stop('mightymodels:workers:architect')
        ) == (
            0,
            '',
            '',
        )

    @pytest.mark.parametrize('agent_type', OTHER_AGENTS)
    def test_another_agent_type_is_let_through(self, agent_type: str, hook_command: Hook) -> None:
        assert hook_command.run('completion-gate', implementer_stop(agent_type)) == (0, '', '')

    @pytest.mark.parametrize('text', UNREADABLE_INPUTS)
    def test_unreadable_input_is_let_through_and_says_why(
        self, text: str, hook_command: Hook
    ) -> None:
        code, out, err = hook_command.run('completion-gate', text)

        assert (code, out) == (0, '')
        assert err.startswith(SKIPPED)

    def test_off_the_ticket_branch_it_does_nothing(
        self, hook_command: Hook, git: GitRunner
    ) -> None:
        git(hook_command.repository, 'symbolic-ref', 'HEAD', 'refs/heads/elsewhere')

        assert hook_command.run('completion-gate', implementer_stop()) == (0, '', '')


@pytest.mark.usefixtures('intern_on_t1')
class TestCompletionGateOnTheIntern(TestTheStateOfATicket):
    INTERN = 'mightymodels:workers:intern'

    @pytest.fixture
    def intern_on_t1(self, on_the_branch: Slug, task_service: TaskService) -> Slug:
        task_service.start(
            on_the_branch,
            'T1',
            TaskStart(by=Implementer.INTERN, owned=('src/queue.py',), acceptance=('AC-1',)),
        )
        return on_the_branch

    @pytest.fixture
    def taken_over_by_the_engineer(self, intern_on_t1: Slug, task_service: TaskService) -> None:
        task_service.mark(intern_on_t1, 'T1', TaskMark(to=Status.BLOCKED, reason='AC-1 still red'))
        task_service.start(
            intern_on_t1,
            'T1',
            TaskStart(by=Implementer.ENGINEER, owned=('src/queue.py',), acceptance=('AC-1',)),
        )

    def test_it_blocks_the_interns_stop_naming_the_task_and_the_missing_brief(
        self, hook_command: Hook
    ) -> None:
        code, out, err = hook_command.run('completion-gate', implementer_stop(self.INTERN))
        decision = json.loads(out)

        assert (code, err) == (0, '')
        assert decision['decision'] == 'block'
        assert 'T1' in decision['reason']
        assert 'task-01.md is missing' in decision['reason']

    def test_with_a_done_half_naming_a_commit_it_lets_the_intern_stop(
        self, hook_command: Hook, brief: Path
    ) -> None:
        self.write_brief(brief, DONE_WITH_A_COMMIT)

        assert hook_command.run('completion-gate', implementer_stop(self.INTERN)) == (0, '', '')

    def test_the_engineer_that_did_not_start_the_task_is_let_through(
        self, hook_command: Hook
    ) -> None:
        assert hook_command.run('completion-gate', implementer_stop()) == (0, '', '')

    @pytest.mark.usefixtures('taken_over_by_the_engineer')
    def test_once_the_engineer_took_the_task_over_it_holds_the_engineer_and_not_the_intern(
        self, hook_command: Hook
    ) -> None:
        _, held, _ = hook_command.run('completion-gate', implementer_stop())

        assert json.loads(held)['decision'] == 'block'
        assert hook_command.run('completion-gate', implementer_stop(self.INTERN)) == (0, '', '')


@pytest.mark.usefixtures('on_the_branch')
class TestDispatchOfTheIntern(TestTheStateOfATicket):
    INTERN = 'mightymodels:workers:intern'
    ENGINEER = 'mightymodels:workers:engineer'
    NO_TASK_STARTED = 'no task is started for the intern on the ticket whose branch is checked out'
    NOTHING_FOR_THE_INTERN = ('on_the_branch', 'engineer_on_t1')
    WHATEVER_IS_STARTED = ('engineer_on_t1', 'intern_on_one_file', 'intern_on_two_files')

    @pytest.fixture
    def intern_on_one_file(self, on_the_branch: Slug, task_service: TaskService) -> None:
        task_service.start(
            on_the_branch,
            'T1',
            TaskStart(by=Implementer.INTERN, owned=('src/queue.py',), acceptance=('AC-1',)),
        )

    @pytest.fixture
    def intern_on_two_files(self, on_the_branch: Slug, task_service: TaskService) -> None:
        task_service.start(
            on_the_branch,
            'T1',
            TaskStart(
                by=Implementer.INTERN, owned=('src/queue.py', 'src/drain.py'), acceptance=('AC-1',)
            ),
        )

    def refusal(self, hook_command: Hook) -> str:
        code, out, err = hook_command.run('dispatch-hook', dispatch(self.INTERN))
        decision = json.loads(out)['hookSpecificOutput']

        assert (code, err) == (0, '')
        assert decision['permissionDecision'] == 'deny'
        assert decision['permissionDecisionReason'].startswith(f'{self.INTERN} was refused: ')
        assert decision['permissionDecisionReason'].endswith(f'dispatch {self.ENGINEER} instead.')
        return decision['permissionDecisionReason']

    @pytest.mark.parametrize('started', NOTHING_FOR_THE_INTERN)
    def test_with_no_task_started_for_it_it_is_refused(
        self, started: str, request: pytest.FixtureRequest, hook_command: Hook
    ) -> None:
        request.getfixturevalue(started)

        assert self.NO_TASK_STARTED in self.refusal(hook_command)

    @pytest.mark.usefixtures('intern_on_one_file')
    def test_off_the_ticket_branch_it_is_refused(self, hook_command: Hook, git: GitRunner) -> None:
        git(hook_command.repository, 'symbolic-ref', 'HEAD', 'refs/heads/elsewhere')

        assert self.NO_TASK_STARTED in self.refusal(hook_command)

    @pytest.mark.usefixtures('intern_on_two_files')
    def test_on_a_task_owning_two_files_it_is_refused_naming_the_task(
        self, hook_command: Hook
    ) -> None:
        assert 'T1 owns 2 files' in self.refusal(hook_command)

    @pytest.mark.usefixtures('intern_on_one_file')
    def test_on_a_task_owning_exactly_one_file_it_is_allowed(self, hook_command: Hook) -> None:
        assert hook_command.run('dispatch-hook', dispatch(self.INTERN)) == (0, '', '')

    @pytest.mark.usefixtures('intern_on_one_file')
    def test_when_the_state_cannot_be_read_it_is_refused_saying_so(
        self, hook_command: Hook
    ) -> None:
        hook_command.monkeypatch.delenv(PLUGIN_DATA_VARIABLE)

        reason = self.refusal(hook_command)

        assert f'the started task could not be read ({PLUGIN_DATA_VARIABLE} is not set' in reason

    @pytest.mark.usefixtures('intern_on_one_file')
    def test_when_the_data_directory_cannot_be_created_it_is_refused_saying_so(
        self, hook_command: Hook, tmp_path: Path
    ) -> None:
        regular_file = tmp_path.joinpath('a-regular-file')
        regular_file.write_text('', encoding='utf-8')
        under_a_file = regular_file.joinpath('plugin-data')
        hook_command.monkeypatch.setenv(PLUGIN_DATA_VARIABLE, str(under_a_file))

        reason = self.refusal(hook_command)

        assert 'the started task could not be read (' in reason
        assert str(under_a_file) in reason

    @pytest.mark.parametrize('started', WHATEVER_IS_STARTED)
    def test_an_engineer_dispatch_is_allowed_whatever_task_is_in_progress(
        self, started: str, request: pytest.FixtureRequest, hook_command: Hook
    ) -> None:
        request.getfixturevalue(started)

        assert hook_command.run('dispatch-hook', dispatch(self.ENGINEER)) == (0, '', '')


@pytest.mark.usefixtures('on_the_branch')
class TestDispatchFromTheMainThread(TestTheStateOfATicket):
    STARTED_FIRST = ('mightymodels:workers:engineer', 'mightymodels:workers:architect')
    NO_TASK_IN_PROGRESS = f'ticket {SLUG}, whose branch is checked out, has no task in progress'

    def refusal(self, hook_command: Hook, target: str) -> str:
        code, out, err = hook_command.run('dispatch-hook', dispatch(target))
        decision = json.loads(out)['hookSpecificOutput']

        assert (code, err) == (0, '')
        assert decision['permissionDecision'] == 'deny'
        assert decision['permissionDecisionReason'].startswith(f'{target} was refused: ')
        return decision['permissionDecisionReason']

    @pytest.mark.parametrize('target', STARTED_FIRST)
    def test_with_no_task_in_progress_it_is_refused_naming_the_ticket_and_the_step(
        self, target: str, hook_command: Hook
    ) -> None:
        reason = self.refusal(hook_command, target)

        assert self.NO_TASK_IN_PROGRESS in reason
        assert 'Start the task with the `task` tool' in reason

    @pytest.mark.usefixtures('engineer_on_t1')
    @pytest.mark.parametrize('target', STARTED_FIRST)
    def test_with_a_task_in_progress_it_gets_no_decision(
        self, target: str, hook_command: Hook
    ) -> None:
        assert hook_command.run('dispatch-hook', dispatch(target)) == (0, '', '')

    @pytest.mark.parametrize('target', STARTED_FIRST)
    def test_off_the_ticket_branch_it_gets_no_decision(
        self, target: str, hook_command: Hook, git: GitRunner
    ) -> None:
        git(hook_command.repository, 'symbolic-ref', 'HEAD', 'refs/heads/elsewhere')

        assert hook_command.run('dispatch-hook', dispatch(target)) == (0, '', '')

    @pytest.mark.parametrize('target', STARTED_FIRST)
    def test_with_two_tickets_on_the_branch_it_gets_no_decision_and_one_line_naming_them(
        self, target: str, hook_command: Hook, ticket_service: TicketService
    ) -> None:
        other = Slug(OTHER_SLUG)
        ticket_service.write(other, ANSWERS)
        ticket_service.validate(other)

        code, out, err = hook_command.run('dispatch-hook', dispatch(target))

        assert (code, err, out.count('\n')) == (0, '', 1)
        assert list(json.loads(out)) == ['systemMessage']
        assert f'2 unclosed tickets ({SLUG}, {OTHER_SLUG})' in json.loads(out)['systemMessage']

    @pytest.mark.usefixtures('engineer_on_t1')
    @pytest.mark.parametrize('target', STARTED_FIRST)
    def test_when_the_state_cannot_be_read_it_is_refused_saying_so(
        self, target: str, hook_command: Hook
    ) -> None:
        hook_command.monkeypatch.delenv(PLUGIN_DATA_VARIABLE)

        reason = self.refusal(hook_command, target)

        assert f'could not be read ({PLUGIN_DATA_VARIABLE} is not set' in reason

    @pytest.mark.usefixtures('engineer_on_t1')
    def test_when_the_data_directory_cannot_be_created_it_is_refused_saying_so(
        self, hook_command: Hook, tmp_path: Path
    ) -> None:
        regular_file = tmp_path.joinpath('a-regular-file')
        regular_file.write_text('', encoding='utf-8')
        under_a_file = regular_file.joinpath('plugin-data')
        hook_command.monkeypatch.setenv(PLUGIN_DATA_VARIABLE, str(under_a_file))

        assert str(under_a_file) in self.refusal(hook_command, self.STARTED_FIRST[0])

    def test_with_a_detached_head_it_gets_no_decision(
        self, hook_command: Hook, git: GitRunner
    ) -> None:
        identity = ('-c', 'user.name=t', '-c', 'user.email=t@example.com')
        git(hook_command.repository, *identity, 'commit', '--allow-empty', '-q', '-m', 'base')
        git(hook_command.repository, 'checkout', '-q', '--detach')

        assert hook_command.run('dispatch-hook', dispatch(self.STARTED_FIRST[0])) == (0, '', '')

    @pytest.mark.usefixtures('engineer_on_t1')
    def test_a_project_directory_under_the_repository_still_finds_the_ticket_directory(
        self, hook_command: Hook
    ) -> None:
        below = hook_command.repository.joinpath('src', 'queue')
        below.mkdir(parents=True)
        hook_command.monkeypatch.chdir(below)
        hook_command.monkeypatch.delenv(PLUGIN_DATA_VARIABLE)

        assert 'could not be read' in self.refusal(hook_command, self.STARTED_FIRST[0])


def snapshot_files(repository: Path) -> list[str]:
    handoffs = repository.joinpath('.mightymodels', SLUG, 'handoffs')
    return sorted(path.name for path in handoffs.glob('*')) if handoffs.exists() else []


@pytest.mark.usefixtures('on_the_branch')
class TestPreCompactSnapshot(TestTheStateOfATicket):
    @pytest.mark.parametrize('trigger', ['manual', 'auto'])
    def test_it_writes_the_snapshot_of_the_ticket_on_the_checked_out_branch(
        self, trigger: str, hook_command: Hook
    ) -> None:
        code, out, err = hook_command.run('pre-compact', hook_input('PreCompact', trigger=trigger))
        record = json.loads(
            hook_command.repository.joinpath(
                '.mightymodels', SLUG, 'handoffs', 'snapshot.json'
            ).read_text(encoding='utf-8')
        )

        assert (code, out, err) == (0, '', '')
        assert snapshot_files(hook_command.repository) == ['snapshot.json', 'snapshot.md']
        assert record['slug'] == SLUG
        assert record['repository']['branch'] == BRANCH

    def test_on_another_branch_it_writes_nothing(self, hook_command: Hook, git: GitRunner) -> None:
        git(hook_command.repository, 'symbolic-ref', 'HEAD', 'refs/heads/elsewhere')

        assert hook_command.run('pre-compact', hook_input('PreCompact')) == (0, '', '')
        assert snapshot_files(hook_command.repository) == []

    def test_with_a_detached_head_it_writes_nothing(
        self, hook_command: Hook, git: GitRunner
    ) -> None:
        git(
            hook_command.repository,
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
        git(hook_command.repository, 'checkout', '-q', '--detach')

        assert hook_command.run('pre-compact', hook_input('PreCompact')) == (0, '', '')
        assert snapshot_files(hook_command.repository) == []

    def test_with_two_tickets_on_the_branch_it_writes_nothing(
        self, hook_command: Hook, ticket_service: TicketService
    ) -> None:
        other = Slug(OTHER_SLUG)
        ticket_service.write(other, ANSWERS)
        ticket_service.validate(other)

        assert hook_command.run('pre-compact', hook_input('PreCompact')) == (0, '', '')
        assert snapshot_files(hook_command.repository) == []
        assert not hook_command.repository.joinpath(
            '.mightymodels', OTHER_SLUG, 'handoffs'
        ).exists()
