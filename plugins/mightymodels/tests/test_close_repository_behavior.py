"""Every member of the close repository, on the store kept in memory and on SQLite.

One fixture hands out either store, so each case runs on both and the store kept in memory cannot
drift from the repository it stands in for. Nothing reads a closing back, so a case sees
`record_closing` through `recorded`: the ticket it closed reads closed there.
"""

from contextlib import suppress

import pytest
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.routing import Scope
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.close.repository import close_store
from mightymodels_plugin.tools.close.schema import ArchiveRecord
from mightymodels_plugin.tools.close.store import CloseRepository, CloseStore
from mightymodels_plugin.tools.snapshot.store import SnapshotRepository
from mightymodels_plugin.tools.ticket.repository import NotStagedError
from mightymodels_plugin.tools.ticket.schema import TicketSection, TicketStatus, Tracker

TICKET = Slug('retry-queue')
OTHER = Slug('drain-loop')
NEVER_STAGED = Slug('never-staged')
AT = '2026-09-28T12:00:00+00:00'
ARCHIVE = '.mightymodels/archives/retry-queue.md'
REPEATED_ARCHIVE = '.mightymodels/archives/retry-queue-2.md'
SECTION = TicketSection(
    ticket='Retry queue drains slowly',
    summary='The drain loop sleeps between batches',
    branch='fix/retry-queue',
    scope=Scope.MED,
    plan_first=False,
    models={},
    tracker=Tracker(issue=42, jira=None),
    context=(),
    validated_at=AT,
)
OTHER_SECTION = SECTION.model_copy(update={'ticket': 'Drain loop never wakes'})
CLOSING = ArchiveRecord(
    slug=TICKET,
    closed_at=AT,
    head='a' * 40,
    shipped='Retry queue drains in under a second',
    pr='https://x/pull/7',
    tracker=SECTION.tracker,
    summary=SECTION.summary,
    investigations=(),
    tasks={},
    verification=(),
    decisions=(),
    review=None,
    gotchas=('the backoff floor is load-bearing',),
)
CLOSING_WITH_NO_HEAD_AND_NO_PR = CLOSING.model_copy(
    update={'head': None, 'pr': None, 'gotchas': ()}
)
CLOSING_OF_A_TICKET_NEVER_STAGED = CLOSING.model_copy(update={'slug': NEVER_STAGED})


def status_of(repository: CloseRepository, slug: Slug) -> TicketStatus:
    return repository.recorded.tickets.staged_ticket(slug).status


@pytest.fixture
def sqlite_store(repository_database: Database) -> CloseStore:
    return close_store(repository_database)


@pytest.fixture(
    params=[
        pytest.param('in_memory_close_store', id='fake'),
        pytest.param('sqlite_store', id='sqlite'),
    ]
)
def store(request: pytest.FixtureRequest) -> CloseStore:
    return request.getfixturevalue(request.param)


@pytest.fixture
def staged(store: CloseStore) -> CloseStore:
    with store.transaction() as repository:
        repository.recorded.tickets.stage(TICKET, SECTION, [])
        repository.recorded.tickets.stage(OTHER, OTHER_SECTION, [])
    return store


@pytest.fixture
def closed(staged: CloseStore) -> CloseStore:
    with staged.transaction() as repository:
        repository.record_closing(CLOSING, archive=ARCHIVE)
    return staged


class TestCloseRepository:
    @pytest.fixture
    def closed_twice(self, closed: CloseStore) -> CloseStore:
        with closed.transaction() as repository:
            repository.record_closing(CLOSING_WITH_NO_HEAD_AND_NO_PR, archive=REPEATED_ARCHIVE)
        return closed

    @pytest.fixture
    def abandoned(self, staged: CloseStore) -> CloseStore:
        with suppress(NotStagedError), staged.transaction() as repository:
            repository.record_closing(CLOSING, archive=ARCHIVE)
            repository.record_closing(CLOSING_OF_A_TICKET_NEVER_STAGED, archive=ARCHIVE)
        return staged

    def test_the_store_and_its_repository_are_the_seam_the_service_holds(
        self, store: CloseStore
    ) -> None:
        with store.transaction() as repository:
            assert isinstance(store, CloseStore)
            assert isinstance(repository, CloseRepository)
            assert isinstance(repository.recorded, SnapshotRepository)

    def test_what_was_recorded_is_read_in_the_transaction_that_closes(
        self, staged: CloseStore
    ) -> None:
        with staged.transaction() as repository:
            assert repository.recorded.tickets.staged_ticket(TICKET).ticket == SECTION
            assert status_of(repository, TICKET) is TicketStatus.STAGED

    def test_a_closing_marks_its_ticket_closed_in_the_transaction_that_records_it(
        self, staged: CloseStore
    ) -> None:
        with staged.transaction() as repository:
            repository.record_closing(CLOSING, archive=ARCHIVE)

            assert status_of(repository, TICKET) is TicketStatus.CLOSED

    def test_a_recorded_closing_leaves_its_ticket_closed_and_no_other(
        self, closed: CloseStore
    ) -> None:
        with closed.transaction() as repository:
            assert status_of(repository, TICKET) is TicketStatus.CLOSED
            assert status_of(repository, OTHER) is TicketStatus.STAGED

    def test_a_ticket_closed_again_takes_its_new_closing_and_stays_closed(
        self, closed_twice: CloseStore
    ) -> None:
        with closed_twice.transaction() as repository:
            assert status_of(repository, TICKET) is TicketStatus.CLOSED

    def test_a_closing_of_a_ticket_never_staged_is_refused(self, staged: CloseStore) -> None:
        with pytest.raises(NotStagedError) as refusal, staged.transaction() as repository:
            repository.record_closing(CLOSING_OF_A_TICKET_NEVER_STAGED, archive=ARCHIVE)

        assert refusal.value.slug == NEVER_STAGED

    def test_a_transaction_that_fails_leaves_the_ticket_it_closed_open(
        self, abandoned: CloseStore
    ) -> None:
        with abandoned.transaction() as repository:
            assert status_of(repository, TICKET) is TicketStatus.STAGED
