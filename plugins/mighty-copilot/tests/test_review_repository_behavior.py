"""Every method of the review repositories, on the store kept in memory and on SQLite.

One fixture hands out either store, so each case runs on both and the store kept in memory cannot
drift from the repository it stands in for. SQLite reads a run's decisions and outcomes in no
stated order, so a case that reads more than one compares them sorted by finding.
"""

from contextlib import suppress
from dataclasses import replace
from operator import attrgetter

import pytest
from mightymodels.core.database import Database, Latest
from mightymodels.core.routing import Depth
from mightymodels.core.run_id import RunId
from mightymodels.core.slug import Slug
from mightymodels.tools.review.errors import RunNotFoundError
from mightymodels.tools.review.repository import RUNS_LISTED, review_store
from mightymodels.tools.review.schema import (
    Decision,
    Emphasis,
    Evidence,
    EvidenceKind,
    Finding,
    Kind,
    Persona,
    Result,
    ReviewRun,
    ReviewScope,
    Severity,
)
from mightymodels.tools.review.store import (
    DecidedFinding,
    DecisionRepository,
    ResolvedFinding,
    ReviewRepository,
    ReviewStore,
)
from mightymodels.tools.similarity.schema import Duplicate, Match, SimilarityKind

SLUG = Slug('retry-queue')
OTHER_SLUG = Slug('drain-loop')
AT = '2026-09-28T12:00:00+00:00'
THE_DRAIN_LOOP = 'the drain loop sleeps between every retry batch'
REWORDED = 'drain loop sleeps between every retry batches'
BY_FINDING = attrgetter('finding_id')
RUN = ReviewRun(
    run_id=RunId('20260928-120000'),
    slug=SLUG,
    scope=ReviewScope.TICKET,
    base='main',
    head='a' * 40,
    depth=Depth.DEEP,
    emphasis=Emphasis.BALANCED,
    weights={Persona.MERGE_VADER: 0.5, Persona.UNCLE_BOB: 0.5},
    personas=(Persona.MERGE_VADER, Persona.UNCLE_BOB),
    models={'merge-vader': 'opus', 'uncle-bob': None},
    created_at=AT,
)
LATER_RUN = replace(RUN, run_id=RunId('20260928-120005'), depth=Depth.QUICK)
WITHOUT_A_TICKET = replace(
    RUN,
    run_id=RunId('20260928-120009'),
    slug=None,
    scope=ReviewScope.CODEBASE,
    base=None,
    head=None,
)
NEVER_STARTED = RunId('20260101-000000')
REROUTED = {'merge-vader': 'sonnet'}
FIRST = Finding(
    id='F1',
    sources=('MV-1',),
    severity=Severity.HIGH,
    kind=Kind.DEFECT,
    security=True,
    title=THE_DRAIN_LOOP,
    location='src/queue.py:41',
    fix='wake the loop on a new batch',
    verify='uv run pytest -q',
    evidence=None,
    conflict=None,
)
SECOND = FIRST.model_copy(
    update={
        'id': 'F2',
        'sources': ('MV-2', 'UB-4'),
        'severity': Severity.MEDIUM,
        'kind': Kind.QUALITY,
        'security': False,
        'title': 'the retry budget is read twice',
        'evidence': Evidence(kind=EvidenceKind.METRIC, cite='uncle-bob-metrics.json'),
        'conflict': 'UB-4 rated Low, MV-2 rated Critical: the user decides',
    }
)
TENTH = FIRST.model_copy(update={'id': 'F10', 'title': 'a cache is never invalidated'})
FIX_THE_FIRST = DecidedFinding(finding_id='F1', decision=Decision.FIX, reason='', by='user', at=AT)
DEFER_THE_SECOND = DecidedFinding(
    finding_id='F2', decision=Decision.DEFER, reason='ticketed as PLAT-9', by='user', at=AT
)
THE_FIRST_FIXED = ResolvedFinding(
    finding_id='F1', result=Result.FIXED, commit='abc123', reason='', at=AT
)
THE_SECOND_FAILED = ResolvedFinding(
    finding_id='F2', result=Result.FAILED, commit='', reason='tests red', at=AT
)


class WriteFailedError(Exception):
    pass


@pytest.fixture
def sqlite_store(repository_database: Database) -> ReviewStore:
    return review_store(repository_database)


