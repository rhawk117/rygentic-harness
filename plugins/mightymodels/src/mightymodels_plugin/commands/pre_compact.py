"""The `mightymodels pre-compact` command, which the PreCompact hook runs.

A compaction drops the conversation, so the command writes the snapshot of the ticket whose branch
is checked out before it runs: the same record and Markdown the `snapshot` tool serves, to the
ticket's `handoffs/snapshot.json` and `snapshot.md`, for the next turn to resume from. It reads the
state database and git and writes those two files. A detached HEAD, a branch no open ticket names
and a branch two open tickets name leave everything as it was.

The command never blocks a compaction: no data directory, no git work tree, a refused database or
an unwritable handoffs directory is said on standard error, with exit 0.
"""

from sqlalchemy.exc import SQLAlchemyError

from mightymodels_plugin.commands.branch_ticket import ticket_on_branch
from mightymodels_plugin.commands.hook_context import HookContext
from mightymodels_plugin.commands.rejection import skipped
from mightymodels_plugin.core.edge import OpenState, open_state
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.workspace import find_root
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.snapshot.schema import DEFAULT_LIMIT
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.tools.ticket.repository import ticket_store


def write_snapshot(state: OpenState) -> None:
    slug = ticket_on_branch(ticket_store(state.database), state.workspace.git.current_branch())
    if slug is None:
        return
    view = SnapshotService(workspace=state.workspace, database=state.database).take(
        slug, DEFAULT_LIMIT
    )
    files = state.workspace.handoffs.snapshot(slug)
    files.record.parent.mkdir(parents=True, exist_ok=True)
    files.record.write_text(f'{view.record.model_dump_json(indent=2)}\n', encoding='utf-8')
    files.markdown.write_text(view.markdown, encoding='utf-8')


def run_hook(context: HookContext) -> int:
    try:
        with open_state(
            find_root(context.environ, context.cwd), context.data_directory(), ROW_TYPES
        ) as state:
            write_snapshot(state)
    except (StateError, SQLAlchemyError, OSError) as error:
        return skipped(error)
    return 0
