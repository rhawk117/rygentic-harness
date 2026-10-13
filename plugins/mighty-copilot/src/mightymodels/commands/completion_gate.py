"""The `mightymodels completion-gate` command, which the SubagentStop hook on the implementers runs.

When `mightymodels:workers:engineer`, `mightymodels:workers:architect` or
`mightymodels:workers:intern` stops while a task it started is still in progress on the ticket
whose branch is checked out, and the task's brief has no DONE half that names a commit (a
`commit: <hash>` line under `## DONE`), the stop is blocked once: the command prints
`{"decision": "block", "reason": ...}` and the subagent is sent back to finish. The reason names
each task and what its brief lacks.

A residual (an `R` id) has no brief and is held on the rest of what verifies a task: a commit
follows its base, each contract command of its own passed at HEAD, and the commits since its base
touched only the files it owns. The reason names each residual and which of the three it lacks. A
fix for a failing CI check (a `C` id) is not held.

The gate keeps no marker of its own. Claude Code sets `stop_hook_active` on the stop that follows a
block, and the gate lets that one through, so a subagent that cannot finish is never trapped.

A worker with nothing in progress, any other agent type and a stop with no ticket, no data
directory, no git work tree or a refused database print nothing and exit 0; the last three say why
on standard error.
"""

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from mightymodels.commands.branch_ticket import ticket_on_branch
from mightymodels.commands.hook_context import HookContext, plugin_worker
from mightymodels.commands.rejection import skipped
from mightymodels.core.codec import encode_compact
from mightymodels.core.database import Database
from mightymodels.core.edge import OpenState, open_state
from mightymodels.core.errors import StateError
from mightymodels.core.routing import Worker
from mightymodels.core.slug import Slug
from mightymodels.core.task_id import is_plan_task, task_number
from mightymodels.core.workspace import GitQueries, Workspace
from mightymodels.tools.contract.schema import Receipt
from mightymodels.tools.contract.store import RecordedCommand
from mightymodels.tools.row_types import ROW_TYPES
from mightymodels.tools.task.gates import (
    commit_problems,
    done_commit,
    ownership_problems,
    receipt_problems,
)
from mightymodels.tools.task.repository import SqliteTaskStore, in_progress_started_by
from mightymodels.tools.task.schema import Implementer, TaskRecord
from mightymodels.tools.ticket.repository import ticket_store

IMPLEMENTERS = frozenset({Worker.ENGINEER, Worker.ARCHITECT, Worker.INTERN})
STOP_HOOK_ACTIVE_KEY = 'stop_hook_active'
RESIDUAL = 'R'
BRIEF_MISSING = 'its brief {brief} is missing'
NO_DONE_COMMIT = 'its brief {brief} has no DONE half naming a commit'
NOTHING_COMMITTED = 'no commit follows its base'
FINISH_A_PLAN_TASK = (
    'Append the `## DONE` half with a `commit: <hash>` line naming your commit, then report.'
)
FINISH_A_RESIDUAL = (
    'Commit the fix inside the files the residual owns and take each receipt named with '
    '`mightymodels verify run --slug {slug} --id <id>`, then report.'
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Started:
    plan_tasks: Sequence[str]
    residuals: Sequence[TaskRecord]
    commands: Sequence[RecordedCommand]
    receipts: Mapping[str, Receipt]


def is_residual(task_id: str) -> bool:
    return task_id.startswith(RESIDUAL)


def started_by(database: Database, slug: Slug, worker: Implementer) -> Started:
    with SqliteTaskStore(database=database).transaction() as tasks:
        started = in_progress_started_by(tasks, slug, worker)
        records = (tasks.task(slug, task_id) for task_id in filter(is_residual, started))
        return Started(
            plan_tasks=list(filter(is_plan_task, started)),
            residuals=[record for record in records if record is not None],
            commands=tasks.contracts.commands(slug),
            receipts=tasks.contracts.latest_receipts(slug),
        )


def brief_lack(brief: Path, shown: str) -> str | None:
    if not brief.is_file():
        return BRIEF_MISSING.format(brief=shown)
    if done_commit(brief.read_text(encoding='utf-8')) is None:
        return NO_DONE_COMMIT.format(brief=shown)
    return None


def brief_lines(workspace: Workspace, slug: Slug, plan_tasks: Sequence[str]) -> list[str]:
    lines: list[str] = []
    for task_id in plan_tasks:
        brief = workspace.task_brief(slug, task_number(task_id))
        lack = brief_lack(brief, workspace.relative_to_root(brief))
        if lack is not None:
            lines.append(f'{task_id} is in progress and {lack}')
    return lines


def residual_problems(git: GitQueries, residual: TaskRecord, started: Started) -> list[str]:
    head = git.resolve_head()
    if head is None:
        return [NOTHING_COMMITTED]
    base = residual.base
    problems = commit_problems(git, base, head)
    if problems or base is None:
        return problems
    if git.resolve_commit(base) == head:
        return [NOTHING_COMMITTED]
    commands = [command for command in started.commands if command.task_id == residual.id]
    return [
        *receipt_problems(commands, started.receipts, head),
        *ownership_problems(git, residual, base=base, commit=head),
    ]


def residual_lines(git: GitQueries, started: Started) -> list[str]:
    lines: list[str] = []
    for residual in started.residuals:
        problems = residual_problems(git, residual, started)
        if problems:
            lines.append(f'{residual.id} is in progress and {", ".join(problems)}')
    return lines


def unfinished_reason(state: OpenState, worker: Implementer) -> str | None:
    slug = ticket_on_branch(ticket_store(state.database), state.git.current_branch())
    if slug is None:
        return None
    started = started_by(state.database, slug, worker)
    briefs = brief_lines(state.workspace, slug, started.plan_tasks)
    residuals = residual_lines(state.git, started)
    if not briefs and not residuals:
        return None
    remedies = [
        *([FINISH_A_PLAN_TASK] if briefs else []),
        *([FINISH_A_RESIDUAL.format(slug=slug)] if residuals else []),
    ]
    return (
        f'You are stopping with work unfinished on ticket {slug}: '
        f'{"; ".join([*briefs, *residuals])}. {" ".join(remedies)}'
    )


def run_hook(context: HookContext) -> int:
    fields = context.fields()
    if isinstance(fields, StateError):
        return skipped(fields)
    worker = plugin_worker(fields)
    if worker not in IMPLEMENTERS or fields.get(STOP_HOOK_ACTIVE_KEY) is True:
        return 0
    try:
        with open_state(context.cwd, context.data_directory(), ROW_TYPES) as state:
            reason = unfinished_reason(state, Implementer(worker))
    except (StateError, SQLAlchemyError) as error:
        return skipped(error)
    if reason is not None:
        sys.stdout.buffer.write(encode_compact({'decision': 'block', 'reason': reason}) + b'\n')
    return 0
