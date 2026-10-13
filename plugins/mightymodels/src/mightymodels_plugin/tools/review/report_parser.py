"""Reads a persona's Markdown report into the typed findings review-circus records.

The report is the reviewer's output and is untrusted, so only its `## Findings` section is
read and every block must fit the templates: a severity heading, then one block per finding.
The kind of a finding follows from who wrote it and, for merge-vader, its dimension, never
from anything the reviewer labels it, so a reviewer cannot call a preference a defect to
dodge the evidence rule. merge-vader gives the location in its untyped `Evidence` bullet and
uncle-bob after the dash in the heading; the typed evidence of both is the bullet
`Evidence (metric|idiom|convention): <cite>`.

A finding is built as the request model a caller would send, so text over its length is refused
there, and the refusal names the finding and the field.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from mightymodels_plugin.tools.review.errors import (
    EvidenceKindError,
    ForeignSourceError,
    InvalidFieldError,
    NoFindingsSectionError,
    UnknownDimensionError,
    UnknownSeverityHeadingError,
    UnplacedFindingError,
    UnreadableHeadingError,
)
from mightymodels_plugin.tools.review.schema import (
    Evidence,
    EvidenceKind,
    FindingInput,
    Kind,
    Persona,
    ReportedSeverity,
)

FINDINGS_HEADING = '## Findings'
SECTION_HEADING = '## '
BLOCK_LEVEL = '####'
SEVERITY_HEADING = re.compile(r'^###\s+(?P<severity>\S+)\s*$')
BLOCK_HEADING = re.compile(r'^####\s+(?P<id>[A-Z]+-\d+)\s*\|\s*(?P<rest>.+?)\s*$')
BULLET = re.compile(
    r'^-\s+(?P<key>[A-Za-z][A-Za-z ]*?)(?:\s+\((?P<kind>[^)]*)\))?:\s*(?P<value>.*)$'
)
BOB_HEADING = re.compile(
    r'^(?:\[[^\]]+\]\s*)?(?P<title>.+)\s+[\u2014\u2013-]+\s+`(?P<location>[^`]+)`$'
)
SEVERITIES: Mapping[str, ReportedSeverity] = MappingProxyType(
    {severity.value.lower(): severity for severity in ReportedSeverity}
)
ID_PREFIX: Mapping[Persona, str] = MappingProxyType(
    {Persona.MERGE_VADER: 'MV-', Persona.UNCLE_BOB: 'UB-'}
)
DIMENSIONS: Mapping[str, tuple[Kind, bool]] = MappingProxyType(
    {
        'security': (Kind.DEFECT, True),
        'sdlc': (Kind.DEFECT, False),
        'quality': (Kind.QUALITY, False),
        'docs': (Kind.DEFECT, False),
        'plan': (Kind.DEFECT, False),
    }
)

type BulletKey = tuple[str, str]
type Bullets = Mapping[BulletKey, str]
type Pointer = tuple[int, str]

LOCATION_KEY: BulletKey = ('evidence', '')
FIX_KEY: BulletKey = ('fix', '')
VERIFY_KEY: BulletKey = ('verify', '')


@dataclass(slots=True, kw_only=True, frozen=True)
class Block:
    severity: ReportedSeverity
    heading: str
    body: Sequence[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class Basis:
    title: str
    location: str
    kind: Kind
    security: bool


@runtime_checkable
class BasisReader(Protocol):
    def __call__(self, at: Pointer, rest: str, bullets: Bullets, /) -> Basis: ...


def findings_section(lines: Sequence[str]) -> Sequence[str]:
    starts = [number for number, line in enumerate(lines) if line.rstrip() == FINDINGS_HEADING]
    if not starts:
        raise NoFindingsSectionError
    after = lines[starts[0] + 1 :]
    ends = [number for number, line in enumerate(after) if line.startswith(SECTION_HEADING)]
    return after[: ends[0]] if ends else after


def severity_of_heading(heading: str) -> ReportedSeverity:
    named = SEVERITY_HEADING.match(heading)
    severity = None if named is None else SEVERITIES.get(named['severity'].lower())
    if severity is None:
        raise UnknownSeverityHeadingError(heading)
    return severity


def blocks_of(lines: Sequence[str]) -> list[Block]:
    starts = [number for number, line in enumerate(lines) if line.startswith('#')]
    ends = [*starts[1:], len(lines)]
    blocks: list[Block] = []
    severity: ReportedSeverity | None = None
    for start, end in zip(starts, ends, strict=True):
        heading = lines[start].rstrip()
        if not heading.startswith(BLOCK_LEVEL):
            severity = severity_of_heading(heading)
            continue
        if severity is None:
            raise UnplacedFindingError(heading)
        blocks.append(Block(severity=severity, heading=heading, body=lines[start + 1 : end]))
    return blocks


def bullet_key(named: re.Match[str]) -> BulletKey:
    kind = '' if named['kind'] is None else str(named['kind'])
    return str(named['key']).lower(), kind


def bullets_of(body: Sequence[str]) -> Bullets:
    bullets: dict[BulletKey, str] = {}
    current: BulletKey | None = None
    for line in body:
        named = BULLET.match(line)
        if named is not None:
            current = bullet_key(named)
            bullets[current] = named['value'].strip()
            continue
        if current is not None and line.strip():
            bullets[current] = f'{bullets[current]} {line.strip()}'
    return bullets


def pointer_location(pointer: str) -> str:
    return next(iter(pointer.split()), '').strip('`')


def merge_vader_basis(at: Pointer, rest: str, bullets: Bullets) -> Basis:
    index, source = at
    dimension, separator, title = rest.partition('|')
    if not separator:
        msg = f'#### {source} | {rest}'
        raise UnreadableHeadingError(msg)
    named = dimension.strip().lower()
    if named not in DIMENSIONS:
        raise UnknownDimensionError(index, [source], named)
    kind, security = DIMENSIONS[named]
    location = pointer_location(bullets.get(LOCATION_KEY, ''))
    return Basis(title=title.strip(), location=location, kind=kind, security=security)


def uncle_bob_basis(_at: Pointer, rest: str, _bullets: Bullets) -> Basis:
    named = BOB_HEADING.match(rest)
    if named is None:
        return Basis(title=rest, location='', kind=Kind.QUALITY, security=False)
    return Basis(
        title=named['title'].strip(),
        location=named['location'].strip(),
        kind=Kind.QUALITY,
        security=False,
    )


BASES: Mapping[Persona, BasisReader] = MappingProxyType(
    {Persona.MERGE_VADER: merge_vader_basis, Persona.UNCLE_BOB: uncle_bob_basis}
)


def typed_evidence(at: Pointer, bullets: Bullets) -> Evidence | None:
    index, source = at
    typed = next(
        ((kind, cite) for (key, kind), cite in bullets.items() if key == 'evidence' and kind),
        None,
    )
    if typed is None:
        return None
    kind, cite = typed
    try:
        named = EvidenceKind(kind.strip().lower())
    except ValueError as error:
        raise EvidenceKindError(index, [source], kind) from error
    return Evidence(kind=named, cite=cite)


def invalid_field_error(at: Pointer, refused: ValidationError) -> InvalidFieldError:
    index, source = at
    first = refused.errors()[0]
    field = '.'.join(map(str, first['loc']))
    return InvalidFieldError(index, [source], field=field, reason=first['msg'])


def finding_of(index: int, block: Block, persona: Persona) -> FindingInput:
    named = BLOCK_HEADING.match(block.heading)
    if named is None:
        raise UnreadableHeadingError(block.heading)
    at = (index, named['id'])
    if not named['id'].startswith(ID_PREFIX[persona]):
        raise ForeignSourceError(index, [named['id']], persona)
    bullets = bullets_of(block.body)
    basis = BASES[persona](at, named['rest'], bullets)
    try:
        return FindingInput(
            sources=(named['id'],),
            severity=block.severity,
            title=basis.title,
            location=basis.location,
            fix=bullets.get(FIX_KEY, ''),
            verify=bullets.get(VERIFY_KEY, ''),
            kind=basis.kind,
            security=basis.security,
            evidence=typed_evidence(at, bullets),
        )
    except ValidationError as error:
        raise invalid_field_error(at, error) from error


def parse_report(text: str, persona: Persona) -> list[FindingInput]:
    blocks = blocks_of(findings_section(text.splitlines()))
    return [finding_of(index, block, persona) for index, block in enumerate(blocks)]
