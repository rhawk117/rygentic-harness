"""Behavior of paired_compare against hand-checked outcomes and broken inputs."""

from dataclasses import dataclass
from pathlib import Path

import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st
from python_harness.scripts.data_analysis.paired_compare import wilson_interval
from python_harness.scripts.tests.support import CliResult, ScriptRunner

OLD = [1, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]
NEW = [1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1]
CONTRACT_VIOLATION = 2


@pytest.fixture
def results_csv(tmp_path: Path) -> Path:
    path = tmp_path.joinpath('results.csv')
    tasks = [f't{index}' for index in range(len(OLD))]
    pl.DataFrame({'task_id': tasks, 'old_pass': OLD, 'new_pass': NEW}).write_csv(path)
    return path


@pytest.fixture
def source_example(run_paired: ScriptRunner, results_csv: Path) -> CliResult:
    return run_paired(
        str(results_csv), '--old', 'old_pass', '--new', 'new_pass', '--key', 'task_id'
    )


@st.composite
def success_counts(draw: st.DrawFn) -> tuple[int, int]:
    trials = draw(st.integers(1, 5_000))
    return draw(st.integers(0, trials)), trials


class TestSourceDocumentExample:
    def test_reports_rates_and_paired_difference(self, source_example: CliResult) -> None:
        result = source_example.result
        assert source_example.exit_code == 0
        assert result['n_tasks'] == len(OLD)
        assert result['old']['rate'] == pytest.approx(0.5)
        assert result['new']['rate'] == pytest.approx(0.75)
        assert result['difference']['value'] == pytest.approx(0.25)

    def test_counts_discordant_pairs_and_exact_test(self, source_example: CliResult) -> None:
        result = source_example.result
        assert result['discordant'] == {'new_only': 4, 'old_only': 1}
        assert result['exact_mcnemar_p'] == pytest.approx(0.375)

    def test_bootstrap_interval_matches_reference(self, source_example: CliResult) -> None:
        interval = source_example.result['difference']['interval']
        assert interval['lower'] == pytest.approx(-1 / 12, abs=0.02)
        assert interval['upper'] == pytest.approx(7 / 12, abs=0.02)

    def test_caveats_name_small_sample_and_zero_in_interval(
        self, source_example: CliResult
    ) -> None:
        caveats = ' '.join(source_example.caveats)
        assert '12 paired tasks' in caveats
        assert 'includes zero' in caveats


@dataclass(frozen=True, slots=True, kw_only=True)
class BrokenTable:
    path: Path
    message: str


BROKEN_TABLES = (
    pytest.param(({'old_pass': [0, 2], 'new_pass': [1, 1]}, '0/1'), id='non-binary'),
    pytest.param(({'old_pass': [0, None], 'new_pass': [1, 1]}, 'null'), id='null-outcome'),
    pytest.param(({'old_pass': [0], 'other': [1]}, 'new_pass'), id='missing-column'),
)


@pytest.fixture(params=BROKEN_TABLES)
def broken_table(request: pytest.FixtureRequest, tmp_path: Path) -> BrokenTable:
    columns, message = request.param
    path = tmp_path.joinpath('broken.csv')
    pl.DataFrame(columns).write_csv(path)
    return BrokenTable(path=path, message=message)


class TestRejectedInputs:
    def test_contract_violation_exits_without_output(
        self, run_paired: ScriptRunner, broken_table: BrokenTable
    ) -> None:
        result = run_paired(str(broken_table.path), '--old', 'old_pass', '--new', 'new_pass')
        assert (result.exit_code, result.stdout) == (CONTRACT_VIOLATION, '')
        assert broken_table.message in result.stderr

    def test_repeated_task_ids_are_ambiguous(
        self, run_paired: ScriptRunner, tmp_path: Path
    ) -> None:
        path = tmp_path.joinpath('repeated.csv')
        pl.DataFrame({'id': ['a', 'a'], 'o': [0, 1], 'n': [1, 1]}).write_csv(path)
        result = run_paired(str(path), '--old', 'o', '--new', 'n', '--key', 'id')
        assert result.exit_code == CONTRACT_VIOLATION
        assert 'ambiguous' in result.stderr

    def test_level_outside_unit_interval(self, run_paired: ScriptRunner, results_csv: Path) -> None:
        result = run_paired(
            str(results_csv), '--old', 'old_pass', '--new', 'new_pass', '--level', '1.5'
        )
        assert result.exit_code == CONTRACT_VIOLATION

    @pytest.mark.parametrize('resamples', ['0', '-1'])
    def test_resamples_must_be_positive(
        self, run_paired: ScriptRunner, results_csv: Path, resamples: str
    ) -> None:
        result = run_paired(
            str(results_csv), '--old', 'old_pass', '--new', 'new_pass', '--resamples', resamples
        )
        assert (result.exit_code, result.stdout) == (CONTRACT_VIOLATION, '')
        assert f'resamples must be positive, got {resamples}' in result.stderr


class TestWilsonInterval:
    def test_zero_successes_keeps_upper_uncertainty(self) -> None:
        interval = wilson_interval(0, 10, 0.95)
        assert interval.lower == pytest.approx(0.0, abs=1e-15)
        assert interval.upper == pytest.approx(0.2775328, abs=1e-7)

    @given(success_counts())
    def test_bounds_contain_rate_inside_unit_interval(self, counts: tuple[int, int]) -> None:
        successes, trials = counts
        interval = wilson_interval(successes, trials, 0.95)
        assert 0.0 <= interval.lower <= successes / trials <= interval.upper <= 1.0


class TestNoDiscordantPairs:
    def test_exact_test_is_uninformative(self, run_paired: ScriptRunner, tmp_path: Path) -> None:
        path = tmp_path.joinpath('ties.csv')
        pl.DataFrame({'o': [1, 0, 1], 'n': [1, 0, 1]}).write_csv(path)
        report = run_paired(str(path), '--old', 'o', '--new', 'n')
        assert report.result['exact_mcnemar_p'] == pytest.approx(1.0)
        assert any('uninformative' in caveat for caveat in report.caveats)
