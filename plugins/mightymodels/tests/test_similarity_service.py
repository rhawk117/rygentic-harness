"""The similarity service on the stores kept in memory: what a write says, and what `search` finds.

A text reaches the similarity store through the investigation, review and crashout services, so
the four run here on their stores kept in memory, which share the one similarity store. The index,
its rank and its cap are tested on SQLite in test_similarity.py.
"""

import pytest
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.review.schema import Emphasis, ReviewScope, StartPayload
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.similarity.matching import MATCH_OVERLAP
from mightymodels_plugin.tools.similarity.rendering import NO_MATCHES
from mightymodels_plugin.tools.similarity.schema import (
    Scout,
    SimilarityKind,
    SimilarityView,
    SpooledReport,
)
from mightymodels_plugin.tools.similarity.service import SimilarityService
from mightymodels_plugin.tools.similarity.tests.writes import (
    EACH_WRITE,
    ONLY_COMMON_WORDS,
    SHARES_ONE_WORD,
    STARTED,
    THE_DRAIN_LOOP,
    THE_DRAIN_LOOP_REWORDED,
    WRITES,
    Services,
    Write,
    ledger_entry,
    references_found,
    started_investigation,
    store_scout_report,
    write_crashout,
    write_ledger_entry,
    write_review_finding,
)


@pytest.fixture
def services(
    in_memory_investigation_service: InvestigationService,
    in_memory_review_service: ReviewService,
    in_memory_crashout_service: CrashoutService,
    in_memory_similarity_service: SimilarityService,
) -> Services:
    in_memory_review_service.start(
        StartPayload(scope=ReviewScope.CODEBASE, depth=Depth.DEEP, emphasis=Emphasis.BALANCED),
        started=STARTED,
    )
    return Services(
        investigations=in_memory_investigation_service,
        reviews=in_memory_review_service,
        crashouts=in_memory_crashout_service,
        similarity=in_memory_similarity_service,
    )


class TestTheKindOfAText:
    SPOOLED = 'the drain loop of the scout'

    @pytest.fixture
    def every_kind_written(self, services: Services) -> Services:
        for write in (write_ledger_entry, write_review_finding, write_crashout):
            write(services, THE_DRAIN_LOOP, 1)
        store_scout_report(services.similarity, self.SPOOLED)
        return services

    def test_search_can_be_held_to_one_kind(self, every_kind_written: Services) -> None:
        crashouts = every_kind_written.similarity.search(THE_DRAIN_LOOP, SimilarityKind.CRASHOUT)

        assert {match.kind for match in crashouts.matches} == {SimilarityKind.CRASHOUT}
        assert len(crashouts.matches) == 1


class TestAWriteOfANearDuplicate:
    @pytest.mark.parametrize(('write', 'kind'), WRITES)
    def test_names_the_earlier_row_in_its_answer(
        self, write: Write, kind: SimilarityKind, services: Services
    ) -> None:
        write(services, THE_DRAIN_LOOP, 1)
        (earlier,) = services.similarity.search(THE_DRAIN_LOOP, kind).matches
        answer = write(services, THE_DRAIN_LOOP_REWORDED, 2)

        assert f'resembles {kind} {earlier.reference} (overlap ' in answer

    @pytest.mark.parametrize(('write', 'kind'), WRITES)
    def test_is_stored_all_the_same_and_found_by_search(
        self, write: Write, kind: SimilarityKind, services: Services
    ) -> None:
        write(services, THE_DRAIN_LOOP, 1)
        write(services, THE_DRAIN_LOOP_REWORDED, 2)

        found = services.similarity.search(THE_DRAIN_LOOP, kind)

        assert [match.kind for match in found.matches] == [kind, kind]
        assert found.text.count(f'{kind} ') == 2

    def test_a_scout_report_names_the_earlier_row_too(self, services: Services) -> None:
        write_crashout(services, THE_DRAIN_LOOP, 1)
        (earlier,) = services.similarity.search(THE_DRAIN_LOOP, None).matches

        assert store_scout_report(services.similarity, THE_DRAIN_LOOP_REWORDED) == [
            earlier.reference
        ]

    def test_in_the_same_batch_matches_the_entry_before_it(self, services: Services) -> None:
        entries = [ledger_entry(text) for text in (THE_DRAIN_LOOP, THE_DRAIN_LOOP_REWORDED)]

        added = services.investigations.add(started_investigation(services), 1, entries)

        assert added.text.count('near-duplicate:') == 1

    def test_a_finding_that_merges_into_a_recorded_one_does_not_match_itself(
        self, services: Services
    ) -> None:
        write_review_finding(services, THE_DRAIN_LOOP, 1)
        answer = write_review_finding(services, THE_DRAIN_LOOP_REWORDED, 1)

        assert 'near-duplicate' not in answer


class TestATextWithNoCloseRow:
    @pytest.mark.parametrize(
        'text',
        [
            pytest.param(ONLY_COMMON_WORDS, id='only-common-words'),
            pytest.param(SHARES_ONE_WORD, id='one-shared-word'),
        ],
    )
    @pytest.mark.parametrize('write', EACH_WRITE)
    def test_gets_no_match(self, text: str, write: Write, services: Services) -> None:
        write(services, THE_DRAIN_LOOP, 1)

        assert 'near-duplicate' not in write(services, text, 2)

    def test_that_shares_only_common_words_with_every_row_finds_nothing_by_search(
        self, services: Services
    ) -> None:
        write_crashout(services, THE_DRAIN_LOOP, 1)

        assert references_found(services.similarity, ONLY_COMMON_WORDS) == []

    def test_that_shares_one_word_is_found_by_search_with_its_overlap(
        self, services: Services
    ) -> None:
        write_crashout(services, THE_DRAIN_LOOP, 1)

        (found,) = services.similarity.search(SHARES_ONE_WORD, None).matches

        assert 0 < found.overlap < MATCH_OVERLAP


class TestAQueryWithNoContentWord:
    @pytest.mark.parametrize(
        'query',
        [
            pytest.param('', id='empty'),
            pytest.param(ONLY_COMMON_WORDS, id='only-common-words'),
        ],
    )
    def test_finds_nothing_and_says_so(self, query: str, services: Services) -> None:
        write_crashout(services, THE_DRAIN_LOOP, 1)

        assert services.similarity.search(query, None) == SimilarityView(text=NO_MATCHES)


class TestAStoredScoutReport:
    REPORT = SpooledReport(
        repository_key=RepositoryKey('acme/widgets'),
        scout=Scout.CODE_SCOUT,
        target='the drain loop',
        report=THE_DRAIN_LOOP,
    )

    @pytest.fixture
    def report_stored(self, services: Services) -> SimilarityService:
        store_scout_report(services.similarity, THE_DRAIN_LOOP)
        return services.similarity

    def test_is_known_by_its_scout_and_target(self, report_stored: SimilarityService) -> None:
        assert report_stored.has_report_of(self.REPORT)

    @pytest.mark.parametrize(
        'change',
        [
            pytest.param({'scout': Scout.WEB_SCOUT}, id='another-scout'),
            pytest.param({'target': 'the retry queue'}, id='another-target'),
        ],
    )
    def test_is_not_the_report_of_another_scout_or_target(
        self, change: dict[str, object], report_stored: SimilarityService
    ) -> None:
        assert not report_stored.has_report_of(self.REPORT.model_copy(update=change))
