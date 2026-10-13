"""Every member of the snapshot repository, on the store kept in memory and on SQLite.

One fixture hands out either store, so each case runs on both and the store kept in memory cannot
drift from the repository it stands in for. A snapshot stores nothing of its own, so each case
writes through the five repositories the snapshot repository hands out and reads them back the
same way.
"""

from contextlib import suppress

import pytest
from mightymodels.core.database import Database
from mightymodels.core.routing import Depth, Scope
from mightymodels.core.run_id import RunId
from mightymodels.core.slug import Slug
from mightymodels.tools.contract.schema import ContractCommand
from mightymodels.tools.contract.store import Approval, ContractRepository
from mightymodels.tools.investigation.schema import EntryKind, Source
from mightymodels.tools.investigation.store import InvestigationRepository, LedgerRecord
from mightymodels.tools.review.schema import Emphasis, Persona, ReviewRun, ReviewScope
from mightymodels.tools.review.store import ReviewRepository
from mightymodels.tools.snapshot.repository import snapshot_store
from mightymodels.tools.snapshot.store import SnapshotRepository, SnapshotStore
from mightymodels.tools.task.schema import Implementer, Status
from mightymodels.tools.task.store import Attempt, TaskRepository, Transition
from mightymodels.tools.ticket.repository import NotStagedError
from mightymodels.tools.ticket.schema import TicketSection, TicketStatus, Tracker
from mightymodels.tools.ticket.store import TicketRepository

TICKET = Slug('retry-queue')
NEVER_STAGED = Slug('never-staged')
LEDGER = Slug('20260928-queue-drains-slowly')
HEAD = 'a' * 40
AT = '2026-09-28T12:00:00+00:00'
SECTION = TicketSection(
    ticket='Retry queue drains slowly',
    summary='The drain loop sleeps between batches',
    branch='fix/retry-queue',
    scope=Scope.MED,
    plan_first=False,
    models={},
    tracker=Tracker(issue=None, jira=None),
    context=(),
    validated_at=AT,
)
COMMAND = ContractCommand(id='T1.AC-1', argv=('true',), approved_by='user')
APPROVAL = Approval(at=AT, head=HEAD)
STARTED = Transition(
    task_id='T1', before=Status.PENDING, after=Status.IN_PROGRESS, reasons=(), head=HEAD, at=AT
)
BY_THE_ENGINEER = Attempt(worker=Implementer.ENGINEER, mode=None, owned=('src/queue.py',))
RUN = ReviewRun(
    run_id=RunId('20260928-120000'),
    slug=TICKET,
    scope=ReviewScope.TICKET,
    base='main',
    head=HEAD,
    depth=Depth.DEEP,
    emphasis=Emphasis.BALANCED,
    weights={Persona.MERGE_VADER: 0.5, Persona.UNCLE_BOB: 0.5},
    personas=(Persona.MERGE_VADER, Persona.UNCLE_BOB),
    models={'merge-vader': 'opus', 'uncle-bob': None},
    created_at=AT,
)
TARGET = LedgerRecord(
    seq=1,
    round=0,
    kind=EntryKind.TARGET,
    text='Queue drains slowly',
    source=Source.USER,
    cite='behavior',
    supersedes=(),
    at=AT,
    head=None,
)


def record_in_each_domain(repository: SnapshotRepository) -> None:
    repository.tickets.stage(TICKET, SECTION, [LEDGER.root])
    repository.contracts.approve(TICKET, [COMMAND], APPROVAL)
    repository.tasks.record_start(TICKET, STARTED, BY_THE_ENGINEER)
    repository.reviews.record_run(RUN)
    repository.investigations.append(LEDGER, [TARGET])


@pytest.fixture
def sqlite_store(repository_database: Database) -> SnapshotStore:
    return snapshot_store(repository_database)


@pytest.fixture(
    params=[
        pytest.param('in_memory_snapshot_store', id='fake'),
        pytest.param('sqlite_store', id='sqlite'),
    ]
)
def store(request: pytest.FixtureRequest) -> SnapshotStore:
    return request.getfixturevalue(request.param)


