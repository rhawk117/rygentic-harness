"""The seam under the task service: a store whose transaction hands out the task repository.

`TaskStore.transaction` is a context manager, and what it yields is a `TaskRepository` that lives
for that one transaction. The SQLite store in `repository.py` wraps the database, and a store in
test support holds the tasks in memory, so the task service runs on either.

The repository is two Protocols. `TaskRecords` is the ten reads and writes of a ticket's tasks,
attempts, failed fixes and transitions. `TaskRepository` adds `tickets` and `contracts`, the
ticket and the contract of the same transaction, which a task action reads and writes with its own
records.

A repository hands out frozen values and never a row. A task is a `TaskRecord` with no attempts
counted, since `attempts_by_worker` reads those for a whole ticket at once. A `Transition` is one
move of a task, written with the change it records and read back as it was written. An `Attempt`
is the worker, the mode and the owned files of one start.
"""

from collections.abc import Collection, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.contract.store import ContractRepository
from mightymodels_plugin.tools.task.schema import ArchitectMode, Implementer, Status, TaskRecord
from mightymodels_plugin.tools.ticket.store import TicketRepository

type AttemptCounts = dict[str, dict[str, int]]


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


@runtime_checkable
class TaskRecords(Protocol):
    def task(self, slug: Slug, task_id: str) -> TaskRecord | None: ...

    def tasks(self, slug: Slug) -> list[TaskRecord]: ...

    def attempts_by_worker(self, slug: Slug) -> AttemptCounts: ...

    def attempts_in_modes(
        self, slug: Slug, task_id: str, modes: Collection[ArchitectMode]
    ) -> int: ...

    def failed_fixes(self, slug: Slug, task_id: str) -> list[str]: ...

    def latest_transitions_into(
        self, slug: Slug, statuses: Collection[Status], limit: int
    ) -> list[Transition]: ...

    def record_start(self, slug: Slug, transition: Transition, attempt: Attempt) -> None: ...

    def record_failed_fix(self, slug: Slug, task_id: str, hypothesis: str, *, at: str) -> None: ...

    def record_verification(self, slug: Slug, transition: Transition, commit: str) -> None: ...

    def record_mark(self, slug: Slug, transition: Transition) -> None: ...


@runtime_checkable
class TaskRepository(TaskRecords, Protocol):
    @property
    def tickets(self) -> TicketRepository: ...

    @property
    def contracts(self) -> ContractRepository: ...


@runtime_checkable
class TaskStore(Protocol):
    def transaction(self) -> AbstractContextManager[TaskRepository]: ...
