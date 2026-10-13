"""Child processes: the one place the plugin launches them, and what a launch comes back as.

`ProcessRunner.run` runs an argument vector without a shell and waits at most `timeout` seconds,
which every caller has to name. It returns a `CompletedRun`, or a `FailedRun` whose `kind` says
which of four things happened: the wait ran out, the executable is missing, the system refused
the launch, or the output is not text in the default encoding. None of the four leaves `run` as
an exception, and `detail` carries the cause in words. A program, an argument or a working
directory that holds a NUL is a refused launch too.

A finished run is decoded as `text=True` decodes it. What a timed-out run printed before it was
killed is decoded with the same encoding and the same newline handling, except that bytes which
are not text are replaced: the kill can cut a character in half, and a timeout stays a timeout.
"""

import io
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path
from typing import Protocol, runtime_checkable


class FailureKind(StrEnum):
    TIMED_OUT = auto()
    NOT_FOUND = auto()
    REFUSED = auto()
    UNDECODABLE = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class CompletedRun:
    exit: int
    stdout: str
    stderr: str


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedRun:
    kind: FailureKind
    detail: str
    stdout: str
    stderr: str


type RunOutcome = CompletedRun | FailedRun
type LaunchError = subprocess.TimeoutExpired | OSError | ValueError
type Captured = bytes | str | None


@runtime_checkable
class ProcessRunner(Protocol):
    def run(
        self, argv: Sequence[str], *, timeout: float, cwd: Path | None = None
    ) -> RunOutcome: ...


def captured_text(captured: Captured) -> str:
    if captured is None:
        return ''
    if isinstance(captured, str):
        return captured
    return io.TextIOWrapper(io.BytesIO(captured), errors='replace').read()


def failed_run(error: LaunchError) -> FailedRun:
    if isinstance(error, subprocess.TimeoutExpired):
        return FailedRun(
            kind=FailureKind.TIMED_OUT,
            detail=f'timed out after {error.timeout}s',
            stdout=captured_text(error.stdout),
            stderr=captured_text(error.stderr),
        )
    if isinstance(error, UnicodeDecodeError):
        return FailedRun(kind=FailureKind.UNDECODABLE, detail=str(error), stdout='', stderr='')
    missing = isinstance(error, FileNotFoundError)
    kind = FailureKind.NOT_FOUND if missing else FailureKind.REFUSED
    return FailedRun(kind=kind, detail=str(error), stdout='', stderr='')


@dataclass(slots=True, kw_only=True, frozen=True)
class SubprocessRunner:
    def run(self, argv: Sequence[str], *, timeout: float, cwd: Path | None = None) -> RunOutcome:
        try:
            completed = subprocess.run(  # noqa: S603 - no shell and every word is one argument; a caller passes an approved contract argv or fixed words with checked values
                list(argv),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError, ValueError) as error:
            return failed_run(error)
        return CompletedRun(
            exit=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )


def process_runner() -> ProcessRunner:
    return SubprocessRunner()
