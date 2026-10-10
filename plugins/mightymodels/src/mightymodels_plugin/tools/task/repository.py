"""A ticket's tasks, their attempts and their transitions, reached only through a repository.

`task_transaction` opens one transaction on the database and hands out the task repository, so the
task service never sees a session. A task action also reads the ticket's row and the ticket's
contract, so the repository carries a `TicketRepository` and a `ContractRepository`, both built
here on that same session and nowhere else: one transaction serves the three. All three hold the
key of the git repository the database was opened for, and every read and write is under it.

A method that changes a task takes the transition the change is part of and stores the
transition's row with it, so no task moves without its record.

A ticket's tasks are read whole, and the read is refused once a ticket holds more than `TASKS`.
`record_start` is the only write that adds a task, and it is refused with `WriteLimitError` when
the ticket would hold more than `TASKS`: the task, its attempt and its transition are not stored.
The attempts are counted by the database, so a read fetches one row per task and worker however
many attempts there were, and `latest_transitions_into` fetches only the transitions it is asked
for.

A task's failed fixes are read whole, up to `FAILED_FIX_LIMIT`, the most the service lets it hold.

`in_progress_started_by` answers the in-progress tasks whose latest attempt was a worker's, so a
hook that sees a worker stop can tell which tasks it left open.

A task's base is the HEAD of its first start that had one. A restart keeps it, so what the task
changed is measured from where its first attempt began.
"""

from collections.abc import Collection, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database, ReadLimit
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.contract.repository import ContractRepository
from mightymodels_plugin.tools.task.schema import ArchitectMode, Implementer, Status
from mightymodels_plugin.tools.task.tables import AttemptRow, FailedFixRow, TaskRow, TransitionRow
from mightymodels_plugin.tools.ticket.repository import TicketRepository

type AttemptCounts = dict[str, dict[str, int]]

TASKS = ReadLimit(rows=1000, kept='tasks')
ATTEMPT_COUNTS = ReadLimit(rows=TASKS.rows * len(Implementer), kept='attempt counts')
FAILED_FIX_LIMIT = 3
FAILED_FIXES = ReadLimit(rows=FAILED_FIX_LIMIT, kept='failed fixes')


@dataclass(slots=True, kw_only=True, frozen=True)
class Transition:
    task_id: str
    before: Status
    after: Status
    reasons: Sequence[str]
    head: str | None
    at: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Attempt:
    worker: Implementer
    mode: ArchitectMode | None
    owned: Sequence[str]


