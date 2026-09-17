import re

from pydantic import BaseModel, Field

from mightymcp.artifacts import bullets, missing_refusals, ticket_directory
from mightymcp.routing import CRITICAL, FINDING_SOURCES, HIGH, SEVERITIES

MEDIUM = 'Medium'
# contracts.md: uncle-bob's Blocker is Critical everywhere else in the loop
UNCLE_BOB_BLOCKER = 'Blocker'
REPORTED_SEVERITIES = (UNCLE_BOB_BLOCKER, *SEVERITIES)
NEEDS_USER_GAP = 2
BLOCK = 'BLOCK'
CONDITIONS = 'MERGE WITH CONDITIONS'
CLEAR = 'CLEAR'
REVIEW_VERDICTS = (BLOCK, CONDITIONS, CLEAR)
REVIEW_DIR = 'review'
REPORTS = {
    'merge-vader': 'MERGE-VADER-REPORT.md',
    'uncle-bob': 'UNCLE-BOB-REPORT.md',
}
SPAN = re.compile(r'^(\d+)(?:-(\d+))?$')
NO_SPAN = (0, 0)
# report.md: the weighted mean over the eight categories, on a 4-point scale
WEIGHTS = {
    'tests': 2.0,
    'classes_and_solid': 2.0,
    'components_and_architecture': 2.0,
    'functions': 1.5,
    'error_handling': 1.5,
    'simplicity_and_duplication': 1.5,
    'names': 1.0,
    'comments': 0.5,
}
POINTS = {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}
BANDS = (('A', 3.7), ('B', 3.0), ('C', 2.0), ('D', 1.0))
FAIL = 'F'
PURE = 'pure'
CALIBRATED = 'calibrated'
# report.md's hard cap: a nontrivial codebase with zero tests cannot grade above these
NO_TEST_CAPS = {PURE: 'D', CALIBRATED: 'C'}


class Finding(BaseModel):
    """One review finding, in the shape contracts.md gives the finding format."""

    id: str = Field(description='Stable within its report: MV-n or UB-n')
    severity: str = Field(description=f'One of {", ".join(REPORTED_SEVERITIES)}')
    file: str = Field(description='The file the evidence was read in')
    line: str = Field(description='The line, or a span: 42 or 142-149')
    source: str = Field(description=f'One of {", ".join(FINDING_SOURCES)}')
    summary: str = Field(default='', description='Why it matters, in one line')


class MergedFinding(BaseModel):
    """One defect, with every reviewer that found it and the severity that stands."""

    ids: list[str] = Field(description='Every reporting ID, provenance preserved')
    file: str = Field(description='The file the defect lives in')
    line: str = Field(description='The span the reports cover together')
    severity: str = Field(description='The higher of the reported severities')
    severities: list[str] = Field(description='Every severity reported, as reported')
    sources: list[str] = Field(description='Every reviewer that found it')
    summary: str = Field(default='', description='The summary at the higher severity')
    needs_user: bool = Field(
        default=False, description='True when the severities sit two or more levels apart'
    )
    note: str = Field(default='', description='What the reviewers disagreed about')


class FindingsMerge(BaseModel):
    """The two reviewers' findings as one list, deduped by file:line overlap."""

    findings: list[MergedFinding] = Field(
        default_factory=list, description='One entry per defect'
    )
    needs_user: bool = Field(
        default=False, description='True when any defect needs the user to judge'
    )
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was merged'
    )


class ReviewVerdict(BaseModel):
    """The gated verdict, and the rule that produced it."""

    verdict: str | None = Field(
        default=None, description=f'One of {", ".join(REVIEW_VERDICTS)}'
    )
    rule: str = Field(default='', description='The rule that fired')
    refusals: list[str] = Field(
        default_factory=list, description='Why no verdict was issued'
    )


class GradeInput(BaseModel):
    """A letter grade per uncle-bob category, before the weights are applied."""

    names: str = Field(description='Names (ch 2; N1-N7)')
    functions: str = Field(description='Functions (ch 3)')
    comments: str = Field(description='Comments (ch 4)')
    error_handling: str = Field(description='Error Handling (ch 7)')
    tests: str = Field(description='Tests (ch 9)')
    classes_and_solid: str = Field(description='Classes & SOLID (ch 10)')
    components_and_architecture: str = Field(description='Components & Architecture')
    simplicity_and_duplication: str = Field(description='Simplicity & Duplication')


