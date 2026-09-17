import re
import xml.etree.ElementTree as ET
from collections.abc import Callable

from pydantic import BaseModel, Field

from mightymcp.fleet import FLEET_ROLES

# Vocabularies come from contracts.md; grumpy and sunny classify entries instead of
# carrying a verdict, so their leading entry class is the verdict the loop routes on.
VERDICTS = {
    'scout': ('VERIFIED', 'INFERRED', 'NEEDS-ANALYSIS', 'UNKNOWN-BLOCKED'),
    'engineer': ('done', 'blocked'),
    'budgetron': ('fixed', 'escalated'),
    'gitty-up': ('pass', 'fail', 'error'),
    'grumpy': ('DEFECT', 'RISK', 'QUESTION'),
    'sunny': ('CONFIRMED', 'SOUND', 'UNCONFIRMED'),
}
WINGMAN = 'wingman'
ROLES = FLEET_ROLES
TEXT_ROLES = ('grumpy', 'sunny')
REQUIRED = {
    'scout': ('verdict', 'confidence'),
    'engineer': ('status', 'group', 'tasks', 'deviation'),
    'budgetron': ('status', 'issue'),
    'gitty-up': ('verdict', 'confidence'),
    WINGMAN: ('decision', 'verdict', 'confidence'),
}
# grumpy's QUESTION carries the question itself where the other classes carry evidence
ANCHORED = {'grumpy': ('DEFECT', 'RISK'), 'sunny': VERDICTS['sunny']}
CONFIDENCE = ('high', 'medium', 'low')
VERIFIED_STATES = ('true', 'false', 'deferred')
BLOCKED = 'UNKNOWN-BLOCKED'
STOP_VERDICTS = ('fail', 'error')
NO_ENTRIES = 'NONE'
BLOCKER = 'blocker'
CHECKED = 'Checked:'
PRESERVE = 'Preserve:'
REPORT_SPAN = re.compile(r'<report\b.*?</report>', re.DOTALL)
ENTRY = re.compile(r'^\[([A-Za-z-]+)\]\s*(.*)$')
DETAIL = re.compile(
    r'^\s*(Where|Why it breaks|Unknown|Evidence|Would need|Depends on it):\s*(.*)$'
)
WHERE = 'Where'


class ReportFinding(BaseModel):
    """One piece of evidence a worker reported, with where it was found."""

    kind: str = Field(default='', description='Entry class, CI bucket, or blocker')
    location: str = Field(default='', description='file:line, URL, or a check name')
    summary: str = Field(default='', description='The claim, in one line')
    task: str = Field(default='', description='The task a blocker stops, for engineers')


class ReportTask(BaseModel):
    """One task in an engineer's report, with the verification state it claims."""

    id: str = Field(description='Task id from the plan, e.g. T3')
    verified: str = Field(description='true, false, or deferred')
    note: str = Field(default='', description='What the coordinator must know')


class WorkerReport(BaseModel):
    """A worker's report parsed: the verdict the loop routes on, and its evidence."""

    role: str = Field(description='The fleet role that wrote the report')
    verdict: str = Field(default='', description="The role's verdict, status, or class")
    confidence: str = Field(default='', description='high, medium, or low')
    stop: bool = Field(default=False, description='True when CI did not pass')
    blocked_at: str = Field(
        default='', description='Where the answer lives, for an UNKNOWN-BLOCKED scout'
    )
    subject: str = Field(
        default='', description='What the report is about: group, issue, PR, decision'
    )
    summary: str = Field(
        default='',
        description="The role's payload: the command, deviation, verify, or CI logs",
    )
    findings: list[ReportFinding] = Field(
        default_factory=list, description='The evidence the report carries'
    )
    tasks: list[ReportTask] = Field(
        default_factory=list, description='The engineer report per-task states'
    )
    files_changed: list[str] = Field(
        default_factory=list, description='Paths the worker wrote'
    )
    follow_up: str = Field(default='', description='What is worth asking next')
    checked: str = Field(
        default='', description='The coverage line grumpy and sunny close with'
    )
    preserve: list[str] = Field(
        default_factory=list, description='What the next iteration must not change'
    )
    refusals: list[str] = Field(
        default_factory=list, description='Why the report could not be parsed'
    )


def parse_report(role: str, text: str) -> WorkerReport:
    """Parse one worker's report into the verdict and the evidence behind it."""
    if role not in ROLES:
        return _refused(role, f'unknown role {role!r}; expected {", ".join(ROLES)}')
    report = _parse_text(role, text) if role in TEXT_ROLES else _parse_xml(role, text)
    if report.refusals:
        return _refused(role, *report.refusals)
    return report


