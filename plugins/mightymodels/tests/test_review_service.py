"""The review service on the review store and the git history kept in memory.

What needs a repository on disk is in test_review_in_a_repository.py.
"""

from datetime import UTC, datetime

import pytest
from mightymodels_plugin.core.run_id import InvalidRunIdError, RunId, parsed_run_id
from mightymodels_plugin.tools.review.schema import Shape, Verdict
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.review.tests.workspace import (
    ADVANCED,
    BALANCED,
    REJECTED,
    SLUG,
    Workspace,
    finding,
)
from pydantic import ValidationError

NON_ASCII_DIGIT_RUN_ID = '2026010\u0662-000000'


def run_state(workspace: Workspace, run: RunId) -> dict[str, object]:
    with workspace.reviews.store.transaction() as repository:
        started = repository.started_run(run)
    return {
        'personas': list(started.personas),
        'models': started.models,
        'head': started.head,
    }


def stored_texts(workspace: Workspace, run: RunId) -> list[str]:
    with workspace.reviews.store.transaction() as repository:
        findings = repository.findings(run)
    return [str(value) for finding in findings for value in finding.model_dump().values()]


def test_deep_review_runs_both_personas(workspace: Workspace) -> None:
    head = workspace.git.commit()
    run = workspace.start(depth='deep')
    state = run_state(workspace, run)
    assert state['personas'] == ['merge-vader', 'uncle-bob']
    assert state['head'] == head


def test_deep_review_runs_both_personas_on_opus(workspace: Workspace) -> None:
    run = workspace.start(depth='deep')
    assert run_state(workspace, run)['models'] == {
        'merge-vader-reviewer': 'opus',
        'uncle-bob-reviewer': 'opus',
    }


def test_quick_review_runs_the_heavier_persona_on_sonnet(workspace: Workspace) -> None:
    run = workspace.start(depth='quick', emphasis='maintainability')
    assert run_state(workspace, run)['models'] == {'uncle-bob-reviewer': 'sonnet'}


def test_quick_review_with_tied_weights_needs_a_persona(workspace: Workspace) -> None:
    outcome = workspace.try_start({'scope': 'codebase', 'depth': 'quick', 'emphasis': 'balanced'})
    assert outcome.code == REJECTED
    assert 'pass persona' in outcome.err


def test_standard_review_drops_a_persona_below_the_threshold(workspace: Workspace) -> None:
    weights = {'merge-vader': 0.8, 'uncle-bob': 0.2}
    run = workspace.start(depth='standard', emphasis='custom', weights=weights)
    assert run_state(workspace, run)['models'] == {'merge-vader-reviewer': 'opus'}


def test_custom_weights_must_sum_to_one(workspace: Workspace) -> None:
    weights = {'merge-vader': 0.8, 'uncle-bob': 0.8}
    outcome = workspace.try_start(
        {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'custom', 'weights': weights}
    )
    assert 'must sum to 1' in outcome.err


def test_findings_get_stable_ids_and_uncle_bob_blockers_become_high(
    workspace: Workspace,
) -> None:
    run = workspace.start(depth='deep')
    batch = [
        finding('MV-1', 'High', 'src/queue.py:10', security=True),
        finding('UB-1', 'Blocker', 'src/store.py:4-9'),
    ]
    outcome = workspace.add(run, batch)
    gate = workspace.gate(run).out.splitlines()
    assert 'recorded: F1, F2' in outcome.out
    assert gate[0].startswith('F1\tHigh security\t[MV-1]')
    assert gate[1].startswith('F2\tHigh\t[UB-1]')


def test_overlapping_findings_merge_and_keep_the_higher_severity(workspace: Workspace) -> None:
    run = workspace.start(depth='deep')
    workspace.add(run, [finding('MV-2', 'Medium', 'src/q.py:10-20')])
    workspace.add(run, [finding('UB-4', 'High', 'src/q.py:15')])
    gate = workspace.gate(run).out
    assert gate.startswith('F1\tHigh\t[MV-2/UB-4]\tsrc/q.py:15\tUB-4 title')
    assert 'conflict' not in gate