class GradeResult(BaseModel):
    """The overall grade: the weighted mean, and the no-tests cap when it bit."""

    grade: str | None = Field(default=None, description='A, B, C, D, or F')
    score: float = Field(default=0.0, description='The weighted mean on a 4-point scale')
    capped: bool = Field(default=False, description='True when the no-tests cap applied')
    rule: str = Field(default='', description='The rule that fired')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was graded'
    )


class ReviewWrite(BaseModel):
    """The reviewer's report as written, or why nothing was written."""

    path: str | None = Field(default=None, description='Absolute path of the report')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was written'
    )


class PrComment(BaseModel):
    """The review comment for the PR, rendered as markdown."""

    text: str = Field(default='', description='The comment body')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was rendered'
    )


def findings_merge(findings: list[Finding]) -> FindingsMerge:
    """Merge the reviewers' findings: one entry per defect, both IDs preserved."""
    refusals = [*_vocabulary_refusals(findings), *_span_refusals(findings)]
    if refusals:
        return FindingsMerge(refusals=refusals)

    merged = [_merge(group) for group in _group(findings)]
    return FindingsMerge(
        findings=merged, needs_user=any(finding.needs_user for finding in merged)
    )


def review_verdict(
    findings: list[Finding], *, security_unknown_blocked: bool = False
) -> ReviewVerdict:
    """Apply merge-vader's gate: Critical or High blocks, Medium conditions."""
    refusals = _vocabulary_refusals(findings)
    if refusals:
        return ReviewVerdict(refusals=refusals)

    severities = {_mapped(finding.severity) for finding in findings}
    if severities & {CRITICAL, HIGH}:
        return ReviewVerdict(verdict=BLOCK, rule='a Critical or High finding')
    if security_unknown_blocked:
        return ReviewVerdict(
            verdict=CONDITIONS,
            rule='a security-relevant question sits UNKNOWN-BLOCKED; CLEAR is impossible',
        )
    if MEDIUM in severities:
        return ReviewVerdict(verdict=CONDITIONS, rule='a Medium finding')
    return ReviewVerdict(verdict=CLEAR, rule='no Critical, High, or Medium finding')


def grade_compute(
    categories: GradeInput, mode: str = PURE, *, tests_present: bool = True
) -> GradeResult:
    """Grade the eight categories: report.md's weighted mean, under its no-tests cap."""
    grades = categories.model_dump()
    refusals = [
        f'{category} is graded {grade!r}; expected {", ".join(POINTS)}'
        for category, grade in sorted(grades.items())
        if grade not in POINTS
    ]
    if mode not in NO_TEST_CAPS:
        refusals.append(f'unknown mode {mode!r}; expected {", ".join(NO_TEST_CAPS)}')
    if refusals:
        return GradeResult(refusals=refusals)

    score = sum(POINTS[grades[name]] * weight for name, weight in WEIGHTS.items())
    score = round(score / sum(WEIGHTS.values()), 2)
    grade = next((letter for letter, floor in BANDS if score >= floor), FAIL)
    cap = NO_TEST_CAPS[mode]
    if not tests_present and POINTS[grade] > POINTS[cap]:
        return GradeResult(
            grade=cap,
            score=score,
            capped=True,
            rule=f'no tests: {mode} mode caps the grade at {cap}',
        )
    return GradeResult(grade=grade, score=score, rule=f'weighted mean {score} is {grade}')


def review_report_write(slug: str, reviewer: str, body: str) -> ReviewWrite:
    """Write review/MERGE-VADER-REPORT.md or review/UNCLE-BOB-REPORT.md."""
    directory, refusals = ticket_directory(slug)
    if reviewer not in REPORTS:
        refusals.append(f'unknown reviewer {reviewer!r}; expected {", ".join(REPORTS)}')
    refusals.extend(missing_refusals({'body': body}))
    if directory is None or refusals:
        return ReviewWrite(refusals=refusals)

    path = directory.joinpath(REVIEW_DIR, REPORTS[reviewer])
    path.parent.mkdir(exist_ok=True)
    path.write_text(body if body.endswith('\n') else body + '\n', encoding='utf-8')
    return ReviewWrite(path=str(path))


