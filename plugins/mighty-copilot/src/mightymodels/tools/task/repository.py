"""A ticket's tasks, their attempts and their transitions, reached only through a repository.

`SqliteTaskStore` is the task store over the database: its `transaction` opens one and hands out
the task repository, so the task service never sees a session, and `task_store` builds it as the
`TaskStore` a service holds. A task action also reads the ticket and the ticket's contract, so the
repository carries a `SqliteTicketRepository` and a `SqliteContractRepository`, both built here on
that same session and nowhere else: one transaction serves the three. All three hold the key of
the git repository the database was opened for, and every read and write is under it.

No row leaves the repository: a task is handed out as a `TaskRecord` and a transition as the
`Transition` it was written from.

A method that changes a task takes the transition the change is part of and stores the
transition's row with it, so no task moves without its record.

A ticket's tasks are read whole, and the read is refused once a ticket holds more than `TASKS`.
`record_start` adds a task, and so does `record_mark` when it closes one that never started. Either
is refused with `WriteLimitError` when the ticket would hold more than `TASKS`: the task, its
attempt and its transition are not stored.
The attempts are counted by the database, so a read fetches one row per task and worker however
many attempts there were, and `latest_transitions_into` fetches only the transitions it is asked
for.

A task's failed fixes are read whole, up to `FAILED_FIX_LIMIT`, the most the service lets it hold.

`in_progress_started_by` answers the in-progress tasks whose latest attempt was a worker's, so a
hook that sees a worker stop can tell which tasks it left open. It is a query over the SQLite
repository and not a method of the seam, since only that hook asks it.
`latest_transition_of_each_task_into` is the same kind of query for the dispatch hook: each task's
latest move into one of the statuses named, one row a task however many moves it made.

A task's base is the HEAD of its first start that had one. A restart keeps it, so what the task
changed is measured from where its first attempt began.
"""

from collections.abc import Collection, Generator
from contextlib import contextmanager
from dataclasses import dataclass

import sqlalchemy as sql
from sqlalchemy.orm import Session

from mightymodels.core.database import Database, ReadLimit, WriteLimitError
from mightymodels.core.repository_key import RepositoryKey
from mightymodels.core.slug import Slug
from mightymodels.tools.contract.repository import SqliteContractRepository
from mightymodels.tools.task.schema import ArchitectMode, Implementer, Status, TaskRecord
from mightymodels.tools.task.store import Attempt, AttemptCounts, TaskStore, Transition
from mightymodels.tools.task.tables import AttemptRow, FailedFixRow, TaskRow, TransitionRow
from mightymodels.tools.ticket.repository import SqliteTicketRepository

TASKS = ReadLimit(rows=1000, kept='tasks')
ATTEMPT_COUNTS = ReadLimit(rows=TASKS.rows * len(Implementer), kept='attempt counts')
FAILED_FIX_LIMIT = 3
FAILED_FIXES = ReadLimit(rows=FAILED_FIX_LIMIT, kept='failed fixes')


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


def task_record(row: TaskRow) -> TaskRecord:
    return TaskRecord(
        id=row.task_id,
        status=Status(row.status),
        owned=tuple(row.owned),
        base=row.base,
        commit=row.commit,
        reasons=tuple(row.reasons),
    )


