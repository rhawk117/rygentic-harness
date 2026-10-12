"""The tasks a worker has in progress on the ticket whose branch is checked out, and the tickets
that are on it.

`started_on_branch` answers the tasks from open state: the in-progress tasks of that ticket whose
latest attempt was the worker's, in task order, each with the files it owns. A branch with no
ticket has none. This is the one place a hook learns what a started task owns.

`tickets_on_branch` answers every unclosed ticket on the checked-out branch and, when there is
exactly one, the tasks it has in progress, whoever started them.

`started_for_hook` and `tickets_for_hook` are for a hook that holds no state. Each opens the state
the completion gate opens, from the project directory and the plugin data directory Claude Code
gives a hook, and answers the failure in place of the read when there is no data directory, no git
work tree, the database refuses, or the operating system refuses the data directory, the database
file or git's exclude file, so the hook decides what an unreadable state means.
"""

from collections.abc import Generator
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
from mightymodels_plugin.core.edge import OpenState, open_state
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Worker
from mightymodels_plugin.core.workspace import find_root
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.task.repository import SqliteTaskStore, in_progress_started_by
from mightymodels_plugin.tools.task.schema import Implementer, Status
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
