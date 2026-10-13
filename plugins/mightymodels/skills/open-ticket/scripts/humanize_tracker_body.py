"""Check a tracker body against the tracker-body asset and fix its mechanical tells.

check reports every problem with its line; fix applies only the mechanical repairs (dashes
and filler openers) in place, reports each one, and then reports what still needs a human
or model rewrite. Code blocks and inline code are never inspected or changed. The comment
shape (a PR comment) drops the tracker body's section and citation rules.

Usage:
    python3 humanize_tracker_body.py check BODY.md [--shape tracker|comment]
    python3 humanize_tracker_body.py fix BODY.md [--shape tracker|comment]
"""

from __future__ import annotations

import argparse
import operator
import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

EXIT_ISSUES = 1
EXIT_REJECTED = 2
REQUIRED_SECTIONS = ('Summary', 'Findings', 'Acceptance')
SECTION_ORDER = (
    'Summary',
    'Findings',
    'Open questions',
    'Acceptance',
    'Security surface',
    'References',
)
TELL_WORDS = re.compile(
    r'\b(delve|delves|tapestry|testament|pivotal|crucial|seamless|seamlessly|robust'
    r'|leverage|leverages|leveraging|utilize|utilizes|utilizing|underscore|underscores'
    r'|showcase|showcases|foster|fosters|ever-evolving|cutting-edge|game-changer'
    r'|vital role|navigate the complexities|in conclusion)\b',
    re.IGNORECASE,
)
FILLER_OPENER = re.compile(
    r'(^|(?<=[.!?] ))(?:Additionally|Furthermore|Moreover|Notably|Importantly'
    r"|It is worth noting that|It's worth noting that),? +([a-z])"
)
DIGIT_DASH = re.compile(r'(?<=\d)\s*[\u2013\u2014]\s*(?=\d)')
PROSE_DASH = re.compile(r'\s*[\u2013\u2014]\s*')
PLACEHOLDER = re.compile(r'\{\{.*?\}\}')
CITATION = re.compile(r'\[[^\]]+\]\s*$')
INLINE_CODE = re.compile(r'`[^`]*`')
HEADING = re.compile(r'^## (.+?)\s*$')


class Command(StrEnum):
    CHECK = 'check'
    FIX = 'fix'


class Shape(StrEnum):
    TRACKER = 'tracker'
    COMMENT = 'comment'


PROSE_RULES = frozenset({'placeholder', 'tell-word', 'dash', 'filler-opener'})
STRUCTURE_RULES = frozenset({'missing-section', 'section-order', 'uncited-finding'})
RULES_BY_SHAPE: dict[Shape, frozenset[str]] = {
    Shape.TRACKER: PROSE_RULES | STRUCTURE_RULES,
    Shape.COMMENT: PROSE_RULES,
}


class BodyError(Exception):
    pass


class MissingBodyError(BodyError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} does not exist')


@dataclass(frozen=True, slots=True)
class Issue:
    line: int
    rule: str
    detail: str


@dataclass(frozen=True, slots=True)
class Fixed:
    text: str
    changes: list[Issue]


@dataclass(frozen=True, slots=True)
class ProseLine:
    number: int
    text: str
    section: str


def prose_lines(text: str) -> Iterator[ProseLine]:
    fenced = False
    section = ''
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith('```'):
            fenced = not fenced
            continue
        heading = HEADING.match(line)
        if heading:
            section = heading.group(1)
        if not fenced:
            yield ProseLine(number=number, text=line, section=section)


def without_code(line: str) -> str:
    return INLINE_CODE.sub('', line)


def section_issues(text: str) -> list[Issue]:
    headings = [(line.number, line.section) for line in prose_lines(text)]
    seen = list(dict.fromkeys(section for _, section in headings if section))
    issues = [
        Issue(line=1, rule='missing-section', detail=f'## {name} is required')
        for name in REQUIRED_SECTIONS
        if name not in seen
    ]
    known = [name for name in seen if name in SECTION_ORDER]
    if known != sorted(known, key=SECTION_ORDER.index):
        issues.append(Issue(line=1, rule='section-order', detail=' > '.join(SECTION_ORDER)))
    return issues


