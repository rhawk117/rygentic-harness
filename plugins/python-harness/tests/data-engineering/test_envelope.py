"""Every data engineering command speaks the same envelope and exit-code vocabulary."""

from pathlib import Path

import polars as pl
import pytest
from python_harness.scripts.tests.support import ENVELOPE_KEYS, ScriptRunner

SCHEMA_VERSION = 2
UNREADABLE_INPUT = 3


@pytest.fixture
def keyed_parquet(tmp_path: Path) -> Path:
    path = tmp_path.joinpath('keyed.parquet')
    pl.DataFrame({'asset_id': ['a', 'b'], 'owner': ['x', 'y']}).write_parquet(path)
    return path


class TestEnvelope:
    size_commands = (
        pytest.param(('dense', '--rows', '2', '--cols', '3'), id='dense'),
        pytest.param(('join', '--left-matches', '2', '--right-matches', '3'), id='join'),
        pytest.param(('fits', '--configs', '2', '--folds', '3'), id='fits'),
    )

    @pytest.mark.parametrize('arguments', size_commands)
    def test_size_check_uses_the_shared_envelope(
        self, run_size: ScriptRunner, arguments: tuple[str, ...]
    ) -> None:
        report = run_size(*arguments)
        assert tuple(report.document) == ENVELOPE_KEYS
        assert report.document['command'] == f'size_check {arguments[0]}'
        assert report.document['schema_version'] == SCHEMA_VERSION

    def test_profile_uses_the_shared_envelope(
        self, run_profile: ScriptRunner, keyed_parquet: Path
    ) -> None:
        report = run_profile('profile', str(keyed_parquet), '--key', 'asset_id')
        assert tuple(report.document) == ENVELOPE_KEYS
        assert report.document['arguments']['key'] == ['asset_id']

    def test_join_uses_the_same_key_flag_as_profile(
        self, run_profile: ScriptRunner, keyed_parquet: Path
    ) -> None:
        report = run_profile('join', str(keyed_parquet), str(keyed_parquet), '--key', 'asset_id')
        assert tuple(report.document) == ENVELOPE_KEYS
        assert report.result['keys'] == ['asset_id']
        assert report.caveats == []


class TestExitCodes:
    def test_missing_file_is_unreadable_without_traceback(
        self, run_profile: ScriptRunner, tmp_path: Path
    ) -> None:
        result = run_profile('profile', str(tmp_path.joinpath('absent.parquet')))
        assert (result.exit_code, result.stdout) == (UNREADABLE_INPUT, '')
        assert 'Traceback' not in result.stderr
