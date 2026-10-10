"""Findings from persona reports: validated in full, redacted, merged by location, numbered.

Every reported severity is stored on the one ladder (a Blocker is High). An incoming finding
whose location overlaps a recorded one on the same file merges into it: the sources join, the
higher severity wins, and a gap of two levels or more records a conflict for the user to decide.

A text that redaction lengthens past its limit refuses the batch.
"""

import re
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from mightymodels_plugin.core.declarative import PROSE_LIMIT
from mightymodels_plugin.redaction import redact_within
from mightymodels_plugin.tools.review.errors import (
    FieldRequiredError,
    LocationShapeError,
    UnsupportedQualityError,
)
from mightymodels_plugin.tools.review.schema import (
    Evidence,
    Finding,
    FindingInput,
    Kind,
    ReportedSeverity,
    Severity,
)

LOCATION = re.compile(r'^(?P<path>[^\s:]+):(?P<start>\d+)(?:-(?P<end>\d+))?$')
UNNUMBERED = 'F0'
CONFLICT_GAP = 2

type Span = tuple[str, int, int]

RANK: Mapping[Severity, int] = MappingProxyType(
    {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
)
STORED_SEVERITY: Mapping[ReportedSeverity, Severity] = MappingProxyType(
    {
        ReportedSeverity.BLOCKER: Severity.HIGH,
        ReportedSeverity.CRITICAL: Severity.CRITICAL,
        ReportedSeverity.HIGH: Severity.HIGH,
        ReportedSeverity.MEDIUM: Severity.MEDIUM,
        ReportedSeverity.LOW: Severity.LOW,
    }
)


def finding_number(finding_id: str) -> int:
    return int(finding_id[1:])


def number_of(finding: Finding) -> int:
    return finding_number(finding.id)


def span_of(location: str) -> Span:
    match = LOCATION.match(location)
    if match is None:
        return location, 0, 0
    path = str(match['path'])
    start = int(match['start'])
    return path, start, start if match['end'] is None else int(match['end'])


def required_text(index: int, sources: Sequence[str], field: str, *, value: str) -> str:
    text = value.strip()
    if not text:
        raise FieldRequiredError(index, sources, field)
    return redact_within(text, field, PROSE_LIMIT)


def evidence_of(index: int, sources: Sequence[str], evidence: Evidence | None) -> Evidence | None:
    if evidence is None:
        return None
    cite = required_text(index, sources, 'evidence cite', value=evidence.cite)
    return Evidence(kind=evidence.kind, cite=cite)


def normalized(entry: FindingInput, index: int) -> Finding:
    sources = sorted(set(entry.sources))
    location = required_text(index, sources, 'location', value=entry.location)
    if not LOCATION.match(location):
        raise LocationShapeError(index, sources)
    severity = STORED_SEVERITY[entry.severity]
    finding = Finding(
        id=UNNUMBERED,
        sources=tuple(sources),
        severity=severity,
        kind=entry.kind,
        security=entry.security,
        title=required_text(index, sources, 'title', value=entry.title),
        location=location,
        fix=required_text(index, sources, 'fix', value=entry.fix),
        verify=required_text(index, sources, 'verify', value=entry.verify),
        evidence=evidence_of(index, sources, entry.evidence),
    )
    supported = finding.evidence is not None or severity is Severity.LOW
    if finding.kind is Kind.QUALITY and not supported:
        raise UnsupportedQualityError(index, sources)
    return finding


def overlaps(left: Finding, right: Finding) -> bool:
    left_path, left_start, left_end = span_of(left.location)
    right_path, right_start, right_end = span_of(right.location)
    return left_path == right_path and left_start <= right_end and right_start <= left_end


def conflict_between(keep: Finding, other: Finding, current: str | None) -> str | None:
    gap = abs(RANK[keep.severity] - RANK[other.severity])
    if gap < CONFLICT_GAP:
        return current
    return (
        f'{"/".join(other.sources)} rated {other.severity}, '
        f'{"/".join(keep.sources)} rated {keep.severity}: the user decides'
    )


def merged(existing: Finding, incoming: Finding) -> Finding:
    incoming_is_higher = RANK[incoming.severity] < RANK[existing.severity]
    keep, other = (incoming, existing) if incoming_is_higher else (existing, incoming)
    return Finding(
        id=existing.id,
        sources=tuple(sorted(set(existing.sources) | set(incoming.sources))),
        severity=keep.severity,
        kind=keep.kind,
        security=existing.security or incoming.security,
        title=keep.title,
        location=keep.location,
        fix=keep.fix,
        verify=keep.verify,
        evidence=other.evidence if keep.evidence is None else keep.evidence,
        conflict=conflict_between(keep, other, existing.conflict),
    )


def placed(recorded: Mapping[str, Finding], incoming: Finding) -> Finding:
    overlapped = next((old for old in recorded.values() if overlaps(old, incoming)), None)
    if overlapped is not None:
        return merged(overlapped, incoming)
    number = max(map(number_of, recorded.values()), default=0) + 1
    return incoming.model_copy(update={'id': f'F{number}'})


def fold(current: Mapping[str, Finding], incoming: Sequence[Finding]) -> list[Finding]:
    working = dict(current)
    changed: dict[str, Finding] = {}
    for finding in incoming:
        result = placed(working, finding)
        working[result.id] = changed[result.id] = result
    return sorted(changed.values(), key=number_of)