def test_a_two_level_gap_is_flagged_for_the_user(workspace: Workspace) -> None:
    run = workspace.start(depth='deep')
    batch = [finding('MV-1', 'Critical', 'src/q.py:3'), finding('UB-1', 'Low', 'src/q.py:3')]
    workspace.add(run, batch)
    gate = workspace.gate(run).out
    assert 'conflict: UB-1 rated Low, MV-1 rated Critical: the user decides' in gate


def test_quality_findings_need_structured_evidence(workspace: Workspace) -> None:
    run = workspace.start(depth='deep')
    preference = finding('UB-3', 'Medium', 'src/q.py:1', kind='quality')
    refused = workspace.add(run, [preference])
    metric = {'kind': 'metric', 'cite': 'uncle-bob-metrics.json functions_over_20_loc'}
    backed = workspace.add(
        run, [finding('UB-3', 'Medium', 'src/q.py:1', kind='quality', evidence=metric)]
    )
    assert refused.code == REJECTED
    assert 'needs structured evidence' in refused.err
    assert backed.code == ADVANCED


def test_a_bad_finding_rejects_the_whole_batch(workspace: Workspace) -> None:
    run = workspace.start(depth='deep')
    batch = [finding('MV-1', 'High', 'src/q.py:1'), finding('MV-2', 'High', 'nowhere')]
    outcome = workspace.add(run, batch)
    assert 'finding 1: location must be' in outcome.err
    assert workspace.gate(run).out == 'no findings recorded\n'


@pytest.mark.parametrize(
    ('location', 'problem'),
    [
        pytest.param('src/q.py:0', 'location line 0 is below 1', id='line-zero'),
        pytest.param(
            'src/q.py:9-3', 'location range 9-3 ends before it starts', id='reversed-range'
        ),
    ],
)
def test_a_location_that_is_not_a_span_rejects_the_whole_batch(
    workspace: Workspace, location: str, problem: str
) -> None:
    run = workspace.start(depth='deep')
    batch = [finding('MV-1', 'High', 'src/q.py:1'), finding('MV-2', 'High', location)]
    outcome = workspace.add(run, batch)
    assert outcome.err.startswith(f'finding 1: {problem}')
    assert workspace.gate(run).out == 'no findings recorded\n'


def test_secrets_in_findings_are_redacted(workspace: Workspace) -> None:
    run = workspace.start(depth='deep')
    leaked = finding('MV-1', 'Critical', 'cfg.py:2', title='hardcoded password=hunter22')
    workspace.add(run, [leaked])
    stored = ' '.join(stored_texts(workspace, run))
    assert 'hunter22' not in stored
    assert '[REDACTED:assignment]' in stored


def test_weights_order_findings_inside_a_severity(workspace: Workspace) -> None:
    run = workspace.start(depth='deep', emphasis='maintainability')
    batch = [finding('MV-1', 'Medium', 'a.py:1'), finding('UB-1', 'Medium', 'b.py:1')]
    workspace.add(run, batch)
    gate = workspace.gate(run).out.splitlines()
    assert [line.split('\t')[2] for line in gate] == ['[UB-1]', '[MV-1]']


def test_accepting_risk_needs_a_reason(workspace: Workspace) -> None:
    run = workspace.start(depth='deep')
    workspace.add(run, [finding('MV-1', 'High', 'a.py:1')])
    outcome = workspace.dispose(run, by='user', decisions={'F1': {'decision': 'accept-risk'}})
    assert outcome.code == REJECTED
    assert 'accept-risk needs a reason' in outcome.err


