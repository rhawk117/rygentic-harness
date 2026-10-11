"""The task store kept in memory: a ticket's tasks, attempts, failed fixes and transitions.

It is built on the ticket store and the contract store kept in memory, and its transaction opens
theirs, so the repository it hands out reaches the ticket and the contract in the one transaction
as the SQLite repository does. A transaction works on a copy and keeps it only when its block ends
without an error.

A task is held as the `TaskRecord` the repository hands out, with no attempts counted, and a
transition with its reasons as a tuple, as one read back from a row has them.
"""

from collections.abc import Collection, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.contract.tests.in_memory import (
    InMemoryContractRepository,
    InMemoryContractStore,
)
from mightymodels_plugin.tools.task.schema import ArchitectMode, Status, TaskRecord
from mightymodels_plugin.tools.task.store import Attempt, AttemptCounts, Transition
from mightymodels_plugin.tools.ticket.tests.in_memory import (
    InMemoryTicketRepository,
    InMemoryTicketStore,
)

type TaskKey = tuple[Slug, str]


@dataclass(slots=True, kw_only=True, frozen=True)
class StartedAttempt:
    task: TaskKey
    attempt: Attempt


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedFix:
    task: TaskKey
    hypothesis: str
    at: str


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedTransition:
    slug: Slug
    transition: Transition


def recorded(slug: Slug, transition: Transition) -> RecordedTransition:
    kept = replace(transition, reasons=tuple(transition.reasons))
    return RecordedTransition(slug=slug, transition=kept)


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryTaskRepository:
    held: dict[TaskKey, TaskRecord]
    attempts: list[StartedAttempt]
    fixes: list[FailedFix]
    transitions: list[RecordedTransition]
    tickets: InMemoryTicketRepository
    contracts: InMemoryContractRepository

    def task(self, slug: Slug, task_id: str) -> TaskRecord | None:
        return self.held.get((slug, task_id))

    def tasks(self, slug: Slug) -> list[TaskRecord]:
        return [task for (owner, _), task in self.held.items() if owner == slug]

    def attempts_by_worker(self, slug: Slug) -> AttemptCounts:
        counts: AttemptCounts = {}
        for started in self.attempts:
            owner, task_id = started.task
            if owner == slug:
                worker = started.attempt.worker.value
                by_worker = counts.setdefault(task_id, {})
                by_worker[worker] = by_worker.get(worker, 0) + 1
        return counts

    def attempts_in_modes(self, slug: Slug, task_id: str, modes: Collection[ArchitectMode]) -> int:
        return sum(
            started.task == (slug, task_id) and started.attempt.mode in modes
            for started in self.attempts
        )

    def failed_fixes(self, slug: Slug, task_id: str) -> list[str]:
        return [fix.hypothesis for fix in self.fixes if fix.task == (slug, task_id)]

    def latest_transitions_into(
        self, slug: Slug, statuses: Collection[Status], limit: int
    ) -> list[Transition]:
        into = [
            recorded.transition
            for recorded in self.transitions
            if recorded.slug == slug and recorded.transition.after in statuses
        ]
        return into[max(len(into) - limit, 0) :]

    def record_start(self, slug: Slug, transition: Transition, attempt: Attempt) -> None:
        key = (slug, transition.task_id)
        started = self.held.get(key)
        first_base = None if started is None else started.base
        self.held[key] = TaskRecord(
            id=transition.task_id,
            status=transition.after,
            owned=tuple(attempt.owned),
            base=transition.head if first_base is None else first_base,
        )
        self.attempts.append(StartedAttempt(task=key, attempt=attempt))
        self.transitions.append(recorded(slug, transition))

    def record_failed_fix(self, slug: Slug, task_id: str, hypothesis: str, *, at: str) -> None:
        self.fixes.append(FailedFix(task=(slug, task_id), hypothesis=hypothesis, at=at))

    def record_verification(self, slug: Slug, transition: Transition, commit: str) -> None:
        key = (slug, transition.task_id)
        change = {
            'status': transition.after,
            'commit': commit,
            'reasons': tuple(transition.reasons),
        }
        self.held[key] = self.held[key].model_copy(update=change)
        self.transitions.append(recorded(slug, transition))

    def record_mark(self, slug: Slug, transition: Transition) -> None:
        key = (slug, transition.task_id)
        change = {'status': transition.after, 'reasons': tuple(transition.reasons)}
        self.held[key] = self.held[key].model_copy(update=change)
        self.transitions.append(recorded(slug, transition))


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryTaskStore:
    tickets: InMemoryTicketStore
    contracts: InMemoryContractStore
    held: dict[TaskKey, TaskRecord] = field(default_factory=dict)
    attempts: list[StartedAttempt] = field(default_factory=list)
    fixes: list[FailedFix] = field(default_factory=list)
    transitions: list[RecordedTransition] = field(default_factory=list)

    @contextmanager
    def transaction(self) -> Generator[InMemoryTaskRepository]:
        with self.tickets.transaction() as tickets, self.contracts.transaction() as contracts:
            working = InMemoryTaskRepository(
                held=dict(self.held),
                attempts=list(self.attempts),
                fixes=list(self.fixes),
                transitions=list(self.transitions),
                tickets=tickets,
                contracts=contracts,
            )
            yield working
            self.held.clear()
            self.held.update(working.held)
            self.attempts[:] = working.attempts
            self.fixes[:] = working.fixes
            self.transitions[:] = working.transitions
