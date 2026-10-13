"""Every method of the similarity repository, on the store kept in memory and on SQLite.

One fixture hands out either store, so each case runs on both and the store kept in memory cannot
drift from the repository it stands in for. The store kept in memory holds no index, rank or cap,
so a case that reads more than one match compares them as a set: the order of a search is BM25's
on SQLite, and test_similarity.py tests it there.
"""

from contextlib import suppress

import pytest
from mightymodels.core.database import Database
from mightymodels.core.declarative import REPORT_LIMIT
from mightymodels.core.repository_key import RepositoryKey
from mightymodels.redaction import RedactedTextTooLongError
from mightymodels.tools.similarity.matching import content_words, overlap
from mightymodels.tools.similarity.repository import similarity_store
from mightymodels.tools.similarity.schema import (
    Duplicate,
    Match,
    Scout,
    SimilarityKind,
    SpooledReport,
)
from mightymodels.tools.similarity.store import (
    SimilarityRepository,
    SimilarityStore,
    Written,
)

THE_DRAIN_LOOP = 'the drain loop sleeps between every retry batch'
REWORDED = 'drain loop sleeps between every retry batches'
SHARES_ONE_WORD = 'drain the queue before shutdown completes'
ONLY_COMMON_WORDS = 'it was the and that they would have about this'
REPLACEMENT = 'replacement cache'
LEAKING = 'the drain loop leaks password=hunter2'
CREDENTIALS = '://a:b@'
FIRST = Written(kind=SimilarityKind.CRASHOUT, reference='#1', text=THE_DRAIN_LOOP)
SECOND = Written(kind=SimilarityKind.CRASHOUT, reference='#2', text=REWORDED)
UNLIKE = Written(kind=SimilarityKind.CRASHOUT, reference='#3', text=SHARES_ONE_WORD)
A_FINDING = Written(kind=SimilarityKind.REVIEW_FINDING, reference='run F1', text=THE_DRAIN_LOOP)
THE_FIRST = Match(kind=SimilarityKind.CRASHOUT, reference='#1', text=THE_DRAIN_LOOP, overlap=1.0)
REWORDED_OVERLAP = overlap(content_words(REWORDED), content_words(THE_DRAIN_LOOP))
REPORT = SpooledReport(
    repository_key=RepositoryKey('acme/widgets'),
    scout=Scout.CODE_SCOUT,
    target='the drain loop',
    report=THE_DRAIN_LOOP,
)
REPORT_REWORDED = REPORT.model_copy(update={'target': 'the retry queue', 'report': REWORDED})


class WriteFailedError(Exception):
    pass


@pytest.fixture
def sqlite_store(repository_database: Database) -> SimilarityStore:
    return similarity_store(repository_database)


@pytest.fixture(
    params=[
        pytest.param('in_memory_similarity_store', id='fake'),
        pytest.param('sqlite_store', id='sqlite'),
    ]
)
def store(request: pytest.FixtureRequest) -> SimilarityStore:
    return request.getfixturevalue(request.param)


@pytest.fixture
def first_stored(store: SimilarityStore) -> SimilarityStore:
    with store.transaction() as repository:
        repository.record(FIRST)
    return store


def found(store: SimilarityStore, query: str, kind: SimilarityKind | None = None) -> list[Match]:
    with store.transaction() as repository:
        return repository.search(query, kind=kind)


def test_the_store_and_its_repository_are_the_protocols(store: SimilarityStore) -> None:
    with store.transaction() as repository:
        assert isinstance(repository, SimilarityRepository)
    assert isinstance(store, SimilarityStore)


class TestSearch:
    def test_an_empty_store_holds_no_match(self, store: SimilarityStore) -> None:
        assert found(store, THE_DRAIN_LOOP) == []

    def test_a_stored_text_is_found_with_its_overlap(self, first_stored: SimilarityStore) -> None:
        assert found(first_stored, THE_DRAIN_LOOP) == [THE_FIRST]
        assert found(first_stored, REWORDED) == [
            THE_FIRST.model_copy(update={'overlap': REWORDED_OVERLAP})
        ]

    @pytest.mark.parametrize(
        'query',
        [
            pytest.param('', id='empty'),
            pytest.param(ONLY_COMMON_WORDS, id='only-common-words'),
            pytest.param(REPLACEMENT, id='no-shared-word'),
        ],
    )
    def test_a_query_sharing_no_content_word_finds_nothing(
        self, query: str, first_stored: SimilarityStore
    ) -> None:
        assert found(first_stored, query) == []

    def test_it_can_be_held_to_one_kind(self, first_stored: SimilarityStore) -> None:
        with first_stored.transaction() as repository:
            repository.record(A_FINDING)

        every_kind = found(first_stored, THE_DRAIN_LOOP)

        assert {(match.kind, match.reference) for match in every_kind} == {
            (SimilarityKind.CRASHOUT, '#1'),
            (SimilarityKind.REVIEW_FINDING, 'run F1'),
        }
        assert found(first_stored, THE_DRAIN_LOOP, SimilarityKind.CRASHOUT) == [THE_FIRST]
        assert found(first_stored, THE_DRAIN_LOOP, SimilarityKind.LEDGER_ENTRY) == []


