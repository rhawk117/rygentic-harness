"""Every data analysis command speaks the same envelope and exit-code vocabulary."""

from pathlib import Path

import polars as pl
import pytest
from python_harness.scripts.tests.support import ENVELOPE_KEYS, ScriptRunner

SCHEMA_VERSION = 2
UNREADABLE_INPUT = 3
ALERT_ARGUMENTS = (
    '--events',
    '100',
    '--prevalence',
    '0.1',
    '--recall',
    '0.5',
    '--fpr',
    '0.1',
)


@pytest.fixture
def results_csv(tmp_path: Path) -> Path:
    path = tmp_path.joinpath('results.csv')
    pl.DataFrame({'task': ['a', 'b'], 'old': [0, 1], 'new': [1, 1]}).write_csv(path)
    return path


class TestEnvelope:
    def test_paired_compare_uses_the_shared_envelope(
        self, run_paired: ScriptRunner, results_csv: Path
    ) -> None:
        report = run_paired(str(results_csv), '--old', 'old', '--new', 'new', '--key', 'task')
        assert tuple(report.document) == ENVELOPE_KEYS
        assert report.document['schema_version'] == SCHEMA_VERSION
        assert report.document['arguments']['key'] == 'task'

    def test_alert_budget_uses_the_shared_envelope(self, run_alert: ScriptRunner) -> None:
        report = run_alert(*ALERT_ARGUMENTS)
        assert tuple(report.document) == ENVELOPE_KEYS
        assert report.document['arguments']['fpr'] == pytest.approx(0.1)


class TestExitCodes:
    def test_missing_file_is_unreadable_not_a_contract_violation(
        self, run_paired: ScriptRunner, tmp_path: Path
    ) -> None:
        missing = tmp_path.joinpath('absent.csv')
        result = run_paired(str(missing), '--old', 'old', '--new', 'new')
        assert (result.exit_code, result.stdout) == (UNREADABLE_INPUT, '')
        assert 'Traceback' not in result.stderr

    def test_unsupported_suffix_is_unreadable(
        self, run_paired: ScriptRunner, tmp_path: Path
    ) -> None:
        result = run_paired(str(tmp_path.joinpath('results.txt')), '--old', 'a', '--new', 'b')
        assert result.exit_code == UNREADABLE_INPUT
