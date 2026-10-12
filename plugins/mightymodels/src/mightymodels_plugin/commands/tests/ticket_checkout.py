import json
from dataclasses import dataclass
from pathlib import Path

from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.tools.contract.schema import ContractCommand, Outcome, Phase, Receipt
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.task.repository import task_store
from mightymodels_plugin.tools.task.schema import Implementer, Status
from mightymodels_plugin.tools.task.store import Attempt, Transition
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
OTHER_SLUG = 'retry-queue-again'
BRANCH = 'fix/retry'
COMMAND = 'T1.AC-1'
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': BRANCH,
        'context': ['drain loop sleeps between batches'],
    }
)
NO_DECISION = (0, '', '')


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketCheckout:
    root: Path
    tickets: TicketService
    contracts: ContractService
    database: Database
    runner: GitRunner

    def git(self, *arguments: str) -> str:
        return self.runner(self.root, *IDENTITY, *arguments).strip()

    def commit(self) -> None:
        self.git('commit', '--allow-empty', '--quiet', '-m', 'work')

    def head(self) -> str:
        return self.git('rev-parse', 'HEAD')

    def stage(self, slug: Slug) -> None:
        self.tickets.write(slug, ANSWERS)
        self.tickets.validate(slug)

    def record_task(self, task_id: str, *after: Status) -> None:
        started = Transition(
            task_id=task_id,
            before=Status.PENDING,
            after=Status.IN_PROGRESS,
            reasons=[],
            head=None,
            at=now(),
        )
        attempt = Attempt(worker=Implementer.ENGINEER, mode=None, owned=['src/queue.py'])
        with task_store(self.database).transaction() as repository:
            repository.tickets.mark_in_progress(TICKET)
            repository.record_start(TICKET, started, attempt)
        for status in after:
            marked = Transition(
                task_id=task_id,
                before=Status.IN_PROGRESS,
                after=status,
                reasons=['the drain loop still sleeps'],
                head=None,
                at=now(),
            )
            with task_store(self.database).transaction() as repository:
                repository.record_mark(TICKET, marked)

    def approve(self) -> None:
        self.contracts.approve(
            TICKET, [ContractCommand(id=COMMAND, argv=('true',), approved_by='user')]
        )

    def record_receipt(self, outcome: Outcome, phase: Phase, head: str) -> None:
        receipt = Receipt(
            id=COMMAND,
            argv=('true',),
            outcome=outcome,
            exit=0 if outcome is Outcome.PASSED else 1,
            duration_ms=0,
            stdout_tail='',
            stderr_tail='',
            digest='d' * 64,
            head=head,
            phase=phase,
            at=now(),
        )
        with self.contracts.store.transaction() as repository:
            repository.record(TICKET, [receipt])


def decision_of(out: str) -> tuple[str, str]:
    answer = json.loads(out)['hookSpecificOutput']
    return answer['permissionDecision'], answer['permissionDecisionReason']


def shown(result: tuple[int, str, str]) -> str:
    code, out, err = result
    assert (code, err, out.count('\n')) == (0, '', 1)
    return json.loads(out)['systemMessage']
