"""Every method of the ticket repository, on the store kept in memory and on SQLite.

One fixture hands out either store, so each case runs on both and the store kept in memory cannot
drift from the repository it stands in for. Each store starts with one investigation that has a
ledger.
"""

from contextlib import suppress
from datetime import UTC, datetime
from operator import methodcaller

import pytest
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.routing import Scope
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.investigation.schema import InvestigationStart, TargetKind
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.ticket.repository import (
    ClosedTicketError,
    NotStagedError,
    ticket_store,
)
from mightymodels_plugin.tools.ticket.schema import TicketSection, TicketStatus, Tracker, WorkUnit
from mightymodels_plugin.tools.ticket.store import TicketRepository, TicketStore
from mightymodels_plugin.tools.ticket.tests.in_memory import InMemoryTicketStore

TICKET = Slug('retry-queue')
OTHER = Slug('drain-loop')
BRANCH = 'fix/retry-queue'
LEDGER_TARGET = InvestigationStart(target='inv a', kind=TargetKind.BEHAVIOR)
LEDGER_STARTED = datetime(2026, 9, 28, tzinfo=UTC)
WITH_A_LEDGER = Slug('20260928-inv-a')
WITHOUT_A_LEDGER = Slug('20260929-inv-b')
ALSO_WITHOUT_A_LEDGER = Slug('20260930-inv-c')
SECTION = TicketSection(
    ticket='Retry queue drains slowly',
    summary='The drain loop sleeps between batches',
    branch=BRANCH,
    scope=Scope.MED,
    plan_first=False,
    models={'engineer': 'sonnet', 'architect': None},
    tracker=Tracker(issue=17, jira=None),
    context=('drain loop sleeps between batches',),
    validated_at='2026-09-28T00:00:00+00:00',
)
REVISED = SECTION.model_copy(update={'summary': 'The drain loop never wakes', 'plan_first': True})
OTHER_SECTION = SECTION.model_copy(update={'ticket': 'Drain loop never wakes'})
ELSEWHERE = SECTION.model_copy(update={'ticket': 'Drain loop never wakes', 'branch': 'fix/drain'})
STAGED = WorkUnit(
    slug=TICKET,
    status=TicketStatus.STAGED,
    ticket=SECTION,
    investigations=(WITH_A_LEDGER.root,),
)


@pytest.fixture
def fake_store(in_memory_ticket_store: InMemoryTicketStore) -> TicketStore:
    in_memory_ticket_store.recorded_investigations.add(WITH_A_LEDGER)
    return in_memory_ticket_store


@pytest.fixture
def sqlite_store(
    repository_database: Database, investigation_service: InvestigationService
) -> TicketStore:
    investigation_service.start(LEDGER_TARGET, started=LEDGER_STARTED)
    return ticket_store(repository_database)


@pytest.fixture(
    params=[pytest.param('fake_store', id='fake'), pytest.param('sqlite_store', id='sqlite')]
)
def store(request: pytest.FixtureRequest) -> TicketStore:
    return request.getfixturevalue(request.param)


@pytest.fixture
def staged(store: TicketStore) -> TicketStore:
    with store.transaction() as repository:
        repository.stage(TICKET, SECTION, [WITH_A_LEDGER.root])
    return store


@pytest.fixture
def closed(staged: TicketStore) -> TicketStore:
    with staged.transaction() as repository:
        repository.mark_closed(TICKET)
    return staged


