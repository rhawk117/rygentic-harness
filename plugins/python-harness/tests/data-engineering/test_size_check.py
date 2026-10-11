"""Size arithmetic checked against hand-computed byte and row counts."""

import pytest
from python_harness.scripts.data_engineering.size_check import readable_bytes
from python_harness.scripts.tests.support import ScriptRunner

CONTRACT_VIOLATION = 2
THOUSAND_SQUARED = 1_000 * 1_000

BYTE_CASES = (
    pytest.param(
        ('pairwise', '--n', '1000000', '--dtype', 'float32'),
        4 * 10**12,
        id='pairwise-4tb',
    ),
    pytest.param(('dense', '--rows', '1000000', '--cols', '100'), 800 * 10**6, id='dense-float64'),
    pytest.param(
        ('embeddings', '--n', '1000000', '--dim', '768', '--dtype', 'float32'),
        3_072_000_000,
        id='embeddings-768',
    ),
    pytest.param(
        ('sparse', '--rows', '1000000', '--cols', '100000', '--nnz', '50000000'),
        50_000_000 * (8 + 4) + 1_000_001 * 4,
        id='csr-int32-indices',
    ),
)

READABLE_CASES = (
    pytest.param(0, '0 B', id='zero'),
    pytest.param(999, '999 B', id='below-kilo'),
    pytest.param(1_000, '1 kB', id='kilo-boundary'),
    pytest.param(4 * 10**12, '4 TB', id='terabytes'),
)


class TestByteEstimates:
    @pytest.mark.parametrize(('arguments', 'expected_bytes'), BYTE_CASES)
    def test_bytes_match_hand_arithmetic(
        self, run_size: ScriptRunner, arguments: tuple[str, ...], expected_bytes: int
    ) -> None:
        assert run_size(*arguments).result['bytes'] == expected_bytes

    @pytest.mark.parametrize(('size', 'expected'), READABLE_CASES)
    def test_readable_uses_decimal_units(self, size: int, expected: str) -> None:
        assert readable_bytes(size) == expected


class TestCounts:
    def test_join_output_is_product_of_matches(self, run_size: ScriptRunner) -> None:
        result = run_size('join', '--left-matches', '1000', '--right-matches', '1000').result
        assert result['elements'] == THOUSAND_SQUARED

    def test_fit_budget_in_serial_hours(self, run_size: ScriptRunner) -> None:
        result = run_size(
            'fits', '--configs', '50', '--folds', '5', '--seconds-per-fit', '360'
        ).result
        assert (result['elements'], result['serial_hours']) == (
            250,
            pytest.approx(25.0),
        )


class TestRejections:
    rejected = (
        pytest.param(('dense', '--rows', '-1', '--cols', '2'), 'nonnegative', id='negative'),
        pytest.param(
            ('dense', '--rows', '1', '--cols', '2', '--dtype', 'nope'),
            'nope',
            id='bad-dtype',
        ),
    )

    @pytest.mark.parametrize(('arguments', 'message'), rejected)
    def test_rejects_without_output(
        self, run_size: ScriptRunner, arguments: tuple[str, ...], message: str
    ) -> None:
        result = run_size(*arguments)
        assert (result.exit_code, result.stdout) == (CONTRACT_VIOLATION, '')
        assert message in result.stderr
