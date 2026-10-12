"""The tasks a worker has in progress on the ticket whose branch is checked out, and the tickets
that are on it.

`started_on_branch` answers the tasks from open state: the in-progress tasks of that ticket whose
latest attempt was the worker's, in task order, each with the files it owns. A branch with no
ticket has none. This is the one place a hook learns what a started task owns.

`tickets_on_branch` answers every unclosed ticket on the checked-out branch and, when there is
exactly one, the tasks it has in progress, whoever started them.

`landing_on_branch` answers the same tickets and, when there is exactly one, what keeps it from
landing: every reason the `task` tool's `ready` action would give, read through the functions
`ready` reads them through, and every live contract command whose passing receipt at HEAD was not
taken in the landing phase. It writes nothing.

`started_for_hook`, `tickets_for_hook` and `landing_for_hook` are for a hook that holds no state.
Each opens the state the completion gate opens, from the project directory and the plugin data
directory Claude Code gives a hook, and answers the failure in place of the read when there is no
data directory, no git work tree, the database refuses, or the operating system refuses the data
directory, the database file or git's exclude file, so the hook decides what an unreadable state
means.
"""

from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError

from mightymodels_plugin.commands.branch_ticket import ticket_on_branch, unclosed_tickets_on_branch
from mightymodels_plugin.commands.dispatch_hook import (
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
from mightymodels_plugin.core.workspace import find_root
from mightymodels_plugin.tools.contract.schema import Phase, Receipt
from mightymodels_plugin.tools.contract.store import RecordedCommand
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.task.gates import (
    readiness_problems,
    receipt_problem,
    receipt_problems,
)
from mightymodels_plugin.tools.task.repository import SqliteTaskStore, in_progress_started_by
from mightymodels_plugin.tools.task.schema import Implementer, Status
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


def tickets_on_branch(state: OpenState) -> BranchTickets:
    unclosed = unclosed_tickets_on_branch(ticket_store(state.database), state.git.current_branch())
    names = tuple(map(str, unclosed))
    if len(unclosed) != 1:
        return BranchTickets(unclosed=names)
    with SqliteTaskStore(database=state.database).transaction() as tasks:
        in_progress = tuple(
            task.id for task in tasks.tasks(unclosed[0]) if task.status is Status.IN_PROGRESS
        )
    return BranchTickets(unclosed=names, in_progress=in_progress)


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


def started_for_hook(context: HookContext, worker: Worker) -> StartedOrUnreadable:
    try:
        with state_for_hook(context) as state:
            return started_on_branch(state, Implementer(worker))
    except STATE_UNREADABLE as error:
        return error


def tickets_for_hook(context: HookContext) -> BranchTicketsOrUnreadable:
    try:
        with state_for_hook(context) as state:
            return tickets_on_branch(state)
    except STATE_UNREADABLE as error:
        return error


def landing_for_hook(context: HookContext) -> LandingOrUnreadable:
    try:
        with state_for_hook(context) as state:
            return landing_on_branch(state)
    except STATE_UNREADABLE as error:
        return error
