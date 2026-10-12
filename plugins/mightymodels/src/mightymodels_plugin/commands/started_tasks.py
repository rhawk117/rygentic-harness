"""The tasks a worker has in progress on the ticket whose branch is checked out, and the tickets
that are on it.

`started_on_branch` answers the tasks from open state: the in-progress tasks of that ticket whose
latest attempt was the worker's, in task order, each with the files it owns. A branch with no
ticket has none. This is the one place a hook learns what a started task owns.

`tickets_on_branch` answers every unclosed ticket on the checked-out branch and, when there is
exactly one, the tasks it has in progress, whoever started them, whether the ticket escalates a
block unasked (`auto-escalate`), and the tasks a block stopped.

A block stopped a task that is `blocked` or `failed`, and one that is in progress on an attempt of
the architect's that started from `blocked` or `failed`: agents-assemble marks the task and starts
it for the architect before it dispatches, so by then the task reads in progress. `blocked_tasks`
answers each with the status and the reasons of its latest move into `blocked` or `failed`. A task
the architect started from any other status has no block behind it and is not one of them.

`landing_on_branch` answers the same tickets and, when there is exactly one, what keeps it from
landing: every reason the `task` tool's `ready` action would give, read through the functions
`ready` reads them through, and every live contract command whose passing receipt at HEAD was not
taken in the landing phase. It writes nothing.

`HookState` is what a hook that holds no state reads through, and it is the `StartedTasks` and the
`TicketOnBranch` the hook rules take. Its `started_by`, `tickets_on_branch` and `landing_on_branch`
each open the state the completion gate opens, from the project directory and the plugin data
directory Claude Code gives a hook, and answer the failure in place of the read when there is no
data directory, no git work tree, the database refuses, or the operating system refuses the data
directory, the database file or git's exclude file, so the hook decides what an unreadable state
means. None opens the state of a repository that has no ticket directory
(`HookContext.has_ticket_directory`): such a repository has no ticket, so its answer is no task and
no ticket. `ticket_directory_holds` is the answer of the `HookContext` it was given.
"""

from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from mightymodels_plugin.commands.branch_ticket import ticket_on_branch, unclosed_tickets_on_branch
from mightymodels_plugin.commands.dispatch_hook import (
    BlockedTask,
    BranchTickets,
    BranchTicketsOrUnreadable,
    StartedOrUnreadable,
    StartedTask,
)
from mightymodels_plugin.commands.hook_context import HookContext
from mightymodels_plugin.commands.main_thread_hook import Landing, LandingOrUnreadable
from mightymodels_plugin.core.edge import OpenState, open_state
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Worker
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import find_root
from mightymodels_plugin.tools.contract.schema import Phase, Receipt
from mightymodels_plugin.tools.contract.store import RecordedCommand
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.task.gates import (
    STUCK,
    readiness_problems,
    receipt_problem,
    receipt_problems,
)
from mightymodels_plugin.tools.task.repository import (
    SqliteTaskRepository,
    SqliteTaskStore,
    in_progress_started_by,
    latest_transition_of_each_task_into,
)
from mightymodels_plugin.tools.task.schema import Implementer, Status, TaskRecord
from mightymodels_plugin.tools.task.service import records_of
from mightymodels_plugin.tools.ticket.repository import ticket_store

STATE_UNREADABLE = (StateError, SQLAlchemyError, OSError)


def started_on_branch(state: OpenState, worker: Implementer) -> list[StartedTask]:
    slug = ticket_on_branch(ticket_store(state.database), state.git.current_branch())
    if slug is None:
        return []
    with SqliteTaskStore(database=state.database).transaction() as tasks:
        owned = {task.id: task.owned for task in tasks.tasks(slug)}
        started = in_progress_started_by(tasks, slug, worker)
    return [StartedTask(id=task_id, owned=owned[task_id]) for task_id in started]


