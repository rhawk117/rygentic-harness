"""Every method of the contract repository, on the store kept in memory and on SQLite.

One fixture hands out either store, so each case runs on both and the store kept in memory cannot
drift from the repository it stands in for.
"""

import pytest
from mightymodels.core.database import Database
from mightymodels.core.slug import Slug
from mightymodels.tools.contract.repository import contract_store
from mightymodels.tools.contract.schema import (
    DEFAULT_TIMEOUT,
    ContractCommand,
    Outcome,
    Phase,
    Receipt,
)
from mightymodels.tools.contract.store import (
    Approval,
    ContractRepository,
    ContractStore,
    RecordedCommand,
)

TICKET = Slug('retry-queue')
OTHER = Slug('drain-loop')
HEAD = 'a' * 40
APPROVAL = Approval(at='2026-09-28T00:00:00+00:00', head=HEAD)
OF_A_TASK = ContractCommand(
    id='T1.AC-1', argv=('pytest', '-q'), expect_exit=1, timeout=30, approved_by='user'
)
OF_THE_TICKET = ContractCommand(id='I1', argv=('true',), approved_by='user')
OF_THE_OTHER_TICKET = ContractCommand(id='T2.AC-1', argv=('false',), approved_by='user')
RECORDED = (
    RecordedCommand(id='I1', task_id=None, argv=('true',), expect_exit=0, timeout=DEFAULT_TIMEOUT),
    RecordedCommand(id='T1.AC-1', task_id='T1', argv=('pytest', '-q'), expect_exit=1, timeout=30),
)


def receipt(command: ContractCommand, outcome: Outcome, *, run: int) -> Receipt:
    return Receipt(
        id=command.id,
        argv=command.argv,
        outcome=outcome,
        exit=None if outcome is Outcome.TIMEOUT else run,
        duration_ms=run,
        stdout_tail=f'out {run}',
        stderr_tail=f'err {run}',
        digest=f'digest {run}',
        head=None if run == 1 else HEAD,
        phase=Phase.TASK,
        at=f'2026-09-28T00:00:0{run}+00:00',
    )


FIRST_OF_THE_TASK = receipt(OF_A_TASK, Outcome.FAILED, run=1)
LATEST_OF_THE_TASK = receipt(OF_A_TASK, Outcome.PASSED, run=2)
LATEST_OF_THE_TICKET = receipt(OF_THE_TICKET, Outcome.TIMEOUT, run=3)
OF_THE_OTHER = receipt(OF_THE_OTHER_TICKET, Outcome.PASSED, run=4)


@pytest.fixture
def sqlite_store(repository_database: Database) -> ContractStore:
    return contract_store(repository_database)


@pytest.fixture(
    params=[
        pytest.param('in_memory_contract_store', id='fake'),
        pytest.param('sqlite_store', id='sqlite'),
    ]
)
def store(request: pytest.FixtureRequest) -> ContractStore:
    return request.getfixturevalue(request.param)


@pytest.fixture
def approved(store: ContractStore) -> ContractStore:
    with store.transaction() as repository:
        repository.approve(TICKET, [OF_A_TASK, OF_THE_TICKET], APPROVAL)
        repository.approve(OTHER, [OF_THE_OTHER_TICKET], APPROVAL)
    return store


@pytest.fixture
def run(approved: ContractStore) -> ContractStore:
    with approved.transaction() as repository:
        repository.record(TICKET, [FIRST_OF_THE_TASK, LATEST_OF_THE_TASK])
        repository.record(OTHER, [OF_THE_OTHER])
    with approved.transaction() as repository:
        repository.record(TICKET, [LATEST_OF_THE_TICKET])
    return approved


class TestContractRepository:
    def test_the_store_and_its_repository_are_the_seam_the_service_holds(
        self, store: ContractStore
    ) -> None:
        with store.transaction() as repository:
            assert isinstance(store, ContractStore)
            assert isinstance(repository, ContractRepository)

    def test_a_ticket_with_no_contract_has_no_command_and_no_receipt(
        self, store: ContractStore
    ) -> None:
        with store.transaction() as repository:
            assert repository.commands(TICKET) == []
            assert repository.latest_receipts(TICKET) == {}

    def test_the_approved_commands_of_a_ticket_are_read_in_the_order_of_their_ids(
        self, approved: ContractStore
    ) -> None:
        with approved.transaction() as repository:
            assert repository.commands(TICKET) == list(RECORDED)
            assert [command.id for command in repository.commands(OTHER)] == ['T2.AC-1']

    def test_commands_approved_later_join_the_ones_already_held(
        self, approved: ContractStore
    ) -> None:
        with approved.transaction() as repository:
            repository.approve(TICKET, [OF_THE_OTHER_TICKET], APPROVAL)

        with approved.transaction() as repository:
            assert [command.id for command in repository.commands(TICKET)] == [
                'I1',
                'T1.AC-1',
                'T2.AC-1',
            ]

    def test_a_command_never_run_has_no_receipt(self, approved: ContractStore) -> None:
        with approved.transaction() as repository:
            assert repository.latest_receipts(TICKET) == {}

    def test_the_latest_receipt_of_each_command_is_read_as_it_was_recorded(
        self, run: ContractStore
    ) -> None:
        with run.transaction() as repository:
            assert repository.latest_receipts(TICKET) == {
                'T1.AC-1': LATEST_OF_THE_TASK,
                'I1': LATEST_OF_THE_TICKET,
            }
            assert repository.latest_receipts(OTHER) == {'T2.AC-1': OF_THE_OTHER}
