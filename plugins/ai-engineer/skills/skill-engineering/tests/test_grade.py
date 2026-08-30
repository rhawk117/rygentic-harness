"""grade.run_mechanical — never previously imported by a test.

Exit 0 is a pass, nonzero is a fail, and a check that cannot finish is a distinct
ERROR outcome (never folded into "fail"), per grade.py's own module docstring.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from skilleng.grade import run_mechanical
from skilleng.schema import Assertion, AssertionKind, Outcome


def _assertion(check: str) -> Assertion:
    return Assertion(id='a1', text='a check', kind=AssertionKind.MECHANICAL, check=check)


class TestRunMechanical:
    def test_exit_zero_is_a_pass(self, tmp_path: Path) -> None:
        result = run_mechanical(_assertion('exit 0'), tmp_path)
        assert result.outcome is Outcome.PASS

    def test_nonzero_exit_is_a_fail(self, tmp_path: Path) -> None:
        result = run_mechanical(_assertion('exit 1'), tmp_path)
        assert result.outcome is Outcome.FAIL
        assert 'exited 1' in result.evidence

    def test_a_check_that_hangs_times_out_as_an_error_not_a_fail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr('skilleng.grade.TIMEOUT', 0.2)
        result = run_mechanical(_assertion('sleep 5'), tmp_path)
        assert result.outcome is Outcome.ERROR
        assert 'timed out' in result.evidence