@pytest.fixture(
    params=[
        pytest.param('in_memory_review_store', id='fake'),
        pytest.param('sqlite_store', id='sqlite'),
    ]
)
def store(request: pytest.FixtureRequest) -> ReviewStore:
    return request.getfixturevalue(request.param)


@pytest.fixture
def started(store: ReviewStore) -> ReviewStore:
    with store.transaction() as repository:
        repository.record_run(RUN)
    return store


@pytest.fixture
def two_findings(started: ReviewStore) -> ReviewStore:
    with started.transaction() as repository:
        repository.record_findings(RUN.run_id, [FIRST, SECOND])
    return started


@pytest.fixture
def both_decided(two_findings: ReviewStore) -> ReviewStore:
    with two_findings.transaction() as repository:
        repository.decisions.record_dispositions(RUN.run_id, [FIX_THE_FIRST, DEFER_THE_SECOND])
        repository.decisions.record_outcome(RUN.run_id, THE_FIRST_FIXED)
        repository.decisions.record_outcome(RUN.run_id, THE_SECOND_FAILED)
    return two_findings


def dispositions(store: ReviewStore, run: RunId) -> list[DecidedFinding]:
    with store.transaction() as repository:
        return sorted(repository.decisions.dispositions(run), key=BY_FINDING)


def outcomes(store: ReviewStore, run: RunId) -> list[ResolvedFinding]:
    with store.transaction() as repository:
        return sorted(repository.decisions.outcomes(run), key=BY_FINDING)


def test_the_store_and_its_repositories_are_the_protocols(store: ReviewStore) -> None:
    with store.transaction() as repository:
        assert isinstance(repository, ReviewRepository)
        assert isinstance(repository.decisions, DecisionRepository)
    assert isinstance(store, ReviewStore)


class TestRun:
    def test_a_run_never_started_reads_as_none(self, started: ReviewStore) -> None:
        with started.transaction() as repository:
            assert repository.run(NEVER_STARTED) is None

    def test_a_run_reads_back_as_it_was_recorded(self, started: ReviewStore) -> None:
        with started.transaction() as repository:
            assert repository.run(RUN.run_id) == RUN
            assert repository.started_run(RUN.run_id) == RUN

    def test_a_run_with_no_ticket_base_or_head_reads_back_without_them(
        self, store: ReviewStore
    ) -> None:
        with store.transaction() as repository:
            repository.record_run(WITHOUT_A_TICKET)

            assert repository.run(WITHOUT_A_TICKET.run_id) == WITHOUT_A_TICKET

    def test_a_started_run_never_started_is_refused(self, started: ReviewStore) -> None:
        with pytest.raises(RunNotFoundError) as refused, started.transaction() as repository:
            repository.started_run(NEVER_STARTED)

        assert refused.value.run == NEVER_STARTED

    def test_the_run_of_a_failed_transaction_is_not_kept(self, store: ReviewStore) -> None:
        with suppress(WriteFailedError), store.transaction() as repository:
            repository.record_run(RUN)
            raise WriteFailedError

        with store.transaction() as repository:
            assert repository.run(RUN.run_id) is None


class TestRecordModels:
    def test_the_models_of_a_run_are_replaced_whole(self, started: ReviewStore) -> None:
        with started.transaction() as repository:
            repository.record_models(RUN.run_id, REROUTED)

        with started.transaction() as repository:
            assert repository.started_run(RUN.run_id) == replace(RUN, models=REROUTED)

    def test_the_models_of_a_run_never_started_are_refused(self, started: ReviewStore) -> None:
        with pytest.raises(RunNotFoundError), started.transaction() as repository:
            repository.record_models(NEVER_STARTED, REROUTED)


class TestLatestRuns:
    @pytest.fixture
    def one_past_the_window(self, store: ReviewStore) -> ReviewStore:
        with store.transaction() as repository:
            for second in range(RUNS_LISTED.rows + 1):
                repository.record_run(replace(RUN, run_id=RunId(f'20260928-1200{second:02d}')))
        return store

    def test_no_run_is_listed_as_none(self, store: ReviewStore) -> None:
        with store.transaction() as repository:
            assert repository.latest_runs() == Latest(rows=(), older_left_out=False)

    def test_the_runs_are_listed_oldest_first_whatever_order_they_were_recorded_in(
        self, store: ReviewStore
    ) -> None:
        with store.transaction() as repository:
            repository.record_run(WITHOUT_A_TICKET)
            repository.record_run(RUN)
            repository.record_run(LATER_RUN)

            assert repository.latest_runs() == Latest(
                rows=(RUN, LATER_RUN, WITHOUT_A_TICKET), older_left_out=False
            )

    def test_past_the_window_the_oldest_is_left_out_and_it_says_so(
        self, one_past_the_window: ReviewStore
    ) -> None:
        with one_past_the_window.transaction() as repository:
            listed = repository.latest_runs()

        assert listed.older_left_out
        assert len(listed.rows) == RUNS_LISTED.rows
        assert listed.rows[0].run_id == RunId('20260928-120001')