def _parse_xml(role: str, text: str) -> WorkerReport:
    span = REPORT_SPAN.search(text)
    if span is None:
        return _refused(role, 'no <report> element; this is not a report')
    try:
        root = ET.fromstring(span.group())  # noqa: S314 -- same, a fleet worker wrote it
    except ET.ParseError as err:
        return _refused(role, f'<report> is not well-formed XML: {err}')
    missing = [tag for tag in REQUIRED[role] if root.find(tag) is None]
    if missing:
        return _refused(role, f'the {role} report is missing {", ".join(missing)}')
    return PARSERS[role](root)


def _scout(root: ET.Element) -> WorkerReport:
    verdict, refusals = _verdict('scout', _child(root, 'verdict'))
    refusals.extend(_confidence_refusals(_child(root, 'confidence')))
    findings = [
        ReportFinding(location=element.get('location', ''), summary=_collapse(element))
        for element in root.iterfind('findings/finding')
    ]
    follow_up = _child(root, 'follow_up')
    blocked_at = ''
    if verdict == BLOCKED:
        blocked_at = follow_up or next((f.location for f in findings), '')
        if not blocked_at:
            refusals.append(
                f'{BLOCKED} names neither a follow_up nor a finding; contracts.md '
                'wants where the answer lives'
            )
    return WorkerReport(
        role='scout',
        verdict=verdict,
        confidence=_child(root, 'confidence'),
        blocked_at=blocked_at,
        summary=_child(root, 'command'),
        findings=findings,
        follow_up=follow_up,
        refusals=refusals,
    )


def _engineer(root: ET.Element) -> WorkerReport:
    verdict, refusals = _verdict('engineer', _child(root, 'status'))
    tasks = []
    for element in root.iterfind('tasks/task'):
        state = element.get('verified', '')
        if state not in VERIFIED_STATES:
            refusals.append(
                f'task {element.get("id", "")!r} is verified={state!r}; expected '
                f'{", ".join(VERIFIED_STATES)}'
            )
        tasks.append(
            ReportTask(id=element.get('id', ''), verified=state, note=_collapse(element))
        )
    if not tasks:
        refusals.append('the engineer report names no task; every task is accounted for')
    return WorkerReport(
        role='engineer',
        verdict=verdict,
        subject=_child(root, 'group'),
        summary=_child(root, 'deviation'),
        tasks=tasks,
        files_changed=[_collapse(f) for f in root.iterfind('files_changed/file')],
        findings=[
            ReportFinding(
                kind=BLOCKER,
                task=element.get('task', ''),
                location=element.get('location', ''),
                summary=_collapse(element),
            )
            for element in root.iterfind('blockers/blocker')
        ],
        refusals=refusals,
    )


def _budgetron(root: ET.Element) -> WorkerReport:
    verdict, refusals = _verdict('budgetron', _child(root, 'status'))
    findings = []
    summary = ''
    if verdict == 'fixed':
        summary = _attr(root, 'verify', 'command')
        if not summary:
            refusals.append(
                'a fixed report carries no <verify command>; a fix without '
                'its check is not reportable'
            )
    elif verdict == 'escalated':
        blocker = root.find('blocker')
        if blocker is None:
            refusals.append('an escalated report carries no <blocker>')
        else:
            findings.append(
                ReportFinding(
                    kind=BLOCKER,
                    location=blocker.get('location', ''),
                    summary=_collapse(blocker),
                )
            )
    return WorkerReport(
        role='budgetron',
        verdict=verdict,
        subject=_child(root, 'issue'),
        summary=summary,
        files_changed=[_collapse(f) for f in root.iterfind('files_changed/file')],
        findings=findings,
        refusals=refusals,
    )


def _gitty_up(root: ET.Element) -> WorkerReport:
    verdict, refusals = _verdict('gitty-up', _child(root, 'verdict'))
    refusals.extend(_confidence_refusals(_child(root, 'confidence')))
    logs = root.find('logs')
    return WorkerReport(
        role='gitty-up',
        verdict=verdict,
        confidence=_child(root, 'confidence'),
        stop=verdict in STOP_VERDICTS,
        subject=root.get('pr', ''),
        summary=(logs.text or '').strip() if logs is not None else '',
        findings=[
            ReportFinding(
                kind=element.get('bucket', ''),
                location=element.get('location', ''),
                summary=_collapse(element),
            )
            for element in root.iterfind('findings/finding')
        ],
        follow_up=_child(root, 'follow_up'),
        refusals=refusals,
    )