def test_the_verdict_follows_the_decisions_and_the_fixes(workspace: Workspace) -> None:
    run = workspace.start(depth='deep')
    batch = [finding('MV-1', 'High', 'a.py:1'), finding('MV-2', 'Medium', 'b.py:1')]
    workspace.add(run, batch)
    before = workspace.report(run)
    decisions = {
        'F1': {'decision': 'fix'},
        'F2': {'decision': 'defer', 'reason': 'ticketed as PLAT-9'},
    }
    workspace.dispose(run, by='user', decisions=decisions)
    workspace.resolve(run, finding='F1', result='fixed', commit='abc123')
    after = workspace.report(run, Shape.COMMENT)
    assert before.verdict == Verdict.BLOCK
    assert after.verdict == Verdict.CONDITIONS
    assert '**Verdict: MERGE WITH CONDITIONS**' in after.out
    assert '- F1 (High, fixed): MV-1 title. `a.py:1`' in after.out


def test_only_findings_chosen_for_fixing_are_resolved(workspace: Workspace) -> None:
    run = workspace.start(depth='deep')
    workspace.add(run, [finding('MV-1', 'High', 'a.py:1')])
    outcome = workspace.resolve(run, finding='F1', result='fixed', commit='abc')
    assert 'only a finding the user chose to fix is resolved' in outcome.err


def test_a_path_shaped_run_id_is_refused() -> None:
    refused = parsed_run_id('../../etc')
    assert isinstance(refused, InvalidRunIdError)
    assert "run id '../../etc' is not valid" in str(refused)
    with pytest.raises(ValidationError):
        RunId('../../etc')


def test_a_run_id_holding_a_non_ascii_digit_is_refused() -> None:
    refused = parsed_run_id(NON_ASCII_DIGIT_RUN_ID)
    assert isinstance(refused, InvalidRunIdError)
    with pytest.raises(ValidationError):
        RunId(NON_ASCII_DIGIT_RUN_ID)


class TestDecidedBy:
    LEAKING_BY = 'user password=hunter22'

    @pytest.fixture
    def stored_by(self, workspace: Workspace) -> str:
        run = workspace.start(depth='deep')
        workspace.add(run, [finding('MV-1', 'High', 'a.py:1')])
        workspace.dispose(run, by=self.LEAKING_BY, decisions={'F1': {'decision': 'fix'}})
        with workspace.reviews.store.transaction() as repository:
            (decided,) = repository.decisions.dispositions(run)
        return decided.by

    def test_a_secret_in_by_is_redacted_in_the_stored_row(self, stored_by: str) -> None:
        assert stored_by == 'user [REDACTED:assignment]'


class TestVerdict:
    @pytest.fixture
    def run(self, workspace: Workspace) -> RunId:
        return workspace.start(depth='deep')

    def test_an_open_critical_gives_block(self, workspace: Workspace, run: RunId) -> None:
        workspace.add(run, [finding('MV-1', 'Critical', 'a.py:1')])
        assert workspace.report(run).verdict == Verdict.BLOCK

    @pytest.mark.parametrize(
        'decisions',
        [
            pytest.param({}, id='undecided'),
            pytest.param({'F1': {'decision': 'defer', 'reason': 'later'}}, id='deferred'),
            pytest.param({'F1': {'decision': 'fix'}}, id='chosen-for-fixing'),
        ],
    )
    def test_an_open_high_not_accepted_as_a_risk_gives_block(
        self, workspace: Workspace, run: RunId, decisions: dict[str, dict[str, str]]
    ) -> None:
        workspace.add(run, [finding('MV-1', 'High', 'a.py:1')])
        workspace.dispose(run, by='user', decisions=decisions)
        assert workspace.report(run).verdict == Verdict.BLOCK

    def test_a_high_accepted_as_a_risk_gives_merge_with_conditions(
        self, workspace: Workspace, run: RunId
    ) -> None:
        workspace.add(run, [finding('MV-1', 'High', 'a.py:1')])
        accepted = {'F1': {'decision': 'accept-risk', 'reason': 'the endpoint is internal'}}
        workspace.dispose(run, by='user', decisions=accepted)
        assert workspace.report(run).verdict == Verdict.CONDITIONS

    def test_only_low_findings_open_gives_clear(self, workspace: Workspace, run: RunId) -> None:
        workspace.add(run, [finding('MV-1', 'Low', 'a.py:1')])
        assert workspace.report(run).verdict == Verdict.CLEAR

    def test_a_dismissed_finding_is_closed(self, workspace: Workspace, run: RunId) -> None:
        workspace.add(run, [finding('MV-1', 'Critical', 'a.py:1')])
        dismissed = {'F1': {'decision': 'dismiss', 'reason': 'not reachable'}}
        workspace.dispose(run, by='user', decisions=dismissed)
        assert workspace.report(run).verdict == Verdict.CLEAR


