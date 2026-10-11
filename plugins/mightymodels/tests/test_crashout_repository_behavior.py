"""Every method of the crashout repository, on the store kept in memory and on SQLite.

One fixture hands out either store, so each case runs on both and the store kept in memory cannot
drift from the repository it stands in for.
"""

from contextlib import suppress

import pytest
from mightymodels_plugin.core.database import Database, Latest
from mightymodels_plugin.tools.crashout.repository import JOURNAL_WINDOW, crashout_store
from mightymodels_plugin.tools.crashout.schema import JournaledCrashout, Severity, Verdict
from mightymodels_plugin.tools.crashout.store import CrashoutRepository, CrashoutStore, Journaled
from mightymodels_plugin.tools.similarity.schema import Duplicate, Match, SimilarityKind

AT = '2026-09-28T00:00:00+00:00'
SKIPPED_TESTS = JournaledCrashout(
    at=AT,
    ticket='retry-queue',
    branch='fix/retry-queue',
    severity=Severity.HEATED,
    verdict=Verdict.DESERVED,
    rant='WHY did you skip the tests\n  AGAIN',
    failures=('skipped the tests', 'claimed done'),
    root_cause='optimised for speed',
    corrective_action='run the gate before reporting',
    barked_back=False,
)
WRONG_BRANCH = JournaledCrashout(
    at='2026-09-29T00:00:00+00:00',
    ticket=None,
    branch=None,
    severity=Severity.FULL_MELTDOWN,
    verdict=Verdict.SPLIT,
    rant='that was my branch',
    failures=('committed to main',),
    root_cause='the branch was never checked',
    corrective_action='check the branch first',
    barked_back=True,
)
SAME_CAUSE = WRONG_BRANCH.model_copy(update={'root_cause': 'optimised for speed'})


class JournalFailedError(Exception):
    pass


@pytest.fixture
def sqlite_store(repository_database: Database) -> CrashoutStore:
    return crashout_store(repository_database)


@pytest.fixture(
    params=[
        pytest.param('in_memory_crashout_store', id='fake'),
        pytest.param('sqlite_store', id='sqlite'),
    ]
)
def store(request: pytest.FixtureRequest) -> CrashoutStore:
    return request.getfixturevalue(request.param)


@pytest.fixture
def journal_of_two(store: CrashoutStore) -> CrashoutStore:
    with store.transaction() as repository:
        repository.journal(SKIPPED_TESTS)
        repository.journal(WRONG_BRANCH)
    return store


def test_the_store_and_its_repository_are_the_protocols(store: CrashoutStore) -> None:
    with store.transaction() as repository:
        assert isinstance(repository, CrashoutRepository)
    assert isinstance(store, CrashoutStore)


class TestAnEmptyJournal:
    def test_the_latest_crashouts_are_none(self, store: CrashoutStore) -> None:
        with store.transaction() as repository:
            assert repository.latest_crashouts() == Latest(rows=(), older_left_out=False)

    def test_there_is_no_latest_crashout(self, store: CrashoutStore) -> None:
        with store.transaction() as repository:
            assert repository.latest_crashout() is None


class TestJournal:
    def test_a_crashout_is_numbered_by_its_place_in_the_journal(self, store: CrashoutStore) -> None:
        with store.transaction() as repository:
            first = repository.journal(SKIPPED_TESTS)
            second = repository.journal(WRONG_BRANCH)

        assert first == Journaled(number=1, duplicates=[])
        assert second == Journaled(number=2, duplicates=[])

    def test_the_number_goes_on_from_an_earlier_transaction(
        self, journal_of_two: CrashoutStore
    ) -> None:
        with journal_of_two.transaction() as repository:
            assert repository.journal(SKIPPED_TESTS).number == 3

    def test_a_root_cause_stored_before_is_answered_as_a_duplicate(
        self, journal_of_two: CrashoutStore
    ) -> None:
        with journal_of_two.transaction() as repository:
            journaled = repository.journal(SAME_CAUSE)

        earlier = Match(
            kind=SimilarityKind.CRASHOUT, reference='#1', text='optimised for speed', overlap=1.0
        )
        assert journaled == Journaled(
            number=3, duplicates=[Duplicate(written='#3', earlier=earlier)]
        )

    def test_a_crashout_of_a_failed_transaction_is_not_kept(
        self, journal_of_two: CrashoutStore
    ) -> None:
        with suppress(JournalFailedError), journal_of_two.transaction() as repository:
            repository.journal(SAME_CAUSE)
            raise JournalFailedError

        with journal_of_two.transaction() as repository:
            assert repository.latest_crashout() == WRONG_BRANCH
            assert repository.journal(SAME_CAUSE).number == 3


class TestLatest:
    def test_the_latest_crashouts_read_oldest_first_as_they_were_journaled(
        self, journal_of_two: CrashoutStore
    ) -> None:
        with journal_of_two.transaction() as repository:
            latest = repository.latest_crashouts()

        assert latest == Latest(rows=(SKIPPED_TESTS, WRONG_BRANCH), older_left_out=False)

    def test_the_latest_crashout_is_the_newest(self, journal_of_two: CrashoutStore) -> None:
        with journal_of_two.transaction() as repository:
            assert repository.latest_crashout() == WRONG_BRANCH


class TestAJournalPastTheWindow:
    @pytest.fixture
    def one_past_the_window(self, store: CrashoutStore) -> CrashoutStore:
        with store.transaction() as repository:
            repository.journal(SKIPPED_TESTS)
            for _ in range(JOURNAL_WINDOW.rows):
                repository.journal(WRONG_BRANCH)
        return store

    def test_the_latest_crashouts_leave_the_oldest_out_and_say_so(
        self, one_past_the_window: CrashoutStore
    ) -> None:
        with one_past_the_window.transaction() as repository:
            latest = repository.latest_crashouts()

        assert latest.older_left_out
        assert latest.rows == (WRONG_BRANCH,) * JOURNAL_WINDOW.rows
