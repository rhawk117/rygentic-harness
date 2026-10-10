"""The `verify run` executor: one approved command run without a shell, and the receipt of it.

The argv comes only from the ticket's contract, never from the caller. Every run gets a receipt
with the exit code, duration, bounded output tails, a digest of the full output, and the HEAD it
ran at. A run that HEAD moved under cannot pass.

The process runner is handed in. A command that cannot be launched, outlives its timeout or prints
what is not text still gets a receipt: no exit code, whatever it printed before a timeout, and the
cause as the last line of stderr.
"""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from mightymodels_plugin.clock import now
from mightymodels_plugin.core.process import FailedRun, FailureKind, ProcessRunner
from mightymodels_plugin.core.workspace import Git, Workspace
from mightymodels_plugin.tools.contract.schema import ApprovedCommand, Outcome, Phase, Receipt

TAIL_LINES = 40
TAIL_CHARS = 4000
HEAD_MOVED = '\nHEAD changed during verification; rerun at the current HEAD.'


@dataclass(slots=True, kw_only=True, frozen=True)
class Execution:
    outcome: Outcome
    exit: int | None
    stdout: str
    stderr: str


def tail(text: str) -> str:
    return '\n'.join(text.splitlines()[-TAIL_LINES:])[-TAIL_CHARS:]


def failure_outcome(kind: FailureKind) -> Outcome:
    if kind is FailureKind.TIMED_OUT:
        return Outcome.TIMEOUT
    if kind is FailureKind.NOT_FOUND:
        return Outcome.NOT_FOUND
    return Outcome.FAILED


def with_cause(captured: str, cause: str) -> str:
    separator = '' if not captured or captured.endswith('\n') else '\n'
    return f'{captured}{separator}{cause}'


def failed_execution(failure: FailedRun) -> Execution:
    return Execution(
        outcome=failure_outcome(failure.kind),
        exit=None,
        stdout=failure.stdout,
        stderr=with_cause(failure.stderr, failure.detail),
    )


def execute(command: ApprovedCommand, root: Path, *, processes: ProcessRunner) -> Execution:
    run = processes.run(command.argv, timeout=command.timeout, cwd=root)
    if isinstance(run, FailedRun):
        return failed_execution(run)
    passed = run.exit == command.expect_exit
    return Execution(
        outcome=Outcome.PASSED if passed else Outcome.FAILED,
        exit=run.exit,
        stdout=run.stdout,
        stderr=run.stderr,
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


def receipt_for(
    command: ApprovedCommand, workspace: Workspace, phase: Phase, *, processes: ProcessRunner
) -> Receipt:
    head = workspace.git.resolve_head()
    started = time.monotonic()
    execution = execute(command, workspace.root, processes=processes)
    result = failed_if_head_moved(execution, head, workspace.git)
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