def transition_of(row: TransitionRow) -> Transition:
    return Transition(
        task_id=row.task_id,
        before=Status(row.before),
        after=Status(row.after),
        reasons=tuple(row.reasons),
        head=row.head,
        at=row.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteTaskRepository:
    session: Session
    repository_key: RepositoryKey
    tickets: SqliteTicketRepository
    contracts: SqliteContractRepository

    def task(self, slug: Slug, task_id: str) -> TaskRecord | None:
        row = self.session.get(TaskRow, (self.repository_key.root, slug.root, task_id))
        return None if row is None else task_record(row)

    def tasks(self, slug: Slug) -> list[TaskRecord]:
        query = (
            sql.select(TaskRow)
            .where(TaskRow.repository_key == self.repository_key.root, TaskRow.slug == slug.root)
            .limit(TASKS.fetched)
        )
        rows = list(self.session.scalars(query))
        if (error := TASKS.error(rows, owner=f'ticket {slug}')) is not None:
            raise error
        return list(map(task_record, rows))

    def attempts_by_worker(self, slug: Slug) -> AttemptCounts:
        query = (
            sql.select(AttemptRow.task_id, AttemptRow.worker, sql.func.count())
            .where(
                AttemptRow.repository_key == self.repository_key.root,
                AttemptRow.slug == slug.root,
            )
            .group_by(AttemptRow.task_id, AttemptRow.worker)
            .order_by(sql.func.min(AttemptRow.id))
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
            sql.select(sql.func.count())
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
            sql.select(FailedFixRow.hypothesis)
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
    ) -> list[Transition]:
        query = (
            sql.select(TransitionRow)
            .where(
                TransitionRow.repository_key == self.repository_key.root,
                TransitionRow.slug == slug.root,
                TransitionRow.after.in_(sorted(statuses)),
            )
            .order_by(TransitionRow.id.desc())
            .limit(limit)
        )
        return list(map(transition_of, reversed(self.session.scalars(query).all())))

    def record_start(self, slug: Slug, transition: Transition, attempt: Attempt) -> None:
        started = self.task(slug, transition.task_id)
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
        if (error := tasks_held_error(self, slug)) is not None:
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
        started = self.task(slug, transition.task_id)
        never_started = TaskRecord(id=transition.task_id, status=transition.before)
        held = never_started if started is None else started
        self.session.merge(
            TaskRow(
                repository_key=self.repository_key.root,
                slug=slug.root,
                task_id=transition.task_id,
                status=transition.after,
                owned=list(held.owned),
                base=held.base,
                commit=held.commit,
                reasons=list(transition.reasons),
                updated_at=transition.at,
            )
        )
        self.session.add(transition_row(slug, transition, repository_key=self.repository_key))
        if (error := tasks_held_error(self, slug)) is not None:
            raise error


def tasks_held_error(repository: SqliteTaskRepository, slug: Slug) -> WriteLimitError | None:
    repository.session.flush()
    held = (
        sql.select(sql.func.count())
        .select_from(TaskRow)
        .where(TaskRow.repository_key == repository.repository_key.root, TaskRow.slug == slug.root)
    )
    return TASKS.write_error(repository.session.scalars(held).one(), owner=f'ticket {slug}')


def in_progress_started_by(
    repository: SqliteTaskRepository, slug: Slug, worker: Implementer
) -> list[str]:
    latest_attempts = (
        sql.select(sql.func.max(AttemptRow.id))
        .where(
            AttemptRow.repository_key == repository.repository_key.root,
            AttemptRow.slug == slug.root,
        )
        .group_by(AttemptRow.task_id)
    )
    query = (
        sql.select(TaskRow.task_id)
        .join(
            AttemptRow,
            sql.and_(
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


def latest_transition_of_each_task_into(
    repository: SqliteTaskRepository, slug: Slug, statuses: Collection[Status]
) -> dict[str, Transition]:
    latest_of_each_task = (
        sql.select(sql.func.max(TransitionRow.id))
        .where(
            TransitionRow.repository_key == repository.repository_key.root,
            TransitionRow.slug == slug.root,
            TransitionRow.after.in_(sorted(statuses)),
        )
        .group_by(TransitionRow.task_id)
    )
    query = (
        sql.select(TransitionRow)
        .where(TransitionRow.id.in_(latest_of_each_task))
        .limit(TASKS.fetched)
    )
    return {row.task_id: transition_of(row) for row in repository.session.scalars(query)}


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteTaskStore:
    database: Database

    @contextmanager
    def transaction(self) -> Generator[SqliteTaskRepository]:
        with self.database.transaction() as session:
            repository_key = self.database.repository_key
            yield SqliteTaskRepository(
                session=session,
                repository_key=repository_key,
                tickets=SqliteTicketRepository(session=session, repository_key=repository_key),
                contracts=SqliteContractRepository(session=session, repository_key=repository_key),
            )


def task_store(database: Database) -> TaskStore:
    return SqliteTaskStore(database=database)
