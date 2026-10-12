"""The tasks a worker has in progress on the ticket whose branch is checked out.

`started_on_branch` answers them from open state: the in-progress tasks of that ticket whose latest
attempt was the worker's, in task order, each with the files it owns. A branch with no ticket has
none. This is the one place a hook learns what a started task owns.

`started_for_hook` is for a hook that holds no state. It opens the state the completion gate
opens, from the project directory and the plugin data directory Claude Code gives a hook, and
answers the failure in place of the tasks when there is no data directory, no git work tree, the
database refuses, or the operating system refuses the data directory, the database file or git's
exclude file, so the hook decides what an unreadable state means.
"""

from sqlalchemy.exc import SQLAlchemyError

from mightymodels_plugin.commands.branch_ticket import ticket_on_branch
from mightymodels_plugin.commands.dispatch_hook import StartedOrUnreadable, StartedTask
from mightymodels_plugin.commands.hook_context import HookContext
from mightymodels_plugin.core.edge import OpenState, open_state
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Worker
from mightymodels_plugin.core.workspace import find_root
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.task.repository import SqliteTaskStore, in_progress_started_by
from mightymodels_plugin.tools.task.schema import Implementer
from mightymodels_plugin.tools.ticket.repository import ticket_store


def started_on_branch(state: OpenState, worker: Implementer) -> list[StartedTask]:
    slug = ticket_on_branch(ticket_store(state.database), state.git.current_branch())
    if slug is None:
        return []
    with SqliteTaskStore(database=state.database).transaction() as tasks:
        owned = {task.id: task.owned for task in tasks.tasks(slug)}
        started = in_progress_started_by(tasks, slug, worker)
    return [StartedTask(id=task_id, owned=owned[task_id]) for task_id in started]


def started_for_hook(context: HookContext, worker: Worker) -> StartedOrUnreadable:
    try:
        with open_state(
            find_root(context.environ, context.cwd), context.data_directory(), ROW_TYPES
        ) as state:
            return started_on_branch(state, Implementer(worker))
    except (StateError, SQLAlchemyError, OSError) as error:
        return error