class TestTicketRepository:
    def test_the_store_and_its_repository_are_the_seam_the_service_holds(
        self, store: TicketStore
    ) -> None:
        with store.transaction() as repository:
            assert isinstance(store, TicketStore)
            assert isinstance(repository, TicketRepository)

    def test_no_ticket_is_read_before_one_is_staged(self, store: TicketStore) -> None:
        with store.transaction() as repository:
            assert repository.ticket(TICKET) is None

    @pytest.mark.parametrize(
        'ask',
        [
            pytest.param(methodcaller('staged_ticket', TICKET), id='staged-ticket'),
            pytest.param(methodcaller('unclosed_ticket', TICKET), id='unclosed-ticket'),
            pytest.param(methodcaller('mark_in_progress', TICKET), id='mark-in-progress'),
            pytest.param(methodcaller('mark_closed', TICKET), id='mark-closed'),
        ],
    )
    def test_a_ticket_never_staged_is_refused(self, store: TicketStore, ask: methodcaller) -> None:
        with store.transaction() as repository, pytest.raises(NotStagedError) as refusal:
            ask(repository)

        assert refusal.value.slug == TICKET

    def test_stage_returns_the_unit_it_staged(self, store: TicketStore) -> None:
        with store.transaction() as repository:
            unit = repository.stage(TICKET, SECTION, [WITH_A_LEDGER.root])

        assert unit == STAGED

    def test_a_staged_ticket_is_read_back_by_every_read(self, staged: TicketStore) -> None:
        with staged.transaction() as repository:
            assert repository.ticket(TICKET) == STAGED
            assert repository.staged_ticket(TICKET) == STAGED
            assert repository.unclosed_ticket(TICKET) == STAGED

    def test_staging_again_keeps_the_status_and_adds_only_the_new_investigations(
        self, staged: TicketStore
    ) -> None:
        declared = [WITHOUT_A_LEDGER.root, WITH_A_LEDGER.root]

        with staged.transaction() as repository:
            repository.mark_in_progress(TICKET)
            restaged = repository.stage(TICKET, REVISED, declared)

        assert restaged == WorkUnit(
            slug=TICKET,
            status=TicketStatus.IN_PROGRESS,
            ticket=REVISED,
            investigations=(WITH_A_LEDGER.root, WITHOUT_A_LEDGER.root),
        )

    def test_a_ticket_marked_in_progress_reads_in_progress(self, staged: TicketStore) -> None:
        with staged.transaction() as repository:
            repository.mark_in_progress(TICKET)

        with staged.transaction() as repository:
            assert repository.unclosed_ticket(TICKET).status is TicketStatus.IN_PROGRESS

    def test_a_closed_ticket_is_still_read(self, closed: TicketStore) -> None:
        with closed.transaction() as repository:
            read = repository.ticket(TICKET)
            assert read == repository.staged_ticket(TICKET)
            assert repository.staged_ticket(TICKET).status is TicketStatus.CLOSED

    @pytest.mark.parametrize(
        'ask',
        [
            pytest.param(methodcaller('unclosed_ticket', TICKET), id='unclosed-ticket'),
            pytest.param(methodcaller('mark_in_progress', TICKET), id='mark-in-progress'),
        ],
    )
    def test_a_closed_ticket_takes_no_more_work(
        self, closed: TicketStore, ask: methodcaller
    ) -> None:
        with closed.transaction() as repository, pytest.raises(ClosedTicketError) as refusal:
            ask(repository)

        assert refusal.value.slug == TICKET

    def test_the_investigations_with_no_ledger_are_named_in_the_order_given(
        self, store: TicketStore
    ) -> None:
        linked = [WITHOUT_A_LEDGER, WITH_A_LEDGER, ALSO_WITHOUT_A_LEDGER]

        with store.transaction() as repository:
            assert repository.unrecorded_investigations(linked) == [
                WITHOUT_A_LEDGER,
                ALSO_WITHOUT_A_LEDGER,
            ]
            assert repository.unrecorded_investigations([]) == []


class TestUnclosedOnBranch:
    @pytest.fixture
    def two_on_the_branch(self, staged: TicketStore) -> TicketStore:
        with staged.transaction() as repository:
            repository.stage(OTHER, OTHER_SECTION, [])
        return staged

    @pytest.fixture
    def one_of_two_closed(self, two_on_the_branch: TicketStore) -> TicketStore:
        with two_on_the_branch.transaction() as repository:
            repository.mark_closed(TICKET)
        return two_on_the_branch

    @pytest.fixture
    def one_on_each_branch(self, staged: TicketStore) -> TicketStore:
        with staged.transaction() as repository:
            repository.stage(OTHER, ELSEWHERE, [])
        return staged

    def test_no_ticket_is_on_a_branch_before_one_is_staged(self, store: TicketStore) -> None:
        with store.transaction() as repository:
            assert repository.unclosed_on_branch(BRANCH) is None

    def test_the_one_ticket_on_the_branch_is_named(self, one_on_each_branch: TicketStore) -> None:
        with one_on_each_branch.transaction() as repository:
            assert repository.unclosed_on_branch(BRANCH) == TICKET
            assert repository.unclosed_on_branch(ELSEWHERE.branch) == OTHER
            assert repository.unclosed_on_branch('main') is None

    def test_two_tickets_on_the_branch_name_none(self, two_on_the_branch: TicketStore) -> None:
        with two_on_the_branch.transaction() as repository:
            assert repository.unclosed_on_branch(BRANCH) is None

    def test_a_closed_ticket_is_not_on_its_branch(self, one_of_two_closed: TicketStore) -> None:
        with one_of_two_closed.transaction() as repository:
            assert repository.unclosed_on_branch(BRANCH) == OTHER


class TestAFailedTransaction:
    @pytest.fixture
    def staging_that_failed(self, store: TicketStore) -> TicketStore:
        with suppress(NotStagedError), store.transaction() as repository:
            repository.stage(TICKET, SECTION, [])
            repository.staged_ticket(OTHER)
        return store

    def test_a_transaction_that_fails_keeps_nothing(self, staging_that_failed: TicketStore) -> None:
        with staging_that_failed.transaction() as repository:
            assert repository.ticket(TICKET) is None
