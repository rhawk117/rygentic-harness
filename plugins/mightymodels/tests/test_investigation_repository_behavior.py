"""Every method of the investigation repository, on the store kept in memory and on SQLite.

One fixture hands out either store, so each case runs on both and the store kept in memory cannot
drift from the repository it stands in for.
"""

from contextlib import suppress
from dataclasses import replace

import pytest
from mightymodels_plugin.core.database import Database, Latest
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.investigation.repository import (
    INVESTIGATIONS_LISTED,
    investigation_store,
)
from mightymodels_plugin.tools.investigation.schema import EntryKind, Source
from mightymodels_plugin.tools.investigation.store import (
    InvestigationRepository,
    InvestigationStore,
    LedgerRecord,
)
from mightymodels_plugin.tools.similarity.schema import Duplicate, Match, SimilarityKind

LEDGER = Slug('20260928-queue-drains-slowly')
LATER_LEDGER = Slug('20260929-drain-loop-never-wakes')
NEVER_STARTED = Slug('20260930-never-started')
AT = '2026-09-28T12:00:00+00:00'
HEAD = 'a' * 40
THE_DRAIN_LOOP = 'the drain loop sleeps between every retry batch'
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
KNOWN = LedgerRecord(
    seq=2,
    round=1,
    kind=EntryKind.KNOWN,
    text=THE_DRAIN_LOOP,
    source=Source.CODE_SCOUT,
    cite='src/queue.py:41',
    supersedes=(),
    at=AT,
    head=HEAD,
)
ANSWER = LedgerRecord(
    seq=3,
    round=2,
    kind=EntryKind.OPEN,
    text='is the backoff thirty seconds',
    source=Source.WEB_SCOUT,
    cite=None,
    supersedes=(2,),
    at=AT,
    head=HEAD,
)
REWORDED = replace(ANSWER, seq=4, text='drain loop sleeps between every retry batches')


class AppendFailedError(Exception):
    pass


@pytest.fixture
def sqlite_store(repository_database: Database) -> InvestigationStore:
    return investigation_store(repository_database)


@pytest.fixture(
    params=[
        pytest.param('in_memory_investigation_store', id='fake'),
        pytest.param('sqlite_store', id='sqlite'),
    ]
)
def store(request: pytest.FixtureRequest) -> InvestigationStore:
    return request.getfixturevalue(request.param)


@pytest.fixture
def started(store: InvestigationStore) -> InvestigationStore:
    with store.transaction() as repository:
        repository.append(LEDGER, [TARGET])
    return store


@pytest.fixture
def two_rounds(started: InvestigationStore) -> InvestigationStore:
    with started.transaction() as repository:
        repository.append(LEDGER, [KNOWN, ANSWER])
    return started


def test_the_store_and_its_repository_are_the_protocols(store: InvestigationStore) -> None:
    with store.transaction() as repository:
        assert isinstance(repository, InvestigationRepository)
    assert isinstance(store, InvestigationStore)


class TestHasEntries:
    def test_an_investigation_never_started_has_none(self, started: InvestigationStore) -> None:
        with started.transaction() as repository:
            assert not repository.has_entries(NEVER_STARTED)

    def test_an_investigation_has_entries_once_its_target_is_stored(
        self, started: InvestigationStore
    ) -> None:
        with started.transaction() as repository:
            assert repository.has_entries(LEDGER)


class TestEntries:
    def test_an_investigation_never_started_reads_empty(self, started: InvestigationStore) -> None:
        with started.transaction() as repository:
            assert repository.entries(NEVER_STARTED) == []

    def test_a_ledger_reads_back_as_it_was_stored_in_the_order_of_its_numbers(
        self, two_rounds: InvestigationStore
    ) -> None:
        with two_rounds.transaction() as repository:
            assert repository.entries(LEDGER) == [TARGET, KNOWN, ANSWER]

    def test_entries_appended_out_of_order_read_in_the_order_of_their_numbers(
        self, started: InvestigationStore
    ) -> None:
        with started.transaction() as repository:
            repository.append(LEDGER, [ANSWER, KNOWN])

        with started.transaction() as repository:
            assert repository.entries(LEDGER) == [TARGET, KNOWN, ANSWER]

    def test_a_ledger_holds_its_own_entries_alone(self, two_rounds: InvestigationStore) -> None:
        with two_rounds.transaction() as repository:
            repository.append(LATER_LEDGER, [TARGET])

        with two_rounds.transaction() as repository:
            assert repository.entries(LATER_LEDGER) == [TARGET]
            assert len(repository.entries(LEDGER)) == 3


