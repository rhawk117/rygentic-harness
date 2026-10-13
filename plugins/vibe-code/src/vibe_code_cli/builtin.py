import itertools
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import msgspec

from vibe_code_cli.findings import CannotCheckError, Finding, error, warning


class BuiltinUnavailableError(CannotCheckError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class ReportItem(msgspec.Struct, frozen=True, kw_only=True):
    message: str
    path: str | None = None


class ReportSection(msgspec.Struct, frozen=True, kw_only=True):
    errors: list[ReportItem] = msgspec.field(default_factory=list)
    warnings: list[ReportItem] = msgspec.field(default_factory=list)


class Report(msgspec.Struct, frozen=True, kw_only=True):
    manifest: ReportSection | None = None
    contents: list[ReportSection] = msgspec.field(default_factory=list)


def run_builtin(target: Path, *, include_manifest: bool = True) -> list[Finding]:
    claude = shutil.which('claude')
    if claude is None:
        message = 'claude is not on PATH: npm install -g @anthropic-ai/claude-code'
        raise BuiltinUnavailableError(message)

    result = subprocess.run(  # noqa: S603  fixed argument list with no shell; target is a path.
        [claude, 'plugin', 'validate', shlex.quote(str(target)), '--json'],
        capture_output=True,
        text=True,
        check=False,
    )
    findings = parse_report(result.stdout, include_manifest=include_manifest)
    if result.returncode != 0 and not any(finding.level == 'error' for finding in findings):
        message = f'claude plugin validate exited {result.returncode} with no error finding: '
        raise BuiltinUnavailableError(message + result.stderr.strip())
    return findings


@runtime_checkable
class BuiltinRunner(Protocol):
    def __call__(
        self,
        target: Path,
        /,
        *,
        include_manifest: bool = True,
    ) -> list[Finding]: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class Services:
    run_builtin: BuiltinRunner = run_builtin


def parse_report(stdout: str, *, include_manifest: bool = True) -> list[Finding]:
    try:
        report = msgspec.json.decode(stdout, type=Report)
    except msgspec.DecodeError as problem:
        message = f'claude plugin validate printed no JSON report: {problem}'
        raise BuiltinUnavailableError(message) from problem
    manifest = [report.manifest] if include_manifest and report.manifest is not None else []

    return [
        finding
        for section in itertools.chain(manifest, report.contents)
        for finding in section_findings(section)
    ]


def section_findings(section: ReportSection) -> list[Finding]:
    return [
        *(error(finding_text(item)) for item in section.errors),
        *(warning(finding_text(item)) for item in section.warnings),
    ]


def finding_text(item: ReportItem) -> str:
    if item.path:
        return f'{item.path}: {item.message}'

    return item.message