class TestLatestRun:
    def test_a_ticket_with_no_run_has_none(self, started: ReviewStore) -> None:
        with started.transaction() as repository:
            assert repository.latest_run(OTHER_SLUG) is None

    def test_it_is_the_newest_run_of_that_ticket(self, started: ReviewStore) -> None:
        of_another_ticket = replace(RUN, run_id=RunId('20260928-120007'), slug=OTHER_SLUG)
        with started.transaction() as repository:
            repository.record_run(of_another_ticket)
            repository.record_run(LATER_RUN)
            repository.record_run(WITHOUT_A_TICKET)

            assert repository.latest_run(SLUG) == LATER_RUN
            assert repository.latest_run(OTHER_SLUG) == of_another_ticket


class TestFindings:
    def test_a_run_with_no_finding_reads_empty(self, started: ReviewStore) -> None:
        with started.transaction() as repository:
            assert repository.findings(RUN.run_id) == []
            assert repository.findings(NEVER_STARTED) == []

    def test_the_findings_read_back_as_recorded_in_the_order_of_their_numbers(
        self, started: ReviewStore
    ) -> None:
        with started.transaction() as repository:
            repository.record_findings(RUN.run_id, [TENTH, SECOND, FIRST])

        with started.transaction() as repository:
            assert repository.findings(RUN.run_id) == [FIRST, SECOND, TENTH]

    def test_a_finding_recorded_again_under_its_number_replaces_the_old_one(
        self, two_findings: ReviewStore
    ) -> None:
        raised = FIRST.model_copy(
            update={'severity': Severity.CRITICAL, 'sources': ('MV-1', 'UB-1')}
        )
        with two_findings.transaction() as repository:
            repository.record_findings(RUN.run_id, [raised])

        with two_findings.transaction() as repository:
            assert repository.findings(RUN.run_id) == [raised, SECOND]

    def test_a_run_holds_its_own_findings_alone(self, two_findings: ReviewStore) -> None:
        with two_findings.transaction() as repository:
            repository.record_run(LATER_RUN)
            repository.record_findings(LATER_RUN.run_id, [TENTH])

        with two_findings.transaction() as repository:
            assert repository.findings(LATER_RUN.run_id) == [TENTH]
            assert repository.findings(RUN.run_id) == [FIRST, SECOND]

    def test_the_findings_of_a_failed_transaction_are_not_kept(self, started: ReviewStore) -> None:
        with suppress(WriteFailedError), started.transaction() as repository:
            repository.record_findings(RUN.run_id, [FIRST])
            raise WriteFailedError

        with started.transaction() as repository:
            assert repository.findings(RUN.run_id) == []
            assert repository.record_findings(RUN.run_id, [FIRST]) == []


class TestRecordFindings:
    def test_findings_unlike_any_earlier_title_name_no_duplicate(
        self, started: ReviewStore
    ) -> None:
        with started.transaction() as repository:
            assert repository.record_findings(RUN.run_id, [FIRST, SECOND]) == []

    def test_no_findings_are_no_duplicates(self, started: ReviewStore) -> None:
        with started.transaction() as repository:
            assert repository.record_findings(RUN.run_id, []) == []

    def test_a_title_reworded_from_an_earlier_one_names_it(self, two_findings: ReviewStore) -> None:
        reworded = TENTH.model_copy(update={'title': REWORDED})
        with two_findings.transaction() as repository:
            (duplicate,) = repository.record_findings(RUN.run_id, [reworded])

        earlier = Match(
            kind=SimilarityKind.REVIEW_FINDING,
            reference=f'{RUN.run_id} F1',
            text=THE_DRAIN_LOOP,
            overlap=duplicate.earlier.overlap,
        )
        assert duplicate == Duplicate(written=f'{RUN.run_id} F10', earlier=earlier)


