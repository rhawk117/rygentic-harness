import json
from pathlib import Path

import pytest
from mightymodels_plugin.commands.tests.hook_inputs import (
    OTHER_AGENTS,
    SKIPPED,
    UNREADABLE_INPUTS,
    Hook,
    hook_input,
    implementer_stop,
)
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.task.schema import Implementer, TaskStart
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

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

    def test_with_a_done_half_naming_a_commit_it_lets_the_stop_through(
        self, hook_command: Hook, brief: Path
    ) -> None:
        self.write_brief(brief, DONE_WITH_A_COMMIT)

        assert hook_command.run('completion-gate', implementer_stop()) == (0, '', '')

    def test_a_worker_that_started_nothing_is_let_through(self, hook_command: Hook) -> None:
        assert hook_command.run('completion-gate', implementer_stop('mightymodels:architect')) == (
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
