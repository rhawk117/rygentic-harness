"""The PreToolUse hook on Agent judges a caller that is no plugin worker as the main thread: its
dispatch of the engineer or the architect is denied while the one unclosed ticket on the checked-out
branch has no task in progress, and when the tickets cannot be read."""

import io
import json
from dataclasses import dataclass, field
from types import MappingProxyType

import pytest
from mightymodels_plugin.commands.dispatch_hook import (
    BranchTickets,
    BranchTicketsOrUnreadable,
    StartedOrUnreadable,
    agent_type,
    check_dispatch,
)
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Worker
from sqlalchemy.exc import OperationalError

ENGINEER = 'mightymodels:workers:engineer'
ARCHITECT = 'mightymodels:workers:architect'
INTERN = 'mightymodels:workers:intern'
TICKET = 'retry-queue'
NOTHING_STARTED = BranchTickets(unclosed=(TICKET,))
ONE_STARTED = BranchTickets(unclosed=(TICKET,), in_progress=('T1',))
NO_TICKET = BranchTickets()
SEVERAL_TICKETS = BranchTickets(unclosed=('drain-loop', TICKET))
NO_DECISION = b''
MAIN_THREAD_CALLERS = (
    pytest.param({}, id='no-agent-type'),
    pytest.param({'agent_type': 7}, id='agent-type-a-number'),
    pytest.param({'agent_type': None}, id='agent-type-null'),
    pytest.param({'agent_type': [ENGINEER]}, id='agent-type-a-list'),
    pytest.param({'agent_type': {'name': ENGINEER}}, id='agent-type-an-object'),
    pytest.param({'agent_type': ''}, id='agent-type-empty'),
    pytest.param({'agent_type': 'general-purpose'}, id='built-in'),
    pytest.param({'agent_type': 'other:engineer'}, id='another-plugins-agent'),
)
TYPE_OF_TARGET = MappingProxyType(
    {ENGINEER: ENGINEER, ARCHITECT: ARCHITECT, 'engineer': ENGINEER, 'architect': ARCHITECT}
)
NEVER_JUDGED = (
    *(
        agent_type(worker)
        for worker in Worker
        if worker not in {Worker.ENGINEER, Worker.ARCHITECT, Worker.INTERN}
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


def denial(text: str, branch: FakeBranch) -> str:
    decision = json.loads(written(text, branch))['hookSpecificOutput']
    assert decision['hookEventName'] == 'PreToolUse'
    assert decision['permissionDecision'] == 'deny'
    return decision['permissionDecisionReason']


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

    @pytest.mark.parametrize(
        'failure',
        [
            pytest.param(StateError('CLAUDE_PLUGIN_DATA is not set'), id='no-data-directory'),
            pytest.param(PermissionError(13, 'Permission denied'), id='operating-system'),
            pytest.param(
                OperationalError('SELECT 1', {}, Exception('database is locked')), id='database'
            ),
        ],
    )
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
