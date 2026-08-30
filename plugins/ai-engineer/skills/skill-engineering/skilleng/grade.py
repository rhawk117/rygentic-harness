"""Mechanical assertion execution.

A mechanical assertion is a command run against the outputs directory. Exit 0 is a
pass, nonzero is a fail, and a command that could not be executed at all is an
ERROR — a distinct third outcome, because "the check crashed" is not evidence that
the skill failed.

Judged assertions are graded by the blinded grader agent (agents/grader.md) and
arrive here already decided; this module only ever runs the deterministic half.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .schema import Assertion, AssertionKind, AssertionResult, Outcome

TIMEOUT = 60


def run_mechanical(assertion: Assertion, outputs_dir: Path) -> AssertionResult:
    if assertion.kind is not AssertionKind.MECHANICAL:
        raise ValueError(f"{assertion.id} is {assertion.kind.value}, not mechanical")
    outputs_dir = Path(outputs_dir)
    if not outputs_dir.is_dir():
        return AssertionResult(assertion.id, assertion.text, assertion.kind, Outcome.ERROR,
                               f"outputs dir missing: {outputs_dir}", assertion.weight)
    try:
        proc = subprocess.run(
            ["bash", "-lc", assertion.check or ""], cwd=str(outputs_dir),
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return AssertionResult(assertion.id, assertion.text, assertion.kind, Outcome.ERROR,
                               f"check timed out after {TIMEOUT}s", assertion.weight)
    except OSError as e:
        return AssertionResult(assertion.id, assertion.text, assertion.kind, Outcome.ERROR,
                               f"could not execute check: {e}", assertion.weight)
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
    outcome = Outcome.PASS if proc.returncode == 0 else Outcome.FAIL
    evidence = f"`{assertion.check}` exited {proc.returncode}" + (f"\n{tail}" if tail else "")
    return AssertionResult(assertion.id, assertion.text, assertion.kind, outcome, evidence, assertion.weight)


def grade_case(assertions: list[Assertion], outputs_dir: Path,
               judged: dict[str, AssertionResult] | None = None) -> list[AssertionResult]:
    """Combine mechanical execution with any judged results supplied by the grader."""
    judged = judged or {}
    out: list[AssertionResult] = []
    for a in assertions:
        if a.kind is AssertionKind.MECHANICAL:
            out.append(run_mechanical(a, outputs_dir))
        elif a.id in judged:
            out.append(judged[a.id])
        else:
            out.append(AssertionResult(a.id, a.text, a.kind, Outcome.ERROR,
                                       "no grader verdict supplied", a.weight))
    return out