class TestAppend:
    def test_an_entry_unlike_any_earlier_text_names_no_duplicate(
        self, started: InvestigationStore
    ) -> None:
        with started.transaction() as repository:
            assert repository.append(LEDGER, [KNOWN, ANSWER]) == []

    def test_an_entry_reworded_from_an_earlier_one_names_it(
        self, two_rounds: InvestigationStore
    ) -> None:
        with two_rounds.transaction() as repository:
            (duplicate,) = repository.append(LEDGER, [REWORDED])

        earlier = Match(
            kind=SimilarityKind.LEDGER_ENTRY,
            reference=f'{LEDGER} e2',
            text=THE_DRAIN_LOOP,
            overlap=duplicate.earlier.overlap,
        )
        assert duplicate == Duplicate(written=f'{LEDGER} e4', earlier=earlier)

    def test_no_entries_are_no_duplicates_and_nothing_stored(
        self, started: InvestigationStore
    ) -> None:
        with started.transaction() as repository:
            assert repository.append(LEDGER, []) == []
            assert repository.entries(LEDGER) == [TARGET]

    def test_the_entries_of_a_failed_transaction_are_not_kept(
        self, started: InvestigationStore
    ) -> None:
        with suppress(AppendFailedError), started.transaction() as repository:
            repository.append(LEDGER, [KNOWN])
            raise AppendFailedError

        with started.transaction() as repository:
            assert repository.entries(LEDGER) == [TARGET]
            assert repository.append(LEDGER, [REWORDED]) == []


class TestUnrecorded:
    def test_it_names_the_investigations_with_no_ledger_in_the_order_given(
        self, started: InvestigationStore
    ) -> None:
        with started.transaction() as repository:
            asked = [NEVER_STARTED, LEDGER, LATER_LEDGER]

            assert repository.unrecorded(asked) == [NEVER_STARTED, LATER_LEDGER]

    def test_none_asked_about_is_none_unrecorded(self, started: InvestigationStore) -> None:
        with started.transaction() as repository:
            assert repository.unrecorded([]) == []


class TestLatestRounds:
    @pytest.fixture
    def one_past_the_window(self, store: InvestigationStore) -> InvestigationStore:
        with store.transaction() as repository:
            for number in range(INVESTIGATIONS_LISTED.rows + 1):
                repository.append(Slug(f'20260928-ledger-{number:03d}'), [TARGET])
        return store

    def test_no_investigation_is_no_round(self, store: InvestigationStore) -> None:
        with store.transaction() as repository:
            assert repository.latest_rounds() == Latest(rows=(), older_left_out=False)

    def test_each_investigation_is_listed_with_its_latest_round_oldest_first(
        self, two_rounds: InvestigationStore
    ) -> None:
        with two_rounds.transaction() as repository:
            repository.append(LATER_LEDGER, [TARGET])

            assert repository.latest_rounds() == Latest(
                rows=((LEDGER.root, 2), (LATER_LEDGER.root, 0)), older_left_out=False
            )

    def test_past_the_window_the_oldest_is_left_out_and_it_says_so(
        self, one_past_the_window: InvestigationStore
    ) -> None:
        with one_past_the_window.transaction() as repository:
            listed = repository.latest_rounds()

        assert listed.older_left_out
        assert len(listed.rows) == INVESTIGATIONS_LISTED.rows
        assert listed.rows[0] == ('20260928-ledger-001', 0)
