"""The one assessment of a receipt, and what its three callers show while there is no HEAD."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pytest
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.contract.assessment import Assessment, ReceiptState, Taken
from mightymodels_plugin.tools.contract.schema import ContractCommand, Outcome, Phase, Receipt
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.snapshot.schema import DEFAULT_LIMIT
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

TICKET = Slug('retry-queue')
COMMAND = 'T1.AC-1'
COMMIT = 'a' * 40
ANOTHER_COMMIT = 'b' * 40
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': 'fix/retry-queue',
        'context': ['drain loop sleeps between batches'],
    }
)


class TestTheThreeStates:
    AT_THE_COMMIT = Taken(outcome=Outcome.PASSED, head=COMMIT)
    AT_ANOTHER_COMMIT = Taken(outcome=Outcome.PASSED, head=ANOTHER_COMMIT)
    AT_NO_HEAD = Taken(outcome=Outcome.PASSED, head=None)

    @pytest.mark.parametrize(
        ('taken', 'head', 'state'),
        [
            pytest.param(None, COMMIT, ReceiptState.NEVER_RUN, id='never-run'),
            pytest.param(AT_THE_COMMIT, COMMIT, ReceiptState.AT_HEAD, id='at-head'),
            pytest.param(AT_ANOTHER_COMMIT, COMMIT, ReceiptState.STALE, id='at-another-head'),
            pytest.param(AT_NO_HEAD, None, ReceiptState.STALE, id='no-head-anywhere'),
            pytest.param(
                AT_THE_COMMIT, None, ReceiptState.STALE, id='receipt-at-a-commit-with-no-head'
            ),
            pytest.param(
                AT_NO_HEAD, COMMIT, ReceiptState.STALE, id='receipt-at-no-head-with-a-head'
            ),
        ],
    )
    def test_a_receipt_is_at_head_only_when_head_is_known_and_is_its_own(
        self, taken: Taken | None, head: str | None, state: ReceiptState
    ) -> None:
        assert Assessment(taken=taken, head=head).state is state


@dataclass(frozen=True, slots=True, kw_only=True)
class Shown:
    counted: bool
    lines: Sequence[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class Callers:
    contracts: ContractService
    snapshots: SnapshotService
    tasks: TaskService

    def verify_status(self) -> Shown:
        view = self.contracts.status(TICKET)
        return Shown(counted=view.passing, lines=view.text.splitlines())

    def snapshot(self) -> Shown:
        record = self.snapshots.take(TICKET, DEFAULT_LIMIT).record
        states = [check.state for check in record.checks]
        return Shown(counted=Outcome.PASSED in states, lines=states)

    def task_gate(self) -> Shown:
        view = self.tasks.ready(TICKET)
        return Shown(counted=view.advanced, lines=view.text.splitlines())


@runtime_checkable
class Reading(Protocol):
    def __call__(self, callers: Callers, /) -> Shown: ...


def passing_receipt(taken_at: str | None) -> Receipt:
    return Receipt(
        id=COMMAND,
        argv=('true',),
        outcome=Outcome.PASSED,
        exit=0,
        duration_ms=0,
        stdout_tail='',
        stderr_tail='',
        digest='',
        head=taken_at,
        phase=Phase.TASK,
        at=now(),
    )


class TestWhileThereIsNoHead:
    @pytest.fixture
    def unborn_with_a_passing_receipt(
        self,
        contract_service: ContractService,
        snapshot_service: SnapshotService,
        task_service: TaskService,
        ticket_service: TicketService,
        taken_at: str | None,
    ) -> Callers:
        ticket_service.write(TICKET, ANSWERS)
        ticket_service.validate(TICKET)
        approved = ContractCommand(id=COMMAND, argv=('true',), approved_by='user')
        contract_service.approve(TICKET, [approved])
        with contract_service.store.transaction() as repository:
            repository.record(TICKET, [passing_receipt(taken_at)])
        return Callers(contracts=contract_service, snapshots=snapshot_service, tasks=task_service)

    @pytest.mark.parametrize(
        ('taken_at', 'named'),
        [
            pytest.param(None, 'unknown', id='at-no-head'),
            pytest.param(COMMIT, COMMIT[:12], id='at-a-commit'),
        ],
    )
    @pytest.mark.parametrize(
        ('reading', 'wording'),
        [
            pytest.param(
                Callers.verify_status, f'{COMMAND} stale (pass at {{named}})', id='verify-status'
            ),
            pytest.param(Callers.snapshot, 'stale (pass at {named})', id='snapshot'),
            pytest.param(
                Callers.task_gate,
                f'  - {COMMAND} has no receipt at the current HEAD',
                id='task-gate',
            ),
        ],
    )
    def test_no_caller_counts_a_passing_receipt_while_there_is_no_head(
        self, unborn_with_a_passing_receipt: Callers, reading: Reading, wording: str, named: str
    ) -> None:
        shown = reading(unborn_with_a_passing_receipt)

        assert not shown.counted
        assert wording.format(named=named) in shown.lines