def _wingman(root: ET.Element) -> WorkerReport:
    level = _attr(root, 'confidence', 'level')
    return WorkerReport(
        role=WINGMAN,
        verdict=_child(root, 'verdict'),
        confidence=level,
        subject=_child(root, 'decision'),
        summary=_child(root, 'verify'),
        follow_up=_child(root, 'follow_up'),
        refusals=_confidence_refusals(level),
    )


def _parse_text(role: str, text: str) -> WorkerReport:
    lines = text.splitlines()
    checked = next(
        (
            line.strip().removeprefix(CHECKED).strip()
            for line in lines
            if line.strip().startswith(CHECKED)
        ),
        '',
    )
    if not checked:
        return _refused(role, f'no {CHECKED} line; this is not a {role} report')
    findings, refusals = _entries(role, lines)
    return WorkerReport(
        role=role,
        verdict=_leading(role, findings),
        findings=findings,
        checked=checked,
        preserve=_preserve(lines),
        refusals=refusals,
    )


def _entries(role: str, lines: list[str]) -> tuple[list[ReportFinding], list[str]]:
    """Read the [CLASS] entries grumpy and sunny report, with their Where: anchors."""
    findings: list[ReportFinding] = []
    refusals: list[str] = []
    claim: list[str] = []
    detail = ''
    for line in lines:
        entry = ENTRY.match(line)
        if entry is not None:
            kind, opening = entry.groups()
            refusals.extend(_class_refusals(role, kind))
            claim, detail = [opening], ''
            findings.append(ReportFinding(kind=kind, summary=_claim(claim)))
        elif not findings or not line.strip() or line.strip().startswith(CHECKED):
            claim, detail = [], ''
        elif (key := DETAIL.match(line)) is not None:
            detail = key.group(1)
            if detail == WHERE:
                findings[-1].location = key.group(2).strip()
        elif detail == '':
            claim.append(line)
            findings[-1].summary = _claim(claim)
    refusals.extend(_anchor_refusals(role, findings))
    return findings, refusals


def _claim(claim: list[str]) -> str:
    return ' '.join(' '.join(claim).split())


def _class_refusals(role: str, kind: str) -> list[str]:
    if kind in VERDICTS[role]:
        return []
    return [
        (
            f'entry class [{kind}] is outside the {role} vocabulary: '
            f'{", ".join(VERDICTS[role])}'
        )
    ]


def _anchor_refusals(role: str, findings: list[ReportFinding]) -> list[str]:
    return [
        f'[{finding.kind}] {finding.summary!r} carries no {WHERE}: line'
        for finding in findings
        if finding.kind in ANCHORED[role] and not finding.location
    ]


def _leading(role: str, findings: list[ReportFinding]) -> str:
    """The first class in the role's order that the report carries: its verdict."""
    kinds = {finding.kind for finding in findings}
    return next((kind for kind in VERDICTS[role] if kind in kinds), NO_ENTRIES)


def _preserve(lines: list[str]) -> list[str]:
    block = []
    inside = False
    for line in lines:
        if line.strip().startswith(PRESERVE):
            inside = True
        elif line.strip().startswith(CHECKED):
            inside = False
        elif inside and line.strip().startswith('- '):
            block.append(line.strip().removeprefix('- '))
    return block


def _verdict(role: str, value: str) -> tuple[str, list[str]]:
    if value in VERDICTS[role]:
        return value, []
    return '', [
        f'verdict {value!r} is outside the {role} vocabulary: {", ".join(VERDICTS[role])}'
    ]


def _confidence_refusals(value: str) -> list[str]:
    if value in CONFIDENCE:
        return []
    return [f'confidence {value!r} is not {", ".join(CONFIDENCE)}']


def _child(root: ET.Element, tag: str) -> str:
    element = root.find(tag)
    return '' if element is None else _collapse(element)


def _attr(root: ET.Element, tag: str, name: str) -> str:
    element = root.find(tag)
    return '' if element is None else element.get(name, '')


def _collapse(element: ET.Element) -> str:
    return ' '.join((element.text or '').split())


def _refused(role: str, *refusals: str) -> WorkerReport:
    return WorkerReport(role=role, refusals=list(refusals))


PARSERS: dict[str, Callable[[ET.Element], WorkerReport]] = {
    'scout': _scout,
    'engineer': _engineer,
    'budgetron': _budgetron,
    'gitty-up': _gitty_up,
    WINGMAN: _wingman,
}