def transition_row(
    slug: Slug, transition: Transition, *, repository_key: RepositoryKey
) -> TransitionRow:
    return TransitionRow(
        repository_key=repository_key.root,
        slug=slug.root,
        task_id=transition.task_id,
        before=transition.before,
        after=transition.after,
        reasons=list(transition.reasons),
        head=transition.head,
        at=transition.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskRepository:
    session: Session
    repository_key: RepositoryKey
    tickets: TicketRepository
    contracts: ContractRepository

    def row(self, slug: Slug, task_id: str) -> TaskRow | None:
        return self.session.get(TaskRow, (self.repository_key.root, slug.root, task_id))

    def rows(self, slug: Slug) -> list[TaskRow]:
        query = (
            select(TaskRow)
            .where(TaskRow.repository_key == self.repository_key.root, TaskRow.slug == slug.root)
            .limit(TASKS.fetched)
        )
        rows = list(self.session.scalars(query))
        if (error := TASKS.error(rows, owner=f'ticket {slug}')) is not None:
            raise error
        return rows

    def attempts_by_worker(self, slug: Slug) -> AttemptCounts:
        query = (
            select(AttemptRow.task_id, AttemptRow.worker, func.count())
            .where(
                AttemptRow.repository_key == self.repository_key.root,
                AttemptRow.slug == slug.root,
            )
            .group_by(AttemptRow.task_id, AttemptRow.worker)
            .order_by(func.min(AttemptRow.id))
            .limit(ATTEMPT_COUNTS.fetched)
        )
        rows = self.session.execute(query).all()
        if (error := ATTEMPT_COUNTS.error(rows, owner=f'ticket {slug}')) is not None:
            raise error
        counts: AttemptCounts = {}
        for task_id, worker, attempts in rows:
            counts.setdefault(task_id, {})[worker] = attempts
        return counts

    def attempts_in_modes(self, slug: Slug, task_id: str, modes: Collection[ArchitectMode]) -> int:
        query = (
            select(func.count())
            .select_from(AttemptRow)
            .where(
                AttemptRow.repository_key == self.repository_key.root,
                AttemptRow.slug == slug.root,
                AttemptRow.task_id == task_id,
                AttemptRow.mode.in_(sorted(modes)),
            )
        )
        return self.session.scalars(query).one()

    def failed_fixes(self, slug: Slug, task_id: str) -> list[str]:
        query = (
            select(FailedFixRow.hypothesis)
            .where(
                FailedFixRow.repository_key == self.repository_key.root,
                FailedFixRow.slug == slug.root,
                FailedFixRow.task_id == task_id,
            )
            .order_by(FailedFixRow.id)
            .limit(FAILED_FIXES.fetched)
        )
        hypotheses = list(self.session.scalars(query))
        error = FAILED_FIXES.error(hypotheses, owner=f'task {task_id} of ticket {slug}')
        if error is not None:
            raise error
        return hypotheses

    def latest_transitions_into(
        self, slug: Slug, statuses: Collection[Status], limit: int
    ) -> list[TransitionRow]:
        query = (
            select(TransitionRow)
            .where(
                TransitionRow.repository_key == self.repository_key.root,
                TransitionRow.slug == slug.root,
                TransitionRow.after.in_(sorted(statuses)),
            )
            .order_by(TransitionRow.id.desc())
            .limit(limit)
        )
        return list(reversed(self.session.scalars(query).all()))

    def record_start(self, slug: Slug, transition: Transition, attempt: Attempt) -> None:
        started = self.row(slug, transition.task_id)
        first_base = None if started is None else started.base
        self.session.merge(
            TaskRow(
                repository_key=self.repository_key.root,
                slug=slug.root,
                task_id=transition.task_id,
                status=transition.after,
                owned=list(attempt.owned),
                base=transition.head if first_base is None else first_base,
                commit=None,
                reasons=[],
                updated_at=transition.at,
            )
        )
        self.session.add(
            AttemptRow(
                repository_key=self.repository_key.root,
                slug=slug.root,
                task_id=transition.task_id,
                worker=attempt.worker,
                mode=attempt.mode,
                at=transition.at,
            )
        )
        self.session.add(transition_row(slug, transition, repository_key=self.repository_key))
        self.session.flush()
        held = (
            select(func.count())
            .select_from(TaskRow)
            .where(TaskRow.repository_key == self.repository_key.root, TaskRow.slug == slug.root)
        )
        error = TASKS.write_error(self.session.scalars(held).one(), owner=f'ticket {slug}')
        if error is not None:
            raise error

    def record_failed_fix(self, slug: Slug, task_id: str, hypothesis: str, *, at: str) -> None:
        self.session.add(
            FailedFixRow(
                repository_key=self.repository_key.root,
                slug=slug.root,
                task_id=task_id,
                hypothesis=hypothesis,
                at=at,
            )
        )

    def record_verification(self, slug: Slug, transition: Transition, commit: str) -> None:
        row = self.session.get_one(
            TaskRow, (self.repository_key.root, slug.root, transition.task_id)
        )
        row.status = transition.after
        row.commit = commit
        row.reasons = list(transition.reasons)
        row.updated_at = transition.at
        self.session.add(transition_row(slug, transition, repository_key=self.repository_key))

    def record_mark(self, slug: Slug, transition: Transition) -> None:
        row = self.session.get_one(
            TaskRow, (self.repository_key.root, slug.root, transition.task_id)
        )
        row.status = transition.after
        row.reasons = list(transition.reasons)
        row.updated_at = transition.at
        self.session.add(transition_row(slug, transition, repository_key=self.repository_key))


def in_progress_started_by(
    repository: TaskRepository, slug: Slug, worker: Implementer
) -> list[str]:
    latest_attempts = (
        select(func.max(AttemptRow.id))
        .where(
            AttemptRow.repository_key == repository.repository_key.root,
            AttemptRow.slug == slug.root,
        )
        .group_by(AttemptRow.task_id)
    )
    query = (
        select(TaskRow.task_id)
        .join(
            AttemptRow,
            and_(
                AttemptRow.repository_key == TaskRow.repository_key,
                AttemptRow.slug == TaskRow.slug,
                AttemptRow.task_id == TaskRow.task_id,
            ),
        )
        .where(
            TaskRow.repository_key == repository.repository_key.root,
            TaskRow.slug == slug.root,
            TaskRow.status == Status.IN_PROGRESS,
            AttemptRow.worker == worker,
            AttemptRow.id.in_(latest_attempts),
        )
        .order_by(TaskRow.task_id)
        .limit(TASKS.fetched)
    )
    return list(repository.session.scalars(query))


@contextmanager
def task_transaction(database: Database) -> Generator[TaskRepository]:
    with database.transaction() as session:
        repository_key = database.repository_key
        yield TaskRepository(
            session=session,
            repository_key=repository_key,
            tickets=TicketRepository(session=session, repository_key=repository_key),
            contracts=ContractRepository(session=session, repository_key=repository_key),
        )
