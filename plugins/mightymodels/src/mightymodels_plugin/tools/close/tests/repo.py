from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Self

from mightymodels_plugin.clock import now
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.tools.contract.schema import ContractCommand, Outcome, Phase, Receipt
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.review.schema import (
    Emphasis,
    FindingInput,
    ReportedSeverity,
    ReviewScope,
    StartPayload,
)
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.task.schema import Implementer, Status
from mightymodels_plugin.tools.task.store import Attempt, Transition
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
OLD = 'a' * 40
CHECKED_OUT = 'feature'
REVIEWED = datetime(2026, 9, 28, 12, tzinfo=UTC)
ANSWERS: Mapping[str, object] = MappingProxyType(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'context': ['drain loop sleeps between batches'],
        'issue': 42,
    }
)


def reported_finding(number: int) -> FindingInput:
    return FindingInput(
        sources=(f'MV-{number}',),
        severity=ReportedSeverity.HIGH,
        title=f'finding {number}',
        location=f'src/module_{number}.py:1',
        fix='fix it',
        verify='run the tests',
    )


def transition_to(task_id: str, after: Status) -> Transition:
    before = Status.PENDING if after is Status.IN_PROGRESS else Status.IN_PROGRESS
    return Transition(task_id=task_id, before=before, after=after, reasons=[], head=OLD, at=now())


@dataclass(frozen=True, slots=True, kw_only=True)
class CloseRepo:
    closings: CloseService
    tickets: TicketService
    contracts: ContractService
    reviews: ReviewService
    git: InMemoryGit

    @property
    def root(self) -> Path:
        return self.closings.workspace.root

    @property
    def state(self) -> Path:
        return self.root.joinpath('.mightymodels')

    def head(self) -> str:
        return self.git.commits[-1].sha

    def seeing(self, git: InMemoryGit) -> Self:
        return replace(self, git=git, closings=replace(self.closings, git=git))

    def stage(self, branch: str) -> None:
        self.tickets.write(TICKET, TicketAnswers.model_validate({**ANSWERS, 'branch': branch}))
        self.tickets.validate(TICKET)

    def approve_with_a_passing_receipt(self, command_id: str, argv: tuple[str, ...]) -> None:
        command = ContractCommand(id=command_id, argv=argv, approved_by='user')
        self.contracts.approve(TICKET, [command])
        receipt = Receipt(
            id=command_id,
            argv=argv,
            outcome=Outcome.PASSED,
            exit=0,
            duration_ms=0,
            stdout_tail='',
            stderr_tail='',
            digest='d' * 64,
            head=OLD,
            phase=Phase.TASK,
            at=now(),
        )
        with self.contracts.store.transaction() as repository:
            repository.record(TICKET, [receipt])

    def record_task(self, task_id: str, after: Status, *workers: Implementer) -> None:
        started = transition_to(task_id, Status.IN_PROGRESS)
        with self.closings.store.transaction() as repository:
            repository.recorded.tickets.mark_in_progress(TICKET)
            for worker in workers:
                attempt = Attempt(worker=worker, mode=None, owned=['queue.py'])
                repository.recorded.tasks.record_start(TICKET, started, attempt)
        with self.closings.store.transaction() as repository:
            repository.recorded.tasks.record_mark(TICKET, transition_to(task_id, after))

    def record_verified_work(self) -> None:
        self.record_task('T1', Status.VERIFIED, Implementer.ENGINEER)
        self.record_task('C1', Status.VERIFIED, Implementer.ENGINEER, Implementer.ARCHITECT)

    def review(self, findings: int) -> RunId:
        payload = StartPayload(
            scope=ReviewScope.CODEBASE, depth=Depth.DEEP, emphasis=Emphasis.BALANCED, slug=TICKET
        )
        run = RunId(str(self.reviews.start(payload, started=REVIEWED).run_id))
        self.reviews.add_findings(run, [reported_finding(n) for n in range(1, findings + 1)])
        return run

    def ticket_status(self) -> str:
        with self.closings.store.transaction() as repository:
            return repository.recorded.tickets.staged_ticket(TICKET).status