def pr_comment_render(
    verdict: str, findings: list[Finding], remediation: list[str] | None = None
) -> PrComment:
    """Render the PR comment: the verdict, the findings by severity, the conditions."""
    refusals = _vocabulary_refusals(findings)
    if verdict not in REVIEW_VERDICTS:
        refusals.append(
            f'unknown verdict {verdict!r}; expected {", ".join(REVIEW_VERDICTS)}'
        )
    if refusals:
        return PrComment(refusals=refusals)

    lines = [f'VERDICT: {verdict}', '', '## Findings', '']
    lines.extend(_finding_sections(findings))
    if verdict == CONDITIONS:
        lines.extend(('', '## Conditions', *bullets(_conditions(findings, remediation))))
    return PrComment(text='\n'.join(lines) + '\n')


def _finding_sections(findings: list[Finding]) -> list[str]:
    lines: list[str] = []
    for severity in SEVERITIES:
        at_severity = [f for f in findings if _mapped(f.severity) == severity]
        if not at_severity:
            continue
        lines.extend((f'### {severity}', ''))
        lines.extend(f'- {f.id} | `{f.file}:{f.line}` | {f.summary}' for f in at_severity)
        lines.append('')
    if not lines:
        return bullets([])
    return lines[:-1]


def _conditions(findings: list[Finding], remediation: list[str] | None) -> list[str]:
    if remediation:
        return remediation
    return [
        f'{finding.id}: {finding.summary}'
        for finding in findings
        if _mapped(finding.severity) == MEDIUM
    ]


def _group(findings: list[Finding]) -> list[list[Finding]]:
    """Group findings that overlap on file:line; each group is one defect.

    Sorted by file and span first, so a chain of overlaps closes the same way
    whatever order the reviewers reported it in: once the spans ascend, only the
    group still being built can overlap the next finding.
    """
    groups: list[list[Finding]] = []
    for finding in sorted(findings, key=lambda entry: (entry.file, _span(entry.line))):
        span = _span(finding.line)
        open_group = groups[-1] if groups else None
        if (
            open_group is not None
            and open_group[0].file == finding.file
            and _overlaps(_bounds(open_group), span)
        ):
            open_group.append(finding)
        else:
            groups.append([finding])
    return groups


def _merge(group: list[Finding]) -> MergedFinding:
    ranked = sorted(
        group, key=lambda finding: SEVERITIES.index(_mapped(finding.severity))
    )
    severity = _mapped(ranked[0].severity)
    gap = SEVERITIES.index(_mapped(ranked[-1].severity)) - SEVERITIES.index(severity)
    start, end = _bounds(group)
    return MergedFinding(
        ids=[finding.id for finding in group],
        file=group[0].file,
        line=str(start) if start == end else f'{start}-{end}',
        severity=severity,
        severities=list(dict.fromkeys(finding.severity for finding in group)),
        sources=list(dict.fromkeys(finding.source for finding in group)),
        summary=ranked[0].summary,
        needs_user=gap >= NEEDS_USER_GAP,
        note=_note(ranked, severity, gap),
    )


def _note(ranked: list[Finding], severity: str, gap: int) -> str:
    if gap == 0:
        return ''
    reported = ' and '.join(f'{f.id} {f.severity}' for f in ranked)
    note = f'{reported}; kept {severity}'
    if gap >= NEEDS_USER_GAP:
        return f'{note}, {gap} levels apart: the user judges this one'
    return note


def _bounds(group: list[Finding]) -> tuple[int, int]:
    spans = [_span(finding.line) for finding in group]
    return min(span[0] for span in spans), max(span[1] for span in spans)


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] <= right[1] and right[0] <= left[1]


def _span(line: str) -> tuple[int, int]:
    match = SPAN.match(line.strip())
    if match is None:
        return NO_SPAN
    start, end = match.groups()
    return int(start), int(end or start)


def _mapped(severity: str) -> str:
    return CRITICAL if severity == UNCLE_BOB_BLOCKER else severity


def _vocabulary_refusals(findings: list[Finding]) -> list[str]:
    refusals = [
        f'{finding.id} is {finding.severity!r}; expected {", ".join(REPORTED_SEVERITIES)}'
        for finding in findings
        if finding.severity not in REPORTED_SEVERITIES
    ]
    refusals.extend(
        f'{finding.id} came from {finding.source!r}; expected '
        f'{", ".join(FINDING_SOURCES)}'
        for finding in findings
        if finding.source not in FINDING_SOURCES
    )
    return refusals


def _span_refusals(findings: list[Finding]) -> list[str]:
    return [
        f'{finding.id} cites line {finding.line!r}; expected 42 or 142-149'
        for finding in findings
        if _span(finding.line) == NO_SPAN
    ]
