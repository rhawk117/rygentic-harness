"""Behavior of alert_budget against hand-computed load and cost figures."""

import pytest
from python_harness.scripts.tests.support import CliResult, ScriptRunner

CONTRACT_VIOLATION = 2
RARE_DETECTOR = ('--events', '1000000', '--prevalence', '0.001', '--recall', '0.9')


@pytest.fixture
def rare_event_load(run_alert: ScriptRunner) -> CliResult:
    return run_alert(
        *RARE_DETECTOR,
        '--fpr',
        '0.01',
        '--budget',
        '50',
        '--cost-fn',
        '500',
        '--cost-fp',
        '5',
    )


class TestRareEventDetector:
    def test_false_alerts_dominate(self, rare_event_load: CliResult) -> None:
        expected = rare_event_load.result['expected']
        assert expected['true_alerts'] == pytest.approx(900)
        assert expected['false_alerts'] == pytest.approx(9_990)
        assert rare_event_load.result['precision'] == pytest.approx(900 / 10_890)

    def test_always_negative_accuracy_exposes_the_trap(self, rare_event_load: CliResult) -> None:
        assert rare_event_load.result['accuracy_of_always_negative'] == pytest.approx(0.999)

    def test_budget_overflow_is_reported(self, rare_event_load: CliResult) -> None:
        budget = rare_event_load.result['budget']
        assert budget['fits'] is False
        assert budget['alerts_over_budget'] == pytest.approx(10_840)

    def test_cost_weights_misses_and_false_alerts(self, rare_event_load: CliResult) -> None:
        cost = rare_event_load.result['cost']
        assert cost['total'] == pytest.approx(500 * 100 + 5 * 9_990)
        assert cost['per_event'] == pytest.approx(99_950 / 1_000_000)


class TestUndefinedAndRejected:
    def test_no_alerts_leaves_precision_undefined(self, run_alert: ScriptRunner) -> None:
        report = run_alert('--events', '100', '--prevalence', '0', '--recall', '0.9', '--fpr', '0')
        assert report.result['precision'] is None
        assert 'budget' not in report.result
        assert any('undefined' in caveat for caveat in report.caveats)

    def test_rejects_zero_events(self, run_alert: ScriptRunner) -> None:
        result = run_alert(*RARE_DETECTOR[2:], '--events', '0', '--fpr', '0.1')
        assert result.exit_code == CONTRACT_VIOLATION

    invalid_requests = (
        pytest.param(
            ('--prevalence', '1.2', '--recall', '0.5', '--fpr', '0.1'),
            'prevalence',
            id='prevalence-above-one',
        ),
        pytest.param(
            ('--prevalence', '0.1', '--recall', '0.5', '--fpr', 'nan'),
            'false_positive_rate',
            id='nonfinite-rate',
        ),
        pytest.param(
            ('--prevalence', '0.1', '--recall', '0.5', '--fpr', '0.1', '--cost-fn', '3'),
            'both',
            id='one-cost-only',
        ),
    )

    @pytest.mark.parametrize(('arguments', 'message'), invalid_requests)
    def test_rejects_with_message_and_no_output(
        self, run_alert: ScriptRunner, arguments: tuple[str, ...], message: str
    ) -> None:
        result = run_alert('--events', '10', *arguments)
        assert (result.exit_code, result.stdout) == (CONTRACT_VIOLATION, '')
        assert message in result.stderr
