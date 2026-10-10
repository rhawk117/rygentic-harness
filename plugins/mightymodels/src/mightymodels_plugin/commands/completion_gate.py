"""The `mightymodels completion-gate` command, which the SubagentStop hook on the implementers runs.

When `mightymodels:engineer` or `mightymodels:architect` stops while a task it started is still
in progress on the ticket whose branch is checked out, and the task's brief has no DONE half that
names a commit (a `commit: <hash>` line under `## DONE`), the stop is blocked once: the command
prints `{"decision": "block", "reason": ...}` and the subagent is sent back to finish. The reason
names each task and what its brief lacks. A fix, a recovery or a review task (`C` and `R` ids) has
no brief and is not held.

The gate keeps no marker of its own. Claude Code sets `stop_hook_active` on the stop that follows a
block, and the gate lets that one through, so a subagent that cannot finish is never trapped.

A worker with nothing in progress, any other agent type and a stop with no ticket, no data
directory, no git work tree or a refused database print nothing and exit 0; the last three say why
on standard error.
"""

import json
import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from mightymodels_plugin.commands.branch_ticket import ticket_on_branch
from mightymodels_plugin.commands.hook_context import HookContext, plugin_worker
from mightymodels_plugin.commands.rejection import skipped
from mightymodels_plugin.core.edge import OpenState, open_state
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Worker
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.task_id import is_plan_task, task_number
from mightymodels_plugin.core.workspace import find_root
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.task.gates import done_commit
from mightymodels_plugin.tools.task.repository import in_progress_started_by, task_transaction
from mightymodels_plugin.tools.task.schema import Implementer

IMPLEMENTERS = frozenset({Worker.ENGINEER, Worker.ARCHITECT})
STOP_HOOK_ACTIVE_KEY = 'stop_hook_active'
BRIEF_MISSING = 'its brief {brief} is missing'
NO_DONE_COMMIT = 'its brief {brief} has no DONE half naming a commit'


def brief_lack(brief: Path, shown: str) -> str | None:
    if not brief.is_file():
        return BRIEF_MISSING.format(brief=shown)
    if done_commit(brief.read_text(encoding='utf-8')) is None:
        return NO_DONE_COMMIT.format(brief=shown)
    return None


def unfinished_lines(state: OpenState, slug: Slug, worker: Implementer) -> list[str]:
    with task_transaction(state.database) as tasks:
        started = in_progress_started_by(tasks, slug, worker)
    lines: list[str] = []
    for task_id in filter(is_plan_task, started):
        brief = state.workspace.task_brief(slug, task_number(task_id))
        lack = brief_lack(brief, state.workspace.relative_to_root(brief))
        if lack is not None:
            lines.append(f'{task_id} is in progress and {lack}')
    return lines


def unfinished_reason(state: OpenState, worker: Implementer) -> str | None:
    slug = ticket_on_branch(state.database, state.workspace.git.current_branch())
    if slug is None:
        return None
    lines = unfinished_lines(state, slug, worker)
    if not lines:
        return None
    return (
        f'You are stopping with work unfinished on ticket {slug}: {"; ".join(lines)}. '
        'Append the `## DONE` half with a `commit: <hash>` line naming your commit, then report.'
    )


def run_hook(context: HookContext) -> int:
    fields = context.fields()
    if isinstance(fields, StateError):
        return skipped(fields)
    worker = plugin_worker(fields)
    if worker not in IMPLEMENTERS or fields.get(STOP_HOOK_ACTIVE_KEY) is True:
        return 0
    try:
        with open_state(
            find_root(context.environ, context.cwd), context.data_directory(), ROW_TYPES
        ) as state:
            reason = unfinished_reason(state, Implementer(worker))
    except (StateError, SQLAlchemyError) as error:
        return skipped(error)
    if reason is not None:
        sys.stdout.write(f'{json.dumps({"decision": "block", "reason": reason})}\n')
    return 0