def blocked_tasks(
    tasks: SqliteTaskRepository, slug: Slug, records: Sequence[TaskRecord]
) -> tuple[BlockedTask, ...]:
    blocks = latest_transition_of_each_task_into(tasks, slug, STUCK)
    starts = latest_transition_of_each_task_into(tasks, slug, {Status.IN_PROGRESS})
    escalated = {
        task_id
        for task_id in in_progress_started_by(tasks, slug, Implementer.ARCHITECT)
        if starts[task_id].before in STUCK
    }
    return tuple(
        BlockedTask(
            id=record.id,
            status=blocks[record.id].after,
            reasons=tuple(blocks[record.id].reasons),
        )
        for record in records
        if record.status in STUCK or record.id in escalated
    )


def tickets_on_branch(state: OpenState) -> BranchTickets:
    unclosed = unclosed_tickets_on_branch(ticket_store(state.database), state.git.current_branch())
    names = tuple(map(str, unclosed))
    if len(unclosed) != 1:
        return BranchTickets(unclosed=names)
    slug = unclosed[0]
    with SqliteTaskStore(database=state.database).transaction() as tasks:
        records = tasks.tasks(slug)
        return BranchTickets(
            unclosed=names,
            in_progress=tuple(task.id for task in records if task.status is Status.IN_PROGRESS),
            auto_escalate=tasks.tickets.staged_ticket(slug).ticket.auto_escalate,
            blocked=blocked_tasks(tasks, slug, records),
        )


def not_proven_in_landing(
    commands: Sequence[RecordedCommand], receipts: Mapping[str, Receipt], head: str | None
) -> list[str]:
    passed_at_head = (
        receipts[command.id]
        for command in commands
        if receipt_problem(command.id, receipts.get(command.id), head) is None
    )
    return [
        f'{receipt.id} passed at HEAD in the {receipt.phase} phase, not the landing phase'
        for receipt in passed_at_head
        if receipt.phase is not Phase.LANDING
    ]


def landing_on_branch(state: OpenState) -> Landing:
    unclosed = unclosed_tickets_on_branch(ticket_store(state.database), state.git.current_branch())
    names = tuple(map(str, unclosed))
    if len(unclosed) != 1:
        return Landing(unclosed=names)
    slug = unclosed[0]
    head = state.git.resolve_head()
    with SqliteTaskStore(database=state.database).transaction() as tasks:
        records = tuple(records_of(tasks, slug).values())
        superseded = {record.id for record in records if record.status is Status.SUPERSEDED}
        live = [
            command
            for command in tasks.contracts.commands(slug)
            if command.task_id not in superseded
        ]
        receipts = tasks.contracts.latest_receipts(slug)
    unproven = (
        *readiness_problems(records),
        *receipt_problems(live, receipts, head),
        *not_proven_in_landing(live, receipts, head),
    )
    return Landing(unclosed=names, unproven=unproven)


@contextmanager
def state_for_hook(context: HookContext) -> Generator[OpenState]:
    with open_state(
        find_root(context.environ, context.cwd), context.data_directory(), ROW_TYPES
    ) as state:
        yield state


@dataclass(slots=True, kw_only=True, frozen=True)
class HookState:
    context: HookContext

    def ticket_directory_holds(self, file_path: str) -> bool:
        return self.context.ticket_directory_holds(file_path)

    def started_by(self, worker: Worker) -> StartedOrUnreadable:
        if not self.context.has_ticket_directory():
            return ()
        try:
            with state_for_hook(self.context) as state:
                return started_on_branch(state, Implementer(worker))
        except STATE_UNREADABLE as error:
            return error

    def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        if not self.context.has_ticket_directory():
            return BranchTickets()
        try:
            with state_for_hook(self.context) as state:
                return tickets_on_branch(state)
        except STATE_UNREADABLE as error:
            return error

    def landing_on_branch(self) -> LandingOrUnreadable:
        if not self.context.has_ticket_directory():
            return Landing()
        try:
            with state_for_hook(self.context) as state:
                return landing_on_branch(state)
        except STATE_UNREADABLE as error:
            return error
