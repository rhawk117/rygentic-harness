"""The similarity table on SQLite: its index, its rank, its cap and its stored rows.

What a write says about an earlier text, and what the service finds on the stores kept in memory,
is in test_similarity_service.py.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels_plugin.core.database import DATABASE_NAME, Database, open_database
from mightymodels_plugin.core.declarative import REPORT_LIMIT
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.redaction import RedactedTextTooLongError
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.review.schema import Emphasis, ReviewScope, StartPayload
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.similarity.matching import (
    CANDIDATE_CAP,
    MATCH_OVERLAP,
    content_words,
    overlap,
)
from mightymodels_plugin.tools.similarity.rendering import NO_MATCHES
from mightymodels_plugin.tools.similarity.repository import similarity_store
from mightymodels_plugin.tools.similarity.schema import SimilarityKind, SimilarityView
from mightymodels_plugin.tools.similarity.service import SimilarityService
from mightymodels_plugin.tools.similarity.store import Written
from mightymodels_plugin.tools.similarity.tables import SimilarityRow
from mightymodels_plugin.tools.similarity.tests.writes import (
    EACH_WRITE,
    ONLY_COMMON_WORDS,
    SHARES_ONE_WORD,
    STARTED,
    THE_DRAIN_LOOP,
    THE_DRAIN_LOOP_REWORDED,
    Services,
    Write,
    references_found,
    store_scout_report,
    write_crashout,
    write_ledger_entry,
    write_review_finding,
)
from mightymodels_plugin.tools.tests.support import StateServer, selects_sent_to, text_of

OTHER_KEY = RepositoryKey('acme/gadgets')
CREDENTIALS = '://a:b@'
WORDS = 'the drain loop sleeps between every retry batch '


def words_of(length: int) -> str:
    return (WORDS * (length // len(WORDS) + 1))[:length]


@pytest.fixture
def services(
    investigation_service: InvestigationService,
    review_service: ReviewService,
    crashout_service: CrashoutService,
    similarity_service: SimilarityService,
) -> Services:
    review_service.start(
        StartPayload(scope=ReviewScope.CODEBASE, depth=Depth.DEEP, emphasis=Emphasis.BALANCED),
        started=STARTED,
    )
    return Services(
        investigations=investigation_service,
        reviews=review_service,
        crashouts=crashout_service,
        similarity=similarity_service,
    )


@pytest.fixture
def another_repository(data_directory: Path, spool: Path) -> Generator[SimilarityService]:
    with open_database(data_directory.joinpath(DATABASE_NAME), OTHER_KEY, ROW_TYPES) as database:
        yield SimilarityService(
            store=similarity_store(database), spool=spool, repository_key=OTHER_KEY
        )


class TestTheMatchConstants:
    def test_a_reworded_text_is_over_the_threshold_and_a_text_sharing_one_word_is_under_it(
        self,
    ) -> None:
        reworded = overlap(content_words(THE_DRAIN_LOOP), content_words(THE_DRAIN_LOOP_REWORDED))
        shares_one = overlap(content_words(THE_DRAIN_LOOP), content_words(SHARES_ONE_WORD))

        assert shares_one < MATCH_OVERLAP <= reworded

    def test_a_text_of_common_words_has_no_content_word(self) -> None:
        assert content_words(ONLY_COMMON_WORDS) == frozenset()

    def test_the_marker_redaction_leaves_is_no_content_word(self) -> None:
        assert content_words('uses [REDACTED:api-key] and') == frozenset({'uses'})


class TestTheTypeColumn:
    SPOOLED = 'the drain loop of the scout'

    @pytest.fixture
    def every_kind_written(self, services: Services, repository_database: Database) -> list[str]:
        for write in (write_ledger_entry, write_review_finding, write_crashout):
            write(services, THE_DRAIN_LOOP, 1)
        store_scout_report(services.similarity, self.SPOOLED)
        with repository_database.transaction() as session:
            return sorted(session.scalars(sql.select(SimilarityRow.kind).distinct()))

    def test_it_covers_ledger_entries_scout_reports_review_findings_and_crashouts(
        self, every_kind_written: list[str]
    ) -> None:
        assert every_kind_written == sorted(SimilarityKind)


class TestARowUnderAnotherKey:
    @pytest.fixture
    def written_under_the_other_key(
        self, another_repository: SimilarityService, services: Services
    ) -> Services:
        store_scout_report(another_repository, THE_DRAIN_LOOP)
        return services

    @pytest.mark.parametrize('write', EACH_WRITE)
    def test_is_not_matched_by_a_write(
        self, write: Write, written_under_the_other_key: Services
    ) -> None:
        assert 'near-duplicate' not in write(written_under_the_other_key, THE_DRAIN_LOOP, 1)

    def test_is_not_returned_by_search(self, written_under_the_other_key: Services) -> None:
        searched = written_under_the_other_key.similarity.search(THE_DRAIN_LOOP, None)

        assert searched.matches == ()

    def test_does_not_see_the_rows_of_the_first_key(
        self, another_repository: SimilarityService, services: Services
    ) -> None:
        write_crashout(services, THE_DRAIN_LOOP, 1)

        assert another_repository.search(THE_DRAIN_LOOP, None).matches == ()

    def test_does_not_take_a_candidate_place_of_the_first_keys_rows(
        self, another_repository: SimilarityService, services: Services
    ) -> None:
        for number in range(CANDIDATE_CAP + 1):
            store_scout_report(another_repository, f'{THE_DRAIN_LOOP} copy{number}')
        write_crashout(services, THE_DRAIN_LOOP, 1)

        assert len(services.similarity.search(THE_DRAIN_LOOP, None).matches) == 1


class TestTheCandidateCap:
    @pytest.fixture
    def more_rows_than_the_cap(self, services: Services) -> Services:
        for number in range(CANDIDATE_CAP + 5):
            write_crashout(services, f'drain copy{number}', number)
        return services

    def test_search_returns_no_more_rows_than_the_cap(
        self, more_rows_than_the_cap: Services
    ) -> None:
        found = more_rows_than_the_cap.similarity.search('drain', None)

        assert len(found.matches) == CANDIDATE_CAP

    def test_a_write_reads_no_more_candidates_than_the_cap(
        self, more_rows_than_the_cap: Services, repository_database: Database
    ) -> None:
        with selects_sent_to(repository_database) as selects:
            write_crashout(more_rows_than_the_cap, 'drain copy1', 99)

        assert max(selects.rows_fetched()) <= CANDIDATE_CAP


class TestStoredText:
    LEAKING = 'the drain loop leaks password=hunter2 and token=abc123'

    @pytest.fixture
    def stored_text(self, repository_database: Database) -> str:
        with similarity_store(repository_database).transaction() as repository:
            repository.record(
                Written(kind=SimilarityKind.CRASHOUT, reference='#1', text=self.LEAKING)
            )
        with repository_database.transaction() as session:
            return session.scalars(sql.select(SimilarityRow.text)).one()

    def test_is_redacted(self, stored_text: str) -> None:
        assert 'hunter2' not in stored_text
        assert 'abc123' not in stored_text
        assert '[REDACTED:assignment]' in stored_text

    def test_that_redaction_takes_past_the_column_is_refused_and_nothing_is_stored(
        self, repository_database: Database, similarity_service: SimilarityService
    ) -> None:
        lengthened = words_of(REPORT_LIMIT - len(CREDENTIALS)) + CREDENTIALS
        written = Written(kind=SimilarityKind.CRASHOUT, reference='#1', text=lengthened)

        with (
            pytest.raises(RedactedTextTooLongError) as refused,
            similarity_store(repository_database).transaction() as repository,
        ):
            repository.record(written)

        assert (refused.value.field, refused.value.limit) == ('text', REPORT_LIMIT)
        assert refused.value.length > REPORT_LIMIT
        assert references_found(similarity_service, lengthened) == []


class TestTheIndexFollowsTheTable:
    @pytest.fixture
    def stored_then_replaced(
        self, repository_database: Database, similarity_service: SimilarityService
    ) -> SimilarityService:
        written = Written(kind=SimilarityKind.CRASHOUT, reference='#1', text=THE_DRAIN_LOOP)
        with similarity_store(repository_database).transaction() as repository:
            repository.record(written)
        with similarity_store(repository_database).transaction() as repository:
            repository.record(
                Written(kind=written.kind, reference=written.reference, text='replacement cache')
            )
        return similarity_service

    def test_a_text_stored_again_under_its_reference_replaces_the_old_words(
        self, stored_then_replaced: SimilarityService
    ) -> None:
        assert references_found(stored_then_replaced, THE_DRAIN_LOOP) == []
        assert references_found(stored_then_replaced, 'replacement cache') == ['#1']

    def test_a_row_deleted_from_the_table_leaves_the_index(
        self, stored_then_replaced: SimilarityService, repository_database: Database
    ) -> None:
        with repository_database.transaction() as session:
            session.execute(sql.delete(SimilarityRow))

        assert references_found(stored_then_replaced, 'replacement cache') == []


class TestCallerTextInAQuery:
    OPERATORS = (
        pytest.param('"drain" OR NOT "loop', id='unbalanced-quote'),
        pytest.param('drain AND', id='dangling-operator'),
        pytest.param('drain NEAR(loop sleeps, 1)', id='near'),
        pytest.param('text:drain', id='column-filter'),
        pytest.param('drain* ^loop (sleeps', id='prefix-initial-and-bracket'),
        pytest.param("drain' OR 1=1 --", id='sql'),
        pytest.param('-drain +loop {text}: sleeps', id='plus-minus-and-braces'),
    )

    @pytest.fixture
    def drain_stored(self, services: Services) -> SimilarityService:
        write_crashout(services, THE_DRAIN_LOOP, 1)
        return services.similarity

    @pytest.mark.parametrize('query', OPERATORS)
    def test_cannot_change_the_query_or_break_its_syntax(
        self, query: str, drain_stored: SimilarityService
    ) -> None:
        assert len(drain_stored.search(query, None).matches) == 1

    @pytest.mark.parametrize('query', ['', ' ', '"', '* ( ) : ^ -', 'NOT', 'OR AND NEAR'])
    def test_that_holds_no_content_word_finds_nothing_and_raises_nothing(
        self, query: str, drain_stored: SimilarityService
    ) -> None:
        assert drain_stored.search(query, None) == SimilarityView(text=NO_MATCHES)

    def test_is_bound_as_a_parameter_and_never_part_of_the_statement(
        self, drain_stored: SimilarityService, repository_database: Database
    ) -> None:
        with selects_sent_to(repository_database) as selects:
            drain_stored.search('uniqueprobeword', None)

        sent = [select for select in selects.sent if 'bm25' in select.sql]
        assert len(sent) == 1
        assert 'uniqueprobeword' not in sent[0].sql
        assert '"uniqueprobeword"' in sent[0].parameters


class TestTheSimilarityTool:
    @pytest.fixture
    def searched(self, state_server: StateServer) -> tuple[str, str]:
        written, found, missed = state_server.call(
            (
                'crashout',
                {
                    'action': 'add',
                    'entry': {
                        'severity': 'heated',
                        'verdict': 'deserved',
                        'rant': 'why',
                        'failures': ['did it'],
                        'root_cause': THE_DRAIN_LOOP,
                        'corrective_action': 'stop',
                        'barked_back': False,
                    },
                },
            ),
            ('similarity', {'action': 'search', 'query': THE_DRAIN_LOOP_REWORDED}),
            ('similarity', {'action': 'search'}),
        )
        assert not written.is_error
        return text_of(found), text_of(missed)

    def test_search_answers_the_stored_row(self, searched: tuple[str, str]) -> None:
        assert 'crashout #1 (overlap' in searched[0]

    def test_search_without_a_query_says_what_it_needs(self, searched: tuple[str, str]) -> None:
        assert 'search needs a query holding the text to look for' in searched[1]