class TestRecord:
    def test_the_first_text_resembles_nothing(self, store: SimilarityStore) -> None:
        with store.transaction() as repository:
            assert repository.record(FIRST) is None

    def test_a_reworded_text_names_the_earlier_one(self, first_stored: SimilarityStore) -> None:
        with first_stored.transaction() as repository:
            duplicate = repository.record(SECOND)

        earlier = THE_FIRST.model_copy(update={'overlap': REWORDED_OVERLAP})
        assert duplicate == Duplicate(written='#2', earlier=earlier)

    def test_a_text_sharing_one_word_is_stored_and_names_nothing(
        self, first_stored: SimilarityStore
    ) -> None:
        with first_stored.transaction() as repository:
            assert repository.record(UNLIKE) is None

        assert {match.reference for match in found(first_stored, 'drain')} == {'#1', '#3'}

    def test_a_text_stored_again_under_its_reference_replaces_the_old_one(
        self, first_stored: SimilarityStore
    ) -> None:
        with first_stored.transaction() as repository:
            same_again = repository.record(FIRST)
            replaced = repository.record(
                Written(kind=FIRST.kind, reference=FIRST.reference, text=REPLACEMENT)
            )

        assert (same_again, replaced) == (None, None)
        assert found(first_stored, THE_DRAIN_LOOP) == []
        assert [match.text for match in found(first_stored, REPLACEMENT)] == [REPLACEMENT]

    def test_the_text_is_redacted_on_its_way_in(self, store: SimilarityStore) -> None:
        with store.transaction() as repository:
            repository.record(Written(kind=SimilarityKind.CRASHOUT, reference='#1', text=LEAKING))

        (stored,) = found(store, 'drain')
        assert stored.text == 'the drain loop leaks [REDACTED:assignment]'

    def test_a_text_redaction_takes_past_the_limit_is_refused(self, store: SimilarityStore) -> None:
        lengthened = 'x' * (REPORT_LIMIT - len(CREDENTIALS)) + CREDENTIALS
        written = Written(kind=SimilarityKind.CRASHOUT, reference='#1', text=lengthened)

        with pytest.raises(RedactedTextTooLongError) as refused, store.transaction() as repository:
            repository.record(written)

        assert (refused.value.field, refused.value.limit) == ('text', REPORT_LIMIT)

    def test_a_text_of_a_failed_transaction_is_not_kept(self, store: SimilarityStore) -> None:
        with suppress(WriteFailedError), store.transaction() as repository:
            repository.record(FIRST)
            raise WriteFailedError

        assert found(store, THE_DRAIN_LOOP) == []


class TestRecordAll:
    def test_it_answers_the_duplicates_alone_and_a_text_matches_the_one_before_it(
        self, store: SimilarityStore
    ) -> None:
        with store.transaction() as repository:
            duplicates = repository.record_all([FIRST, UNLIKE, SECOND])

        earlier = THE_FIRST.model_copy(update={'overlap': REWORDED_OVERLAP})
        assert duplicates == [Duplicate(written='#2', earlier=earlier)]

    def test_no_texts_are_no_duplicates(self, store: SimilarityStore) -> None:
        with store.transaction() as repository:
            assert repository.record_all([]) == []


class TestScoutReports:
    @pytest.fixture
    def report_stored(self, store: SimilarityStore) -> SimilarityStore:
        with store.transaction() as repository:
            repository.add_scout_report(REPORT)
        return store

    def test_no_report_is_stored_at_first(self, store: SimilarityStore) -> None:
        with store.transaction() as repository:
            assert not repository.has_scout_report(REPORT)

    def test_a_stored_report_is_known_by_its_scout_and_target(
        self, report_stored: SimilarityStore
    ) -> None:
        with report_stored.transaction() as repository:
            assert repository.has_scout_report(REPORT)
            assert not repository.has_scout_report(REPORT_REWORDED)
            assert not repository.has_scout_report(
                REPORT.model_copy(update={'scout': Scout.WEB_SCOUT})
            )

    def test_its_text_is_stored_under_the_number_of_the_report(
        self, report_stored: SimilarityStore
    ) -> None:
        assert found(report_stored, THE_DRAIN_LOOP) == [
            Match(kind=SimilarityKind.SCOUT_REPORT, reference='1', text=THE_DRAIN_LOOP, overlap=1.0)
        ]

    def test_a_reworded_report_names_the_earlier_one(self, report_stored: SimilarityStore) -> None:
        with report_stored.transaction() as repository:
            duplicates = repository.add_scout_report(REPORT_REWORDED)

        assert [(duplicate.written, duplicate.earlier.reference) for duplicate in duplicates] == [
            ('2', '1')
        ]

    def test_the_first_report_resembles_nothing(self, store: SimilarityStore) -> None:
        with store.transaction() as repository:
            assert repository.add_scout_report(REPORT) == []
