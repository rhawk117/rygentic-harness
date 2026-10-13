"""Per-test CLI runners for the data analysis commands."""

import pytest
from python_harness.scripts.data_analysis import alert_budget, paired_compare
from python_harness.scripts.tests.support import ScriptRunner


@pytest.fixture
def run_paired(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> ScriptRunner:
    return ScriptRunner(main=paired_compare.main, capture=capsys, logs=caplog)


@pytest.fixture
def run_alert(capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> ScriptRunner:
    return ScriptRunner(main=alert_budget.main, capture=capsys, logs=caplog)