@pytest.fixture
def recorded(store: SnapshotStore) -> SnapshotStore:
    with store.transaction() as repository:
        record_in_each_domain(repository)
    return store


@pytest.fixture
def abandoned(store: SnapshotStore) -> SnapshotStore:
    with suppress(NotStagedError), store.transaction() as repository:
        record_in_each_domain(repository)
        repository.tickets.staged_ticket(NEVER_STAGED)
    return store


class TestSnapshotRepository:
    def test_the_store_and_its_repository_are_the_seam_the_service_holds(
        self, store: SnapshotStore
    ) -> None:
        with store.transaction() as repository:
            assert isinstance(store, SnapshotStore)
            assert isinstance(repository, SnapshotRepository)

    def test_each_of_the_five_is_the_repository_its_own_domain_names(
        self, store: SnapshotStore
    ) -> None:
        with store.transaction() as repository:
            assert isinstance(repository.tickets, TicketRepository)
            assert isinstance(repository.tasks, TaskRepository)
            assert isinstance(repository.contracts, ContractRepository)
            assert isinstance(repository.reviews, ReviewRepository)
            assert isinstance(repository.investigations, InvestigationRepository)

    def test_a_ticket_never_staged_has_nothing_recorded_in_any_of_the_five(
        self, store: SnapshotStore
    ) -> None:
        with store.transaction() as repository:
            assert repository.tickets.ticket(TICKET) is None
            assert repository.tasks.tasks(TICKET) == []
            assert repository.contracts.commands(TICKET) == []
            assert repository.reviews.latest_run(TICKET) is None
            assert not repository.investigations.has_entries(LEDGER)

    def test_what_each_domain_recorded_is_read_in_one_transaction(
        self, recorded: SnapshotStore
    ) -> None:
        with recorded.transaction() as repository:
            assert repository.tickets.staged_ticket(TICKET).investigations == (LEDGER.root,)
            assert [task.id for task in repository.tasks.tasks(TICKET)] == ['T1']
            assert [command.id for command in repository.contracts.commands(TICKET)] == ['T1.AC-1']
            assert repository.reviews.latest_run(TICKET) == RUN
            assert repository.investigations.entries(LEDGER) == [TARGET]

    def test_a_transaction_that_fails_keeps_nothing_of_the_five(
        self, abandoned: SnapshotStore
    ) -> None:
        with abandoned.transaction() as repository:
            assert repository.tickets.ticket(TICKET) is None
            assert repository.tasks.tasks(TICKET) == []
            assert repository.contracts.commands(TICKET) == []
            assert repository.reviews.latest_run(TICKET) is None
            assert not repository.investigations.has_entries(LEDGER)


class TestTheTicketAndTheContractOfTheTaskRepository:
    @pytest.fixture
    def marked_through_the_tasks(self, recorded: SnapshotStore) -> SnapshotStore:
        with recorded.transaction() as repository:
            repository.tasks.tickets.mark_in_progress(TICKET)
        return recorded

    def test_a_ticket_the_task_repository_moved_reads_moved_from_the_snapshots_own(
        self, recorded: SnapshotStore
    ) -> None:
        with recorded.transaction() as repository:
            repository.tasks.tickets.mark_in_progress(TICKET)

            assert repository.tickets.staged_ticket(TICKET).status is TicketStatus.IN_PROGRESS

    def test_a_ticket_the_task_repository_moved_is_kept_moved(
        self, marked_through_the_tasks: SnapshotStore
    ) -> None:
        with marked_through_the_tasks.transaction() as repository:
            assert repository.tickets.staged_ticket(TICKET).status is TicketStatus.IN_PROGRESS

    def test_a_command_the_snapshots_contracts_approved_is_read_by_the_task_repositorys(
        self, recorded: SnapshotStore
    ) -> None:
        with recorded.transaction() as repository:
            assert [command.id for command in repository.tasks.contracts.commands(TICKET)] == [
                'T1.AC-1'
            ]
