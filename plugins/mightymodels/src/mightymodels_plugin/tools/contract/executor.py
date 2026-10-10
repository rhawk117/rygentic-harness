"""The `verify run` executor: one approved command run without a shell, and the receipt of it.

The argv comes only from the ticket's contract, never from the caller. Every run gets a receipt
with the exit code, duration, bounded output tails, a digest of the full output, and the HEAD it
ran at. A run that HEAD moved under cannot pass.
"""

import hashlib
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from mightymodels_plugin.clock import now
from mightymodels_plugin.core.workspace import Git, Workspace
from mightymodels_plugin.tools.contract.schema import ApprovedCommand, Outcome, Phase, Receipt

TAIL_LINES = 40
TAIL_CHARS = 4000
HEAD_MOVED = '\nHEAD changed during verification; rerun at the current HEAD.'

type RunFailure = subprocess.TimeoutExpired | FileNotFoundError


@dataclass(slots=True, kw_only=True, frozen=True)
class Execution:
    outcome: Outcome
    exit: int | None
    stdout: str
    stderr: str


def tail(text: str) -> str:
    return '\n'.join(text.splitlines()[-TAIL_LINES:])[-TAIL_CHARS:]


def failed_execution(failure: RunFailure, command: ApprovedCommand) -> Execution:
    if isinstance(failure, FileNotFoundError):
        return Execution(outcome=Outcome.NOT_FOUND, exit=None, stdout='', stderr=str(failure))
    output = failure.stdout if isinstance(failure.stdout, str) else ''
    return Execution(
        outcome=Outcome.TIMEOUT,
        exit=None,
        stdout=output,
        stderr=f'timed out after {command.timeout}s',
    )


def execute(command: ApprovedCommand, root: Path) -> Execution:
    try:
        completed = subprocess.run(  # noqa: S603 - argv comes only from the user-approved contract, never from the caller
            list(command.argv),
            cwd=root,
            capture_output=True,
            text=True,
            timeout=command.timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as failure:
        return failed_execution(failure, command)
    passed = completed.returncode == command.expect_exit
    return Execution(
        outcome=Outcome.PASSED if passed else Outcome.FAILED,
        exit=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def failed_if_head_moved(execution: Execution, head: str | None, git: Git) -> Execution:
    if git.resolve_head() == head:
        return execution
    return Execution(
        outcome=Outcome.FAILED,
        exit=execution.exit,
        stdout=execution.stdout,
        stderr=execution.stderr + HEAD_MOVED,
    )


def receipt_for(command: ApprovedCommand, workspace: Workspace, phase: Phase) -> Receipt:
    head = workspace.git.resolve_head()
    started = time.monotonic()
    result = failed_if_head_moved(execute(command, workspace.root), head, workspace.git)
    elapsed = int((time.monotonic() - started) * 1000)
    return Receipt(
        id=command.id,
        argv=command.argv,
        outcome=result.outcome,
        exit=result.exit,
        duration_ms=elapsed,
        stdout_tail=tail(result.stdout),
        stderr_tail=tail(result.stderr),
        digest=hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest(),
        head=head,
        phase=phase,
        at=now(),
    )
