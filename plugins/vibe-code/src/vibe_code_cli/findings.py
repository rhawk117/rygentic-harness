from dataclasses import dataclass
from itertools import groupby
from operator import attrgetter
from typing import Literal

import msgspec


class CannotCheckError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(slots=True, kw_only=True, frozen=True)
class Finding:
    level: Literal['error', 'warning', 'info']
    message: str


def error(message: str) -> Finding:
    return Finding(level='error', message=message)


def warning(message: str) -> Finding:
    return Finding(level='warning', message=message)


def info(message: str) -> Finding:
    return Finding(level='info', message=message)


def decode_problem(problem: msgspec.ValidationError, *, builtin_errored: bool) -> list[Finding]:
    return [] if builtin_errored else [error(str(problem))]


def report(label: str, findings: list[Finding], *, strict: bool) -> int:
    level_getter = attrgetter('level')
    grouped = {level: list(group) for level, group in groupby(findings, key=level_getter)}

    errors = grouped.get('error', [])
    warnings = grouped.get('warning', [])
    infos = grouped.get('info', [])

    for finding in findings:
        print(f'{finding.level}: {finding.message}')

    failed = bool(errors) or (strict and bool(warnings))
    verdict = 'FAIL' if failed else 'PASS'
    counts = f'{len(errors)} error(s), {len(warnings)} warning(s)'
    if infos:
        counts += f', {len(infos)} info'

    print(f'{verdict} {label}: {counts}')
    return 1 if failed else 0
