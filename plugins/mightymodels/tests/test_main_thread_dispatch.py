"""The PreToolUse hook on Agent judges a caller that is no plugin worker as the main thread: its
dispatch of the engineer or the architect is denied while the one unclosed ticket on the checked-out
branch has no task in progress, and when the tickets cannot be read. Its dispatch of the architect
or the wingman is answered `ask`, with the reasons of the block, while that ticket has a task a
block stopped and its `auto-escalate` is off."""

import io
import json
from dataclasses import dataclass, field, replace
from types import MappingProxyType

import pytest
from mightymodels_plugin.commands.dispatch_hook import (
    BlockedTask,
    BranchTickets,
    BranchTicketsOrUnreadable,
    StartedOrUnreadable,
    agent_type,
    check_dispatch,
)
from mightymodels_plugin.commands.tests.hook_inputs import MAIN_THREAD_CALLERS
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Worker
from sqlalchemy.exc import OperationalError

ENGINEER = 'mightymodels:workers:engineer'
ARCHITECT = 'mightymodels:workers:architect'
INTERN = 'mightymodels:workers:intern'
WINGMAN = 'mightymodels:triage:wingman'
TICKET = 'retry-queue'
NOTHING_STARTED = BranchTickets(unclosed=(TICKET,))
ONE_STARTED = BranchTickets(unclosed=(TICKET,), in_progress=('T1',))
NO_TICKET = BranchTickets()
SEVERAL_TICKETS = BranchTickets(unclosed=('drain-loop', TICKET))
GATE_BLOCK = BlockedTask(
    id='T1',
    status='blocked',
    reasons=('the drain loop still sleeps', 'AC-2 carries no citation'),
)
FAILURE = BlockedTask(id='T3', status='failed', reasons=('no fix held',))
ARCHITECT_ON_A_BLOCK = BranchTickets(
    unclosed=(TICKET,), in_progress=('T1',), blocked=(GATE_BLOCK, FAILURE)
)
BLOCKED_AND_NOT_RESTARTED = BranchTickets(unclosed=(TICKET,), blocked=(GATE_BLOCK,))
AUTO_ESCALATING = replace(ARCHITECT_ON_A_BLOCK, auto_escalate=True)
BLOCKS_NAMED = (
    'T1 blocked: the drain loop still sleeps; AC-2 carries no citation | T3 failed: no fix held'
)
STATE_FAILURES = (
    pytest.param(StateError('CLAUDE_PLUGIN_DATA is not set'), id='no-data-directory'),
    pytest.param(PermissionError(13, 'Permission denied'), id='operating-system'),
    pytest.param(OperationalError('SELECT 1', {}, Exception('database is locked')), id='database'),
)
NO_DECISION = b''
TYPE_OF_TARGET = MappingProxyType(
    {ENGINEER: ENGINEER, ARCHITECT: ARCHITECT, 'engineer': ENGINEER, 'architect': ARCHITECT}
)
TYPE_OF_ESCALATION = MappingProxyType(
    {ARCHITECT: ARCHITECT, WINGMAN: WINGMAN, 'architect': ARCHITECT, 'wingman': WINGMAN}
)
NEVER_JUDGED = (
    *(
        agent_type(worker)
        for worker in Worker
        if worker not in {Worker.ENGINEER, Worker.ARCHITECT, Worker.INTERN, Worker.WINGMAN}
    ),
    'code-scout',
    'general-purpose',
    'mightymodels:engineer',
    f'{ENGINEER}:extra',
)


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeBranch:
    tickets: BranchTicketsOrUnreadable = NOTHING_STARTED
    asked: list[Worker | None] = field(default_factory=list)

    def started_by(self, worker: Worker) -> StartedOrUnreadable:
        self.asked.append(worker)
        return ()

    def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        self.asked.append(None)
        return self.tickets


def dispatch(caller: dict[str, object], target: object) -> str:
    return json.dumps({'tool_name': 'Agent', 'tool_input': {'subagent_type': target}} | caller)


def written(text: str, branch: FakeBranch) -> bytes:
    output = io.BytesIO()
    assert check_dispatch(io.StringIO(text), output, branch) == 0
    return output.getvalue()


def reason_of(text: str, branch: FakeBranch, answer: str) -> str:
    decision = json.loads(written(text, branch))['hookSpecificOutput']
    assert decision['hookEventName'] == 'PreToolUse'
    assert decision['permissionDecision'] == answer
    return decision['permissionDecisionReason']


