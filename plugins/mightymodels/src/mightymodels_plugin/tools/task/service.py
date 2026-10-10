"""The task service: per-task state, gated, and durable before anything advances.

Every transition is checked and stored with its transition row in one transaction, and puts the
ticket in progress. `start` records an attempt and the HEAD it starts from, `verify` moves a task
to verified or blocked on the proof in `gates.py`, `mark` closes or parks one with a reason,
`record_failed_fix` stores the hypothesis of a fix that failed, up to `FAILED_FIX_LIMIT` per task,
and refuses the next with the hypotheses tried, `show` lists a ticket's tasks and `ready` is the
gate before any push.

A closed ticket is final. `start`, `verify` and `mark` refuse one before they read a task, and
`show` and `ready` still answer for it.

The ladder is the skills': an engineer attempt, one architect implementation attempt, one
more in systemic-refactor mode after an approved scope expansion, which may take over a task
that is still in progress, and diagnose-replan passes that never count against the limit. A
replanned task closes as superseded, which `ready` treats as closed.

The service is built once by whoever owns the workspace and the database, the server in its
lifespan, and holds both. Each action opens one transaction through `task_transaction`, which
hands it the task repository and, on that repository, the ticket's row and the ticket's contract.
Everything above the class reads no service state.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.declarative import PROSE_LIMIT
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.task_id import is_plan_task, task_number
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.head import short_head
from mightymodels_plugin.redaction import redact_within
from mightymodels_plugin.tools.failed_fix.schema import TaskFailedFix
from mightymodels_plugin.tools.task.errors import FixesSpentError, FixNotUnderwayError
from mightymodels_plugin.tools.task.gates import (
    Evidence,
    readiness_problems,
    receipt_problems,
    verification_problems,
)
from mightymodels_plugin.tools.task.repository import (
    FAILED_FIX_LIMIT,
    Attempt,
    TaskRepository,
    Transition,
    task_transaction,
)
from mightymodels_plugin.tools.task.schema import (
    ArchitectMode,
    Implementer,
    Status,
    TaskMark,
    TaskRecord,
    TaskStart,
    TaskVerification,
    TaskView,
)
from mightymodels_plugin.tools.task.tables import TaskRow

ARCHITECT_LIMIT = 1

TERMINAL = frozenset[Status]()
ALLOWED: Mapping[Status, frozenset[Status]] = MappingProxyType(
    {
        Status.PENDING: frozenset({Status.IN_PROGRESS}),
        Status.IN_PROGRESS: frozenset(
            {Status.VERIFIED, Status.FAILED, Status.BLOCKED, Status.SUPERSEDED}
        ),
        Status.FAILED: frozenset({Status.IN_PROGRESS, Status.SUPERSEDED}),
        Status.BLOCKED: frozenset({Status.IN_PROGRESS, Status.SUPERSEDED}),
        Status.VERIFIED: TERMINAL,
        Status.SUPERSEDED: TERMINAL,
    }
)
IMPLEMENTATION_MODES = frozenset(
    {ArchitectMode.RECOVERY_IMPLEMENTATION, ArchitectMode.SYSTEMIC_REFACTOR}
)


class TransitionError(StateError):
    def __init__(self, task_id: str, current: Status, target: Status) -> None:
        super().__init__(f'{task_id} cannot move from {current} to {target}')
        self.task_id = task_id
        self.current = current
        self.target = target


class ArchitectSpentError(StateError):
    def __init__(self, task_id: str) -> None:
        super().__init__(
            f'{task_id} already had its architect recovery; route it to whats-broken, start it '
            f'in {ArchitectMode.SYSTEMIC_REFACTOR} mode after the user approves a scope '
            f'expansion, or in {ArchitectMode.DIAGNOSE_REPLAN} mode for a revised contract'
        )
        self.task_id = task_id


class ModeNeedsArchitectError(StateError):
    def __init__(self, mode: ArchitectMode) -> None:
        super().__init__(f'{mode} is an architect mode; start the task by architect to use it')
        self.mode = mode


def task_order(record: TaskRecord) -> tuple[bool, int]:
    return not is_plan_task(record.id), task_number(record.id)


def status_of(row: TaskRow | None) -> Status:
    return Status.PENDING if row is None else Status(row.status)


def record_of(row: TaskRow, attempts: dict[str, int]) -> TaskRecord:
    return TaskRecord(
        id=row.task_id,
        status=Status(row.status),
        owned=tuple(row.owned),
        base=row.base,
        commit=row.commit,
        attempts=attempts,
        reasons=tuple(row.reasons),
    )


def records_of(repository: TaskRepository, slug: Slug) -> dict[str, TaskRecord]:
    attempts = repository.attempts_by_worker(slug)
    started = [record_of(row, attempts.get(row.task_id, {})) for row in repository.rows(slug)]
    known = {record.id for record in started}
    planned = {
        command.task_id
        for command in repository.contracts.commands(slug)
        if command.task_id is not None and is_plan_task(command.task_id)
    }
    pending = [TaskRecord(id=task_id, status=Status.PENDING) for task_id in planned - known]
    return {record.id: record for record in sorted([*started, *pending], key=task_order)}


def fix_error(
    task_id: str, before: Status, tried: Sequence[str]
) -> FixNotUnderwayError | FixesSpentError | None:
    if before is not Status.IN_PROGRESS:
        return FixNotUnderwayError(task_id, before)
    if len(tried) >= FAILED_FIX_LIMIT:
        return FixesSpentError(task_id, tried)
    return None


def mode_error(change: TaskStart) -> ModeNeedsArchitectError | None:
    if change.by is Implementer.ARCHITECT or change.mode is None:
        return None
    return ModeNeedsArchitectError(change.mode)


def architect_mode(change: TaskStart) -> ArchitectMode | None:
    if change.by is not Implementer.ARCHITECT:
        return None
    return ArchitectMode.RECOVERY_IMPLEMENTATION if change.mode is None else change.mode


def spent_error(task_id: str, mode: ArchitectMode | None, spent: int) -> ArchitectSpentError | None:
    limit = ARCHITECT_LIMIT + int(mode is ArchitectMode.SYSTEMIC_REFACTOR)
    if mode in IMPLEMENTATION_MODES and spent >= limit:
        return ArchitectSpentError(task_id)
    return None


def start_error(task_id: str, before: Status, mode: ArchitectMode | None) -> TransitionError | None:
    expanded = mode is ArchitectMode.SYSTEMIC_REFACTOR
    if Status.IN_PROGRESS in ALLOWED[before] or (expanded and before is Status.IN_PROGRESS):
        return None
    return TransitionError(task_id, before, Status.IN_PROGRESS)


def start_reasons(worker: Implementer, mode: ArchitectMode | None) -> list[str]:
    return [f'by {worker}', *([] if mode is None else [f'in {mode} mode'])]


def problem_lines(problems: Sequence[str]) -> str:
    return ''.join(f'  - {problem}\n' for problem in problems)


def record_line(record: TaskRecord) -> str:
    reasons = '; '.join(record.reasons)
    return f'{record.id}\t{record.status}\tattempts {record.attempts}\t{reasons}\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskService:
    workspace: Workspace
    database: Database

    def evidence_for(
        self, repository: TaskRepository, slug: Slug, *, task_id: str, change: TaskVerification
    ) -> Evidence:
        commit = self.workspace.git.resolve_commit(change.commit)
        planned = is_plan_task(task_id)
        return Evidence(
            commit=change.commit if commit is None else commit,
            brief=self.workspace.task_brief(slug, task_number(task_id)) if planned else None,
            assertions=change.assertions,
            commands=[
                command
                for command in repository.contracts.commands(slug)
                if command.task_id == task_id
            ],
            receipts=repository.contracts.latest_receipts(slug),
        )

    def start(self, slug: Slug, task_id: str, change: TaskStart) -> TaskView:
        with task_transaction(self.database) as repository:
            repository.tickets.unclosed_row(slug)
            if (error := mode_error(change)) is not None:
                raise error
            mode = architect_mode(change)
            spent = repository.attempts_in_modes(slug, task_id, IMPLEMENTATION_MODES)
            if (error := spent_error(task_id, mode, spent)) is not None:
                raise error
            before = status_of(repository.row(slug, task_id))
            if (error := start_error(task_id, before, mode)) is not None:
                raise error
            head = self.workspace.git.resolve_head()
            transition = Transition(
                task_id=task_id,
                before=before,
                after=Status.IN_PROGRESS,
                reasons=start_reasons(change.by, mode),
                head=head,
                at=now(),
            )
            attempt = Attempt(worker=change.by, mode=mode, owned=sorted(set(change.owned)))
            repository.tickets.mark_in_progress(slug)
            repository.record_start(slug, transition, attempt)
            record = records_of(repository, slug)[task_id]
        text = f'{task_id} in-progress by {change.by} from {short_head(head)}\n'
        return TaskView(text=text, advanced=True, tasks=(record,))

    def verify(self, slug: Slug, task_id: str, change: TaskVerification) -> TaskView:
        with task_transaction(self.database) as repository:
            repository.tickets.unclosed_row(slug)
            row = repository.row(slug, task_id)
            before = status_of(row)
            if row is None or Status.VERIFIED not in ALLOWED[before]:
                raise TransitionError(task_id, before, Status.VERIFIED)
            if (refusal := self.workspace.git.refusal()) is not None:
                raise refusal
            head = self.workspace.git.resolve_head()
            evidence = self.evidence_for(repository, slug, task_id=task_id, change=change)
            problems = verification_problems(self.workspace.git, row, evidence)
            after = Status.BLOCKED if problems else Status.VERIFIED
            transition = Transition(
                task_id=task_id, before=before, after=after, reasons=problems, head=head, at=now()
            )
            repository.tickets.mark_in_progress(slug)
            repository.record_verification(slug, transition, evidence.commit)
            record = records_of(repository, slug)[task_id]
        return TaskView(
            text=f'{task_id} {after}\n{problem_lines(problems)}',
            advanced=not problems,
            tasks=(record,),
        )

    def mark(self, slug: Slug, task_id: str, change: TaskMark) -> TaskView:
        with task_transaction(self.database) as repository:
            repository.tickets.unclosed_row(slug)
            row = repository.row(slug, task_id)
            before = status_of(row)
            if row is None or change.to not in ALLOWED[before]:
                raise TransitionError(task_id, before, change.to)
            transition = Transition(
                task_id=task_id,
                before=before,
                after=change.to,
                reasons=[change.reason],
                head=None,
                at=now(),
            )
            repository.tickets.mark_in_progress(slug)
            repository.record_mark(slug, transition)
            record = records_of(repository, slug)[task_id]
        text = f'{task_id} {change.to}: {change.reason}\n'
        return TaskView(text=text, advanced=True, tasks=(record,))

    def record_failed_fix(self, slug: Slug, task_id: str, change: TaskFailedFix) -> TaskView:
        hypothesis = redact_within(change.hypothesis, 'hypothesis', PROSE_LIMIT)
        with task_transaction(self.database) as repository:
            repository.tickets.unclosed_row(slug)
            before = status_of(repository.row(slug, task_id))
            tried = repository.failed_fixes(slug, task_id)
            if (error := fix_error(task_id, before, tried)) is not None:
                raise error
            repository.record_failed_fix(slug, task_id, hypothesis, at=now())
            record = records_of(repository, slug)[task_id]
        left = FAILED_FIX_LIMIT - len(tried) - 1
        text = f'{task_id} failed fix {len(tried) + 1} recorded: {hypothesis}\n{left} left\n'
        return TaskView(text=text, advanced=False, tasks=(record,))

    def show(self, slug: Slug) -> TaskView:
        with task_transaction(self.database) as repository:
            repository.tickets.staged_row(slug)
            records = tuple(records_of(repository, slug).values())
        text = ''.join(map(record_line, records))
        return TaskView(text=text or 'no tasks started\n', advanced=True, tasks=records)

    def ready(self, slug: Slug) -> TaskView:
        with task_transaction(self.database) as repository:
            repository.tickets.staged_row(slug)
            head = self.workspace.git.resolve_head()
            records = tuple(records_of(repository, slug).values())
            superseded = {record.id for record in records if record.status is Status.SUPERSEDED}
            live = [
                command
                for command in repository.contracts.commands(slug)
                if command.task_id not in superseded
            ]
            problems = [
                *readiness_problems(records),
                *receipt_problems(live, repository.contracts.latest_receipts(slug), head),
            ]
        if not problems:
            return TaskView(text=f'ready at {short_head(head)}\n', advanced=True, tasks=records)
        text = f'not ready\n{problem_lines(problems)}'
        return TaskView(text=text, advanced=False, tasks=records)
