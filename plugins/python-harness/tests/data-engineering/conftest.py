"""Per-test CLI runners for the data engineering commands."""

import pytest
from python_harness.scripts.data_engineering import profile_data, size_check
from python_harness.scripts.tests.support import ScriptRunner


@pytest.fixture
def run_size(capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> ScriptRunner:
    return ScriptRunner(main=size_check.main, capture=capsys, logs=caplog)


@pytest.fixture
def run_profile(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> ScriptRunner:
    return ScriptRunner(main=profile_data.main, capture=capsys, logs=caplog)