def denial(text: str, branch: FakeBranch) -> str:
    return reason_of(text, branch, 'deny')


def question(text: str, branch: FakeBranch) -> str:
    return reason_of(text, branch, 'ask')


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
@pytest.mark.parametrize('target', TYPE_OF_TARGET)
class TestEngineerOrArchitect:
    def test_with_no_task_in_progress_it_is_denied_naming_the_ticket_and_the_step_to_take(
        self, caller: dict[str, object], target: str
    ) -> None:
        named = TYPE_OF_TARGET[target]

        assert denial(dispatch(caller, target), FakeBranch(tickets=NOTHING_STARTED)) == (
            f'{named} was refused: ticket {TICKET}, whose branch is checked out, has no task in '
            'progress. Start the task with the `task` tool (action `start`, `by` naming this '
            'worker), then dispatch again.'
        )

    def test_with_a_task_in_progress_it_gets_no_decision(
        self, caller: dict[str, object], target: str
    ) -> None:
        assert written(dispatch(caller, target), FakeBranch(tickets=ONE_STARTED)) == NO_DECISION

    def test_with_no_unclosed_ticket_on_the_branch_it_gets_no_decision(
        self, caller: dict[str, object], target: str
    ) -> None:
        assert written(dispatch(caller, target), FakeBranch(tickets=NO_TICKET)) == NO_DECISION

    def test_with_several_tickets_it_gets_no_decision_and_one_line_naming_them(
        self, caller: dict[str, object], target: str
    ) -> None:
        named = TYPE_OF_TARGET[target]

        printed = written(dispatch(caller, target), FakeBranch(tickets=SEVERAL_TICKETS))

        assert printed.count(b'\n') == 1
        assert json.loads(printed) == {
            'systemMessage': (
                f'mightymodels did not check the dispatch of {named} for a started task: the '
                f'checked-out branch has 2 unclosed tickets (drain-loop, {TICKET}), and the hook '
                'acts only when it has one'
            )
        }

    @pytest.mark.parametrize('failure', STATE_FAILURES)
    def test_when_the_tickets_cannot_be_read_it_is_denied_saying_why(
        self, caller: dict[str, object], target: str, failure: Exception
    ) -> None:
        named = TYPE_OF_TARGET[target]

        assert denial(dispatch(caller, target), FakeBranch(tickets=failure)) == (
            f'{named} was refused: the tasks in progress could not be read ({failure}), so a '
            'started task cannot be told from none. Dispatch again once the state can be read.'
        )

    def test_it_reads_the_tickets_once_and_no_workers_started_tasks(
        self, caller: dict[str, object], target: str
    ) -> None:
        branch = FakeBranch()

        written(dispatch(caller, target), branch)

        assert branch.asked == [None]


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
@pytest.mark.parametrize('target', TYPE_OF_ESCALATION)
class TestArchitectOrWingman:
    def test_with_a_blocked_task_and_auto_escalate_off_it_is_asked_with_the_reasons_of_the_block(
        self, caller: dict[str, object], target: str
    ) -> None:
        named = TYPE_OF_ESCALATION[target]

        assert question(dispatch(caller, target), FakeBranch(tickets=ARCHITECT_ON_A_BLOCK)) == (
            f'{named} was held for the owner: ticket {TICKET}, whose branch is checked out, has '
            f'a task a block stopped ({BLOCKS_NAMED}), and its `auto-escalate` is off. Approve '
            'this dispatch to escalate, or decline it and say what to do about the block. '
            '`auto-escalate: true` under `handoff-context` in ticket.yml, validated with the '
            '`ticket` tool, lets an escalation through without this question.'
        )

    def test_with_auto_escalate_on_it_gets_no_decision(
        self, caller: dict[str, object], target: str
    ) -> None:
        assert written(dispatch(caller, target), FakeBranch(tickets=AUTO_ESCALATING)) == NO_DECISION

    def test_with_no_blocked_task_it_gets_no_decision(
        self, caller: dict[str, object], target: str
    ) -> None:
        assert written(dispatch(caller, target), FakeBranch(tickets=ONE_STARTED)) == NO_DECISION

    def test_with_no_unclosed_ticket_on_the_branch_it_gets_no_decision(
        self, caller: dict[str, object], target: str
    ) -> None:
        assert written(dispatch(caller, target), FakeBranch(tickets=NO_TICKET)) == NO_DECISION

    def test_it_reads_the_tickets_once_and_no_workers_started_tasks(
        self, caller: dict[str, object], target: str
    ) -> None:
        branch = FakeBranch(tickets=ARCHITECT_ON_A_BLOCK)

        written(dispatch(caller, target), branch)

        assert branch.asked == [None]


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
class TestEscalationBesideTheStartedTaskRule:
    def test_the_architect_with_nothing_in_progress_is_denied_before_it_is_asked_about(
        self, caller: dict[str, object]
    ) -> None:
        branch = FakeBranch(tickets=BLOCKED_AND_NOT_RESTARTED)

        assert 'has no task in progress' in denial(dispatch(caller, ARCHITECT), branch)

    def test_the_wingman_needs_no_task_in_progress_to_be_asked_about(
        self, caller: dict[str, object]
    ) -> None:
        branch = FakeBranch(tickets=BLOCKED_AND_NOT_RESTARTED)

        assert 'T1 blocked: the drain loop still sleeps' in question(
            dispatch(caller, WINGMAN), branch
        )

    @pytest.mark.parametrize('tickets', [NOTHING_STARTED, SEVERAL_TICKETS])
    def test_the_wingman_gets_no_decision_with_nothing_blocked_or_several_tickets(
        self, caller: dict[str, object], tickets: BranchTickets
    ) -> None:
        assert written(dispatch(caller, WINGMAN), FakeBranch(tickets=tickets)) == NO_DECISION

    @pytest.mark.parametrize('failure', STATE_FAILURES)
    def test_when_the_tickets_cannot_be_read_the_wingman_gets_no_decision(
        self, caller: dict[str, object], failure: Exception
    ) -> None:
        assert written(dispatch(caller, WINGMAN), FakeBranch(tickets=failure)) == NO_DECISION

    @pytest.mark.parametrize('tickets', [ARCHITECT_ON_A_BLOCK, AUTO_ESCALATING])
    def test_the_engineer_is_never_asked_about(
        self, caller: dict[str, object], tickets: BranchTickets
    ) -> None:
        assert written(dispatch(caller, ENGINEER), FakeBranch(tickets=tickets)) == NO_DECISION


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
class TestOtherTargets:
    @pytest.mark.parametrize('target', [*NEVER_JUDGED, 7, None])
    def test_a_type_that_is_no_implementer_gets_no_decision_and_reads_no_state(
        self, caller: dict[str, object], target: object
    ) -> None:
        branch = FakeBranch()

        assert written(dispatch(caller, target), branch) == NO_DECISION
        assert branch.asked == []

    @pytest.mark.parametrize('tickets', [NOTHING_STARTED, ONE_STARTED, NO_TICKET, SEVERAL_TICKETS])
    def test_the_intern_is_held_by_its_own_rule_whatever_the_tickets_are(
        self, caller: dict[str, object], tickets: BranchTickets
    ) -> None:
        branch = FakeBranch(tickets=tickets)

        assert denial(dispatch(caller, INTERN), branch).startswith(f'{INTERN} was refused: no task')
        assert branch.asked == [Worker.INTERN]


class TestPluginWorker:
    @pytest.mark.parametrize('caller', Worker)
    @pytest.mark.parametrize('target', [ENGINEER, ARCHITECT])
    def test_its_dispatch_of_an_implementer_is_the_rows_to_judge_and_reads_no_tickets(
        self, caller: Worker, target: str
    ) -> None:
        branch = FakeBranch()
        dispatcher = agent_type(caller)

        reason = denial(dispatch({'agent_type': dispatcher}, target), branch)

        assert reason.startswith(f'{dispatcher} may not dispatch {target}; it may dispatch: ')
        assert branch.asked == []

    @pytest.mark.parametrize('caller', Worker)
    @pytest.mark.parametrize('target', [ARCHITECT, WINGMAN])
    def test_its_dispatch_of_an_escalation_is_the_rows_to_judge_whatever_is_blocked(
        self, caller: Worker, target: str
    ) -> None:
        branch = FakeBranch(tickets=ARCHITECT_ON_A_BLOCK)
        dispatcher = agent_type(caller)

        reason = denial(dispatch({'agent_type': dispatcher}, target), branch)

        assert reason.startswith(f'{dispatcher} may not dispatch {target}; it may dispatch: ')
        assert branch.asked == []