class TestDecisions:
    def test_a_run_with_nothing_decided_reads_empty(self, two_findings: ReviewStore) -> None:
        assert dispositions(two_findings, RUN.run_id) == []
        assert outcomes(two_findings, RUN.run_id) == []

    def test_the_decisions_and_the_outcomes_read_back_as_recorded(
        self, both_decided: ReviewStore
    ) -> None:
        assert dispositions(both_decided, RUN.run_id) == [FIX_THE_FIRST, DEFER_THE_SECOND]
        assert outcomes(both_decided, RUN.run_id) == [THE_FIRST_FIXED, THE_SECOND_FAILED]

    def test_a_finding_decided_again_keeps_the_later_decision(
        self, both_decided: ReviewStore
    ) -> None:
        dismissed = replace(FIX_THE_FIRST, decision=Decision.DISMISS, reason='not reachable')
        with both_decided.transaction() as repository:
            repository.decisions.record_dispositions(RUN.run_id, [dismissed])

        assert dispositions(both_decided, RUN.run_id) == [dismissed, DEFER_THE_SECOND]

    def test_a_finding_resolved_again_keeps_the_later_outcome(
        self, both_decided: ReviewStore
    ) -> None:
        blocked = replace(THE_FIRST_FIXED, result=Result.BLOCKED, commit='', reason='no access')
        with both_decided.transaction() as repository:
            repository.decisions.record_outcome(RUN.run_id, blocked)

        assert outcomes(both_decided, RUN.run_id) == [blocked, THE_SECOND_FAILED]

    def test_no_decisions_recorded_changes_nothing(self, both_decided: ReviewStore) -> None:
        with both_decided.transaction() as repository:
            repository.decisions.record_dispositions(RUN.run_id, [])

        assert dispositions(both_decided, RUN.run_id) == [FIX_THE_FIRST, DEFER_THE_SECOND]

    def test_a_run_holds_its_own_decisions_alone(self, both_decided: ReviewStore) -> None:
        with both_decided.transaction() as repository:
            repository.record_run(LATER_RUN)
            repository.record_findings(LATER_RUN.run_id, [FIRST])

        assert dispositions(both_decided, LATER_RUN.run_id) == []
        assert outcomes(both_decided, LATER_RUN.run_id) == []

    def test_the_decisions_of_a_failed_transaction_are_not_kept(
        self, two_findings: ReviewStore
    ) -> None:
        with suppress(WriteFailedError), two_findings.transaction() as repository:
            repository.decisions.record_dispositions(RUN.run_id, [FIX_THE_FIRST])
            repository.decisions.record_outcome(RUN.run_id, THE_FIRST_FIXED)
            raise WriteFailedError

        assert dispositions(two_findings, RUN.run_id) == []
        assert outcomes(two_findings, RUN.run_id) == []


class TestReopen:
    def test_a_reopened_finding_loses_its_decision_and_its_outcome(
        self, both_decided: ReviewStore
    ) -> None:
        with both_decided.transaction() as repository:
            repository.decisions.reopen(RUN.run_id, ['F1'])

        assert dispositions(both_decided, RUN.run_id) == [DEFER_THE_SECOND]
        assert outcomes(both_decided, RUN.run_id) == [THE_SECOND_FAILED]

    @pytest.mark.parametrize(
        'finding_ids',
        [
            pytest.param([], id='none'),
            pytest.param(['F9'], id='a-finding-never-decided'),
        ],
    )
    def test_reopening_what_was_never_decided_changes_nothing(
        self, finding_ids: list[str], both_decided: ReviewStore
    ) -> None:
        with both_decided.transaction() as repository:
            repository.decisions.reopen(RUN.run_id, finding_ids)

        assert dispositions(both_decided, RUN.run_id) == [FIX_THE_FIRST, DEFER_THE_SECOND]
        assert outcomes(both_decided, RUN.run_id) == [THE_FIRST_FIXED, THE_SECOND_FAILED]

    def test_the_decisions_of_another_run_are_left_alone(self, both_decided: ReviewStore) -> None:
        with both_decided.transaction() as repository:
            repository.record_run(LATER_RUN)
            repository.record_findings(LATER_RUN.run_id, [FIRST])
            repository.decisions.record_dispositions(LATER_RUN.run_id, [FIX_THE_FIRST])
            repository.decisions.reopen(RUN.run_id, ['F1', 'F2'])

        assert dispositions(both_decided, RUN.run_id) == []
        assert dispositions(both_decided, LATER_RUN.run_id) == [FIX_THE_FIRST]
