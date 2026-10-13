"""The dispatch hook on a ticket with a task a block stopped, read from the state database: a
main-thread dispatch of the architect or the wingman is answered `ask` with the reasons of the
block, unless the ticket's `auto-escalate` is on."""

import pytest
from mightymodels.commands.tests.hook_inputs import Hook, dispatch
from mightymodels.commands.tests.ticket_checkout import (
    NO_DECISION,
    OTHER_SLUG,
    SLUG,
    TICKET,
    TicketCheckout,
    decision_of,
)
from mightymodels.core.data_directory import PLUGIN_DATA_VARIABLE
from mightymodels.core.slug import Slug
from mightymodels.tools.task.schema import (
    ArchitectMode,
    Implementer,
    Status,
    TaskMark,
    TaskStart,
)
from mightymodels.tools.task.service import TaskService

ENGINEER = 'mightymodels:workers:engineer'
ARCHITECT = 'mightymodels:workers:architect'
WINGMAN = 'mightymodels:triage:wingman'
ESCALATIONS = (ARCHITECT, WINGMAN)
BLOCKER = 'changed outside the owned set'
FAILURE = 'AC-1 still red after three fixes'
LAST_HANDOFF_LINE = '  worktrees-okay: false'


def start(
    tasks: TaskService, task_id: str, by: Implementer, mode: ArchitectMode | None = None
) -> None:
    change = TaskStart(by=by, owned=('src/queue.py',), acceptance=('AC-1',), mode=mode)
    tasks.start(TICKET, task_id, change)


def answer(hook_command: Hook, target: str, caller: str | None = None) -> tuple[str, str]:
    code, out, err = hook_command.run('dispatch-hook', dispatch(target, caller))

    assert (code, err) == (0, '')
    return decision_of(out)


def question(hook_command: Hook, target: str) -> str:
    decision, reason = answer(hook_command, target)

    assert decision == 'ask'
    assert reason.startswith(f'{target} was held for the owner: ticket {SLUG}, ')
    return reason


class TestABlockOnTheTicket:
    @pytest.fixture
    def engineer_at_work(
        self, checked_out_ticket: TicketCheckout, task_service: TaskService
    ) -> TicketCheckout:
        start(task_service, 'T1', Implementer.ENGINEER)
        return checked_out_ticket

    @pytest.fixture
    def engineer_blocked(
        self, engineer_at_work: TicketCheckout, task_service: TaskService
    ) -> TicketCheckout:
        task_service.mark(TICKET, 'T1', TaskMark(to=Status.BLOCKED, reason=BLOCKER))
        return engineer_at_work

    @pytest.fixture
    def engineer_failed(
        self, engineer_at_work: TicketCheckout, task_service: TaskService
    ) -> TicketCheckout:
        task_service.mark(TICKET, 'T1', TaskMark(to=Status.FAILED, reason=FAILURE))
        return engineer_at_work

    @pytest.fixture
    def architect_on_the_block(
        self, engineer_blocked: TicketCheckout, task_service: TaskService
    ) -> TicketCheckout:
        start(task_service, 'T1', Implementer.ARCHITECT)
        return engineer_blocked

    @pytest.fixture
    def architect_on_the_failure(
        self, engineer_failed: TicketCheckout, task_service: TaskService
    ) -> TicketCheckout:
        start(task_service, 'T1', Implementer.ARCHITECT)
        return engineer_failed

    @pytest.fixture
    def engineer_on_the_block_again(
        self, engineer_blocked: TicketCheckout, task_service: TaskService
    ) -> TicketCheckout:
        start(task_service, 'T1', Implementer.ENGINEER)
        return engineer_blocked

    @pytest.fixture
    def architect_widening_what_the_engineer_restarted(
        self, engineer_on_the_block_again: TicketCheckout, task_service: TaskService
    ) -> TicketCheckout:
        start(task_service, 'T1', Implementer.ARCHITECT, ArchitectMode.SYSTEMIC_REFACTOR)
        return engineer_on_the_block_again

    @pytest.fixture
    def architect_replanning_with_no_block(
        self, checked_out_ticket: TicketCheckout, task_service: TaskService
    ) -> TicketCheckout:
        start(task_service, 'T2', Implementer.ARCHITECT, ArchitectMode.DIAGNOSE_REPLAN)
        return checked_out_ticket

    @pytest.fixture
    def auto_escalating(self, architect_on_the_block: TicketCheckout) -> TicketCheckout:
        tickets = architect_on_the_block.tickets
        ticket_file = tickets.workspace.ticket_file(TICKET)
        written = ticket_file.read_text(encoding='utf-8')
        turned_on = f'{LAST_HANDOFF_LINE}\n  auto-escalate: true'
        ticket_file.write_text(written.replace(LAST_HANDOFF_LINE, turned_on), encoding='utf-8')
        tickets.validate(TICKET)
        return architect_on_the_block


