"""Join and key profiling checked against a hand-counted fixture with planted defects."""

from pathlib import Path

import polars as pl
import pytest
from python_harness.scripts.tests.support import CliResult, ScriptRunner

CONTRACT_VIOLATION = 2
UNREADABLE_INPUT = 3


@pytest.fixture
def findings_csv(tmp_path: Path) -> Path:
    path = tmp_path.joinpath('findings.csv')
    pl.DataFrame(
        {
            'finding_id': [1, 2, 3, 4, 5, 6],
            'asset_id': ['a', 'a', 'b', 'c', 'd', None],
            'cve': ['CVE-1', 'CVE-1', 'CVE-2', 'CVE-3', 'CVE-4', 'CVE-5'],
        }
    ).write_csv(path)
    return path


@pytest.fixture
def assets_parquet(tmp_path: Path) -> Path:
    path = tmp_path.joinpath('assets.parquet')
    pl.DataFrame(
        {
            'asset_id': ['a', 'b', 'b', 'c'],
            'owner': ['payments', 'sre', 'platform', 'internal'],
        }
    ).write_parquet(path)
    return path


@pytest.fixture
def join_profile(run_profile: ScriptRunner, findings_csv: Path, assets_parquet: Path) -> CliResult:
    return run_profile('join', str(findings_csv), str(assets_parquet), '--key', 'asset_id')


class TestJoinProfile:
    def test_output_rows_match_hand_count(self, join_profile: CliResult) -> None:
        result = join_profile.result
        assert result['inner_join_rows'] == 2 * 1 + 1 * 2 + 1 * 1
        assert result['left_join_rows'] == 5 + 1 + 1

    def test_reports_duplicates_on_both_sides(self, join_profile: CliResult) -> None:
        result = join_profile.result
        assert result['observed_cardinality'] == 'm:m'
        assert result['right']['duplicate_keys'] == 1

    def test_reports_unmatched_and_null_keys(self, join_profile: CliResult) -> None:
        left = join_profile.result['left']
        assert (
            left['unmatched_keys'],
            left['unmatched_rows'],
            left['null_key_rows'],
        ) == (1, 1, 1)

    def test_caveats_warn_that_left_join_multiplies(self, join_profile: CliResult) -> None:
        assert any('multiplies' in caveat for caveat in join_profile.caveats)


class TestKeyProfile:
    def test_names_the_duplicated_key(
        self, run_profile: ScriptRunner, assets_parquet: Path
    ) -> None:
        key = run_profile('profile', str(assets_parquet), '--key', 'asset_id').result['key']
        assert (key['unique'], key['duplicate_keys'], key['rows_in_duplicate_keys']) == (
            False,
            1,
            2,
        )
        assert key['duplicate_examples'] == ['b (2 rows)']

    def test_counts_nulls_per_column(self, run_profile: ScriptRunner, findings_csv: Path) -> None:
        columns = run_profile('profile', str(findings_csv)).result['columns']
        nulls = {column['name']: column['nulls'] for column in columns}
        assert nulls == {'finding_id': 0, 'asset_id': 1, 'cve': 0}


class TestRejections:
    def test_unknown_key_column(self, run_profile: ScriptRunner, findings_csv: Path) -> None:
        result = run_profile('profile', str(findings_csv), '--key', 'owner')
        assert (result.exit_code, result.stdout) == (CONTRACT_VIOLATION, '')
        assert 'owner' in result.stderr

    def test_unsupported_suffix(self, run_profile: ScriptRunner, tmp_path: Path) -> None:
        result = run_profile('profile', str(tmp_path.joinpath('data.txt')))
        assert result.exit_code == UNREADABLE_INPUT
