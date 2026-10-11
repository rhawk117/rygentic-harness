import pytest
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.tools.review.schema import Disposition, Evidence, FindingInput
from mightymodels_plugin.tools.review.tests.workspace import Workspace, finding


def decided_ids(workspace: Workspace, run: RunId) -> list[str]:
    with workspace.reviews.store.transaction() as repository:
        return sorted(decided.finding_id for decided in repository.decisions.dispositions(run))


def resolved_ids(workspace: Workspace, run: RunId) -> list[str]:
    with workspace.reviews.store.transaction() as repository:
        return sorted(resolved.finding_id for resolved in repository.decisions.outcomes(run))


def gate_decisions(workspace: Workspace, run: RunId) -> dict[str, str]:
    columns = [line.split('\t') for line in workspace.gate(run).out.splitlines()]
    return {line[0]: line[-1] for line in columns if line[0]}


class TestReopenOnMerge:
    RECORDED = (finding('MV-2', 'Medium', 'src/q.py:10-20'), finding('MV-3', 'Low', 'src/r.py:1'))
    RAISED = finding('UB-4', 'High', 'src/q.py:15')
    UNSEEN = finding('UB-9', 'Low', 'src/s.py:7')
    DISMISSED = Disposition.model_validate({'decision': 'dismiss', 'reason': 'not reachable'})
    METRIC = Evidence.model_validate(
        {'kind': 'metric', 'cite': 'uncle-bob-metrics.json functions_over_20_loc'}
    )

    @pytest.fixture
    def run(self, workspace: Workspace) -> RunId:
        run = workspace.start(depth='deep')
        workspace.add(run, [*self.RECORDED])
        return run

    @pytest.fixture
    def dismissed(self, workspace: Workspace, run: RunId) -> None:
        decisions = {'F1': self.DISMISSED, 'F2': self.DISMISSED}
        workspace.dispose(run, by='user', decisions=decisions)

    @pytest.fixture
    def fixed(self, workspace: Workspace, run: RunId) -> None:
        workspace.dispose(run, by='user', decisions={'F1': {'decision': 'fix'}})
        resolved = workspace.resolve(run, finding='F1', result='fixed', commit='abc123')
        assert resolved.out == 'F1 fixed\n'

    @pytest.mark.usefixtures('dismissed')
    def test_a_dismissed_finding_a_later_merge_raises_in_severity_reads_undecided_at_the_gate(
        self, workspace: Workspace, run: RunId
    ) -> None:
        workspace.add(run, [self.RAISED])
        assert gate_decisions(workspace, run) == {'F1': 'undecided', 'F2': 'dismiss'}
        assert decided_ids(workspace, run) == ['F2']

    @pytest.mark.usefixtures('fixed')
    def test_a_fixed_finding_a_merge_changes_loses_its_decision_and_its_outcome(
        self, workspace: Workspace, run: RunId
    ) -> None:
        workspace.add(run, [self.RAISED])
        refused = workspace.resolve(run, finding='F1', result='fixed', commit='abc123')
        assert decided_ids(workspace, run) == []
        assert resolved_ids(workspace, run) == []
        assert refused.err == 'F1: only a finding the user chose to fix is resolved'

    @pytest.mark.usefixtures('dismissed')
    @pytest.mark.parametrize(
        'incoming',
        [
            pytest.param(finding('UB-4', 'Medium', 'src/q.py:12'), id='a-new-source'),
            pytest.param(finding('UB-4', 'Critical', 'src/q.py:12'), id='a-conflict'),
            pytest.param(
                finding('MV-2', 'Medium', 'src/q.py:10-20', security=True), id='the-security-flag'
            ),
            pytest.param(
                finding('MV-2', 'Medium', 'src/q.py:10-20', evidence=METRIC),
                id='evidence-filled-in',
            ),
        ],
    )
    def test_a_merge_that_changes_any_field_of_a_decided_finding_reopens_it(
        self, workspace: Workspace, run: RunId, incoming: FindingInput
    ) -> None:
        outcome = workspace.add(run, [incoming])
        assert outcome.out == '1 findings in, 1 recorded: F1; back to undecided: F1\n'
        assert decided_ids(workspace, run) == ['F2']

    @pytest.mark.usefixtures('dismissed')
    def test_adding_the_same_batch_again_keeps_the_decisions(
        self, workspace: Workspace, run: RunId
    ) -> None:
        outcome = workspace.add(run, [*self.RECORDED])
        assert outcome.out == '2 findings in, 2 recorded: F1, F2\n'
        assert gate_decisions(workspace, run) == {'F1': 'dismiss', 'F2': 'dismiss'}
        assert decided_ids(workspace, run) == ['F1', 'F2']

    def test_a_merge_into_an_undecided_finding_leaves_the_text_as_it_was(
        self, workspace: Workspace, run: RunId
    ) -> None:
        assert workspace.add(run, [self.RAISED]).out == '1 findings in, 1 recorded: F1\n'

    @pytest.mark.usefixtures('dismissed')
    def test_add_names_only_the_decided_findings_the_batch_changed(
        self, workspace: Workspace, run: RunId
    ) -> None:
        outcome = workspace.add(run, [self.UNSEEN, self.RECORDED[1], self.RAISED])
        assert outcome.out == '3 findings in, 3 recorded: F1, F2, F3; back to undecided: F1\n'


class TestTheReopenedFindingsInTheText:
    NUMBERS = range(1, 11)
    RECORDED = tuple(finding(f'MV-{number}', 'Low', f'src/m{number}.py:1') for number in NUMBERS)
    TENTH_THEN_SECOND = (
        finding('UB-1', 'High', 'src/m10.py:1'),
        finding('UB-2', 'High', 'src/m2.py:1'),
    )
    DISMISSED = Disposition.model_validate({'decision': 'dismiss', 'reason': 'not reachable'})

    @pytest.fixture
    def ten_dismissed(self, workspace: Workspace) -> RunId:
        run = workspace.start(depth='deep')
        workspace.add(run, [*self.RECORDED])
        decisions = {f'F{number}': self.DISMISSED for number in self.NUMBERS}
        workspace.dispose(run, by='user', decisions=decisions)
        return run

    def test_add_names_the_reopened_findings_in_number_order(
        self, workspace: Workspace, ten_dismissed: RunId
    ) -> None:
        outcome = workspace.add(ten_dismissed, [*self.TENTH_THEN_SECOND])
        assert outcome.out == '2 findings in, 2 recorded: F2, F10; back to undecided: F2, F10\n'