class TestRuns:
    def test_a_failed_resolution_needs_a_reason(self, workspace: Workspace) -> None:
        run = workspace.start(depth='deep')
        workspace.add(run, [finding('MV-1', 'High', 'a.py:1')])
        workspace.dispose(run, by='user', decisions={'F1': {'decision': 'fix'}})
        refused = workspace.resolve(run, finding='F1', result='failed')
        recorded = workspace.resolve(run, finding='F1', result='failed', reason='tests red')
        assert 'failed needs reason' in refused.err
        assert recorded.out == 'F1 failed\n'

    def test_disposing_an_unknown_finding_is_refused_and_stores_nothing(
        self, workspace: Workspace
    ) -> None:
        run = workspace.start(depth='deep')
        workspace.add(run, [finding('MV-1', 'High', 'a.py:1')])
        decisions = {'F1': {'decision': 'fix'}, 'F9': {'decision': 'fix'}}
        outcome = workspace.dispose(run, by='user', decisions=decisions)
        assert 'F9: no such finding' in outcome.err
        assert workspace.gate(run).out.endswith('\tundecided\n')

    def test_disposing_names_the_findings_still_undecided(self, workspace: Workspace) -> None:
        run = workspace.start(depth='deep')
        workspace.add(run, [finding('MV-1', 'High', 'a.py:1'), finding('MV-2', 'Low', 'b.py:1')])
        outcome = workspace.dispose(run, by='user', decisions={'F1': {'decision': 'fix'}})
        assert outcome.out == '1 dispositions recorded; undecided: F2\n'

    def test_an_unknown_run_is_refused(self, workspace: Workspace) -> None:
        outcome = workspace.gate(RunId('20260101-000000'))
        assert 'no review run 20260101-000000' in outcome.err

    def test_a_second_run_in_the_same_second_is_refused(self, workspace: Workspace) -> None:
        started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        workspace.start(started=started, depth='deep')
        outcome = workspace.try_start({**BALANCED, 'depth': 'deep'}, started)
        assert 'review run 20260101-120000 already exists' in outcome.err

    @pytest.mark.parametrize(
        ('payload', 'needs'),
        [
            pytest.param({'scope': 'ticket', 'base': 'main'}, 'ticket scope needs slug', id='slug'),
            pytest.param({'scope': 'branch'}, 'branch scope needs base', id='branch-base'),
            pytest.param({'scope': 'diff', 'base': '--output=x'}, 'plain revision', id='option'),
        ],
    )
    def test_a_target_the_scope_cannot_review_is_refused(
        self, workspace: Workspace, payload: dict[str, str], needs: str
    ) -> None:
        outcome = workspace.try_start({'depth': 'deep', 'emphasis': 'balanced', **payload})
        assert outcome.code == REJECTED
        assert needs in outcome.err

    def test_the_list_shows_each_run_with_its_verdict(self, workspace: Workspace) -> None:
        first = workspace.start(
            started=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC), depth='quick', persona='uncle-bob'
        )
        second = workspace.start(started=datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC), depth='deep')
        workspace.add(second, [finding('MV-1', 'High', 'a.py:1')])
        listed = workspace.attempt(ReviewService.listing)
        assert listed.out.splitlines() == [
            f'{first}\t{SLUG}\tquick\t0 findings\tCLEAR',
            f'{second}\t{SLUG}\tdeep\t1 findings\tBLOCK',
        ]

    def test_the_list_of_no_runs_says_so(self, workspace: Workspace) -> None:
        assert workspace.attempt(ReviewService.listing).out == 'no review runs\n'