def line_issues(line: ProseLine) -> Iterator[Issue]:
    prose = without_code(line.text)
    if PLACEHOLDER.search(prose):
        yield Issue(line.number, 'placeholder', 'template placeholder left in')
    for match in TELL_WORDS.finditer(prose):
        yield Issue(line.number, 'tell-word', f'reword "{match.group(0)}"')
    if PROSE_DASH.search(prose):
        yield Issue(line.number, 'dash', 'em or en dash in prose')
    if FILLER_OPENER.search(prose):
        yield Issue(line.number, 'filler-opener', 'sentence opens with filler')
    uncited = line.section == 'Findings' and prose.startswith('- ')
    if uncited and not CITATION.search(prose):
        yield Issue(line.number, 'uncited-finding', 'a finding ends with [citation]')


def check(text: str, shape: Shape) -> list[Issue]:
    issues = section_issues(text)
    for line in prose_lines(text):
        issues.extend(line_issues(line))
    enabled = RULES_BY_SHAPE[shape]
    kept = [issue for issue in issues if issue.rule in enabled]
    return sorted(kept, key=operator.attrgetter('line'))


def capitalize_opener(match: re.Match[str]) -> str:
    return f'{match.group(1)}{match.group(2).upper()}'


def repair(line: str) -> str:
    pieces = re.split(r'(`[^`]*`)', line)
    for index in range(0, len(pieces), 2):
        text = DIGIT_DASH.sub('-', pieces[index])
        text = PROSE_DASH.sub(', ', text)
        pieces[index] = FILLER_OPENER.sub(capitalize_opener, text)
    return ''.join(pieces)


def fix(text: str) -> Fixed:
    lines = text.splitlines(keepends=True)
    changes: list[Issue] = []
    for line in prose_lines(text):
        repaired = repair(line.text)
        if repaired != line.text:
            ending = lines[line.number - 1][len(line.text) :]
            lines[line.number - 1] = repaired + ending
            changes.append(Issue(line.number, 'fixed', repaired.strip()))
    return Fixed(text=''.join(lines), changes=changes)


def report(path: Path, issues: list[Issue]) -> str:
    return ''.join(f'{path}:{issue.line}: {issue.rule}: {issue.detail}\n' for issue in issues)


@dataclass(frozen=True, slots=True)
class Result:
    output: str
    clean: bool


def read_body(path: Path) -> str:
    if not path.is_file():
        raise MissingBodyError(path)
    return path.read_text(encoding='utf-8')


def run_check(path: Path, shape: Shape) -> Result:
    issues = check(read_body(path), shape)
    return Result(output=report(path, issues) or f'{path}: clean\n', clean=not issues)


def run_fix(path: Path, shape: Shape) -> Result:
    fixed = fix(read_body(path))
    path.write_text(fixed.text, encoding='utf-8')
    remaining = check(fixed.text, shape)
    summary = f'{path}: {len(fixed.changes)} lines fixed, {len(remaining)} issues remain\n'
    output = report(path, fixed.changes) + report(path, remaining) + summary
    return Result(output=output, clean=not remaining)


HANDLERS: dict[Command, Callable[[Path, Shape], Result]] = {
    Command.CHECK: run_check,
    Command.FIX: run_fix,
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog='humanize_tracker_body.py', description=__doc__.splitlines()[0]
    )
    root.add_argument('command', choices=[command.value for command in Command])
    root.add_argument('body', type=Path)
    root.add_argument(
        '--shape', choices=[shape.value for shape in Shape], default=Shape.TRACKER.value
    )
    return root


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        result = HANDLERS[Command(options.command)](options.body, Shape(options.shape))
    except BodyError as error:
        sys.stderr.write(f'error: {error}\n')
        return EXIT_REJECTED
    sys.stdout.write(result.output)
    return 0 if result.clean else EXIT_ISSUES


if __name__ == '__main__':
    raise SystemExit(main())