class TestEscalationOfABlock(TestABlockOnTheTicket):
    @pytest.mark.usefixtures('architect_on_the_block')
    @pytest.mark.parametrize('target', ESCALATIONS)
    def test_with_the_architect_started_on_a_block_it_is_asked_with_the_reasons_of_the_block(
        self, target: str, hook_command: Hook
    ) -> None:
        assert f'has a task a block stopped (T1 blocked: {BLOCKER}), ' in question(
            hook_command, target
        )

    @pytest.mark.usefixtures('architect_on_the_failure')
    @pytest.mark.parametrize('target', ESCALATIONS)
    def test_with_the_architect_started_on_a_failure_it_is_asked_with_its_reasons(
        self, target: str, hook_command: Hook
    ) -> None:
        assert f'(T1 failed: {FAILURE})' in question(hook_command, target)

    @pytest.mark.parametrize(
        ('stopped', 'named'),
        [
            pytest.param('engineer_blocked', f'T1 blocked: {BLOCKER}', id='blocked'),
            pytest.param('engineer_failed', f'T1 failed: {FAILURE}', id='failed'),
        ],
    )
    def test_with_a_task_blocked_or_failed_and_not_started_again_the_wingman_is_asked_about(
        self, stopped: str, named: str, hook_command: Hook, request: pytest.FixtureRequest
    ) -> None:
        request.getfixturevalue(stopped)

        assert f'({named})' in question(hook_command, WINGMAN)

    @pytest.mark.usefixtures('engineer_blocked')
    def test_the_architect_is_denied_until_the_blocked_task_is_started_for_it(
        self, hook_command: Hook
    ) -> None:
        decision, reason = answer(hook_command, ARCHITECT)

        assert decision == 'deny'
        assert 'has no task in progress' in reason


class TestEscalationNotAskedAbout(TestABlockOnTheTicket):
    @pytest.mark.usefixtures('auto_escalating')
    @pytest.mark.parametrize('target', ESCALATIONS)
    def test_with_auto_escalate_on_in_the_ticket_it_gets_no_decision(
        self, target: str, hook_command: Hook
    ) -> None:
        assert hook_command.run('dispatch-hook', dispatch(target)) == NO_DECISION

    @pytest.mark.parametrize(
        'started',
        [
            'engineer_at_work',
            'engineer_on_the_block_again',
            'architect_widening_what_the_engineer_restarted',
            'architect_replanning_with_no_block',
        ],
    )
    @pytest.mark.parametrize('target', ESCALATIONS)
    def test_with_no_block_behind_the_task_in_progress_it_gets_no_decision(
        self, target: str, started: str, hook_command: Hook, request: pytest.FixtureRequest
    ) -> None:
        request.getfixturevalue(started)

        assert hook_command.run('dispatch-hook', dispatch(target)) == NO_DECISION

    @pytest.mark.usefixtures('architect_on_the_block')
    def test_the_engineer_is_not_asked_about(self, hook_command: Hook) -> None:
        assert hook_command.run('dispatch-hook', dispatch(ENGINEER)) == NO_DECISION

    @pytest.mark.usefixtures('architect_on_the_block')
    @pytest.mark.parametrize('target', ESCALATIONS)
    def test_a_workers_dispatch_of_it_is_denied_by_its_row_as_before(
        self, target: str, hook_command: Hook
    ) -> None:
        decision, reason = answer(hook_command, target, ENGINEER)

        assert decision == 'deny'
        assert reason.startswith(f'{ENGINEER} may not dispatch {target}; it may dispatch: ')

    def test_off_the_ticket_branch_the_wingman_gets_no_decision(
        self, engineer_blocked: TicketCheckout, hook_command: Hook
    ) -> None:
        engineer_blocked.git('symbolic-ref', 'HEAD', 'refs/heads/elsewhere')

        assert hook_command.run('dispatch-hook', dispatch(WINGMAN)) == NO_DECISION

    def test_with_two_tickets_on_the_branch_the_wingman_gets_no_decision(
        self, engineer_blocked: TicketCheckout, hook_command: Hook
    ) -> None:
        engineer_blocked.stage(Slug(OTHER_SLUG))

        assert hook_command.run('dispatch-hook', dispatch(WINGMAN)) == NO_DECISION

    @pytest.mark.usefixtures('engineer_blocked')
    def test_when_the_state_cannot_be_read_the_wingman_gets_no_decision(
        self, hook_command: Hook
    ) -> None:
        hook_command.monkeypatch.delenv(PLUGIN_DATA_VARIABLE)

        assert hook_command.run('dispatch-hook', dispatch(WINGMAN)) == NO_DECISION
