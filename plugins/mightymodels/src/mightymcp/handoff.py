import re
from pathlib import Path

from pydantic import BaseModel, Field

from mightymcp.artifacts import (
    ALIASED,
    bullets,
    cap_refusals,
    missing_refusals,
    ticket_directory,
)
from mightymcp.paths import MIGHTYMODELS_DIR, git_output
from mightymcp.routing import RampChoice, route_ramp
from mightymcp.status import sprint_status
from mightymcp.ticket import Ticket, ticket_read

SPRINT = 'sprint'
REVIEW = 'review'
BATON = 'baton'
FILES = {SPRINT: 'SPRINT.md', REVIEW: 'REVIEW.md', BATON: 'BATON.md'}
# the baton is the freshest handoff when it exists: it is written mid-work, last
PROMPT_ORDER = (BATON, REVIEW, SPRINT)
BATON_CAP = 40
DECISIONS = 'decisions.md'
DECISIONS_CAP = 40
DECISION_NUMBER = re.compile(r'^- D(\d+):')
FOCUS_PREFIX = 'Focus: '
SKELETON = (
    '# Handoff for {slug}\n'
    '\n'
    '<important>YOU MUST invoke `using-mightymodels`</important>\n'
    '\n'
    '## Handoff Content\n'
    '\n'
    '<!-- The next session reads these first, so they must be correct. -->\n'
)
REVIEW_LINES = (
    '- Invoke `review-circus`.',
    '- The reviewer models come from ticket.yml `subagent-models`.',
)


class HandoffFields(BaseModel):
    """The baton's session-only facts; the sprint and review handoffs ignore them."""

    model_config = ALIASED

    focus: str = Field(default='', description='What the next session is for, one line')
    settled: list[str] = Field(
        default_factory=list, description='Decisions made this session, with their source'
    )
    do_not_retry: list[str] = Field(
        default_factory=list, description='Approaches that failed, and why'
    )
    works: list[str] = Field(
        default_factory=list, description='Exact commands, and what each proves'
    )
    gotchas: list[str] = Field(
        default_factory=list, description='What cost time, and what to do instead'
    )
    parked: list[str] = Field(
        default_factory=list, description='Threads parked, and the signal to revisit'
    )


class HandoffWrite(BaseModel):
    """The handoff file as written, or why nothing was written."""

    kind: str = Field(description='sprint, review, or baton')
    path: str | None = Field(default=None, description='Absolute path of the handoff')
    text: str = Field(default='', description='The handoff as written')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was written'
    )


class HandoffPrompt(BaseModel):
    """The prompt that opens the next session, pointing at the handoff on disk."""

    kind: str | None = Field(default=None, description='The handoff the prompt points at')
    path: str | None = Field(default=None, description='Absolute path of that handoff')
    prompt: str = Field(default='', description='The one-paragraph opening prompt')
    refusals: list[str] = Field(
        default_factory=list, description='Why no prompt was built'
    )


class DecisionWrite(BaseModel):
    """The decision as appended to the ledger, or why it was refused."""

    number: int | None = Field(default=None, description='The decision number, D<n>')
    line: str = Field(default='', description='The ledger line as appended')
    path: str | None = Field(default=None, description='Absolute path of decisions.md')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was appended'
    )


def handoff_write(
    slug: str, kind: str, fields: HandoffFields | None = None
) -> HandoffWrite:
    """Write handoffs/SPRINT.md, REVIEW.md, or BATON.md for this ticket."""
    directory, refusals = ticket_directory(slug)
    if kind not in FILES:
        refusals.append(f'unknown kind {kind!r}; expected {", ".join(FILES)}')
    if directory is None or refusals:
        return HandoffWrite(kind=kind, refusals=refusals)

    read = ticket_read(slug)
    if read.ticket is None:
        return HandoffWrite(kind=kind, refusals=read.refusals)
    if kind == BATON:
        text, refusals = _render_baton(slug, directory, fields or HandoffFields())
    else:
        text, refusals = _render_pointers(slug, kind, read.ticket)
    if refusals:
        return HandoffWrite(kind=kind, refusals=refusals)

    path = directory.joinpath('handoffs', FILES[kind])
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return HandoffWrite(kind=kind, path=str(path), text=text)


def handoff_prompt(slug: str) -> HandoffPrompt:
    """Build the one-paragraph prompt that opens the next session on this handoff."""
    directory, refusals = ticket_directory(slug)
    if directory is None:
        return HandoffPrompt(refusals=refusals)
    read = ticket_read(slug)
    if read.ticket is None:
        return HandoffPrompt(refusals=read.refusals)

    handoff = _latest_handoff(directory)
    if handoff is None:
        return HandoffPrompt(refusals=[f'no handoff in {directory.joinpath("handoffs")}'])
    kind, path = handoff
    closing, refusals = _prompt_closing(kind, directory, read.ticket, path)
    if refusals:
        return HandoffPrompt(kind=kind, path=str(path), refusals=refusals)
    opening = (
        f'Read `{MIGHTYMODELS_DIR}/{slug}/ticket.yml`, then '
        f'`{MIGHTYMODELS_DIR}/{slug}/handoffs/{FILES[kind]}`, and invoke '
        '`using-mightymodels` before anything else.'
    )
    sentences = [opening, *_tracker_sentences(read.ticket), closing]
    return HandoffPrompt(kind=kind, path=str(path), prompt=' '.join(sentences))


def decision_record(
    slug: str, decision: str, options: list[str], chose: str, source: str
) -> DecisionWrite:
    """Append one decision to the ticket's decisions.md ledger."""
    directory, refusals = ticket_directory(slug)
    refusals.extend(
        missing_refusals({'decision': decision, 'chose': chose, 'source': source})
    )
    if not options:
        refusals.append('options is empty; a decision records what it chose between')
    if directory is None or refusals:
        return DecisionWrite(refusals=refusals)

    path = directory.joinpath(DECISIONS)
    lines = path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    if len(lines) >= DECISIONS_CAP:
        return DecisionWrite(
            refusals=[f'{DECISIONS} is {len(lines)} lines; the cap is {DECISIONS_CAP}']
        )
    number = _next_number(lines)
    line = (
        f'- D{number}: {decision} | options: {", ".join(options)} '
        f'| chose: {chose} ({source})'
    )
    with path.open('a', encoding='utf-8') as handle:
        handle.write(line + '\n')
    return DecisionWrite(number=number, line=line, path=str(path))


def _render_pointers(slug: str, kind: str, ticket: Ticket) -> tuple[str, list[str]]:
    """Render SPRINT.md or REVIEW.md: the skeleton, pointers, and the skill to invoke."""
    lines = _pointers(slug, ticket, pr=kind == REVIEW)
    if kind == REVIEW:
        lines.extend(REVIEW_LINES)
    else:
        ramp = _ramp(ticket)
        if ramp.ramp is None:
            return '', ramp.refusals
        lines.append(f'- Invoke the `{ramp.ramp}` skill and stop at its gate.')
    return SKELETON.format(slug=slug) + '\n' + '\n'.join(lines) + '\n', []


def _pointers(slug: str, ticket: Ticket, *, pr: bool) -> list[str]:
    docs = ticket.companion_docs
    lines = [f'- Read `{MIGHTYMODELS_DIR}/{slug}/ticket.yml` first.']
    if docs.issue_number:
        lines.append(f'- Read GitHub issue #{docs.issue_number}.')
    if docs.jira_key:
        lines.append(f'- Read Jira {docs.jira_key}.')
    if pr and docs.pr_number:
        lines.append(f'- Read PR #{docs.pr_number}.')
    return lines


def _render_baton(
    slug: str, directory: Path, fields: HandoffFields
) -> tuple[str, list[str]]:
    """Render BATON.md: the facts from this session that live nowhere else."""
    lines = [
        f'# Baton for {slug}',
        '',
        f'{FOCUS_PREFIX}{fields.focus}',
        _state(slug, directory),
        '',
        '## Settled this session',
        *bullets(fields.settled),
        '',
        '## Do not retry',
        *bullets(fields.do_not_retry),
        '',
        '## Works',
        *bullets(fields.works),
        '',
        '## Gotchas',
        *bullets(fields.gotchas),
        '',
        '## Parked',
        *bullets(fields.parked),
    ]
    text = '\n'.join(lines) + '\n'
    refusals = [
        *missing_refusals({'focus': fields.focus}),
        *cap_refusals(FILES[BATON], text, BATON_CAP),
    ]
    return text, refusals


def _state(slug: str, directory: Path) -> str:
    branch = git_output(['rev-parse', '--abbrev-ref', 'HEAD'], cwd=directory) or 'unknown'
    sha = git_output(['rev-parse', '--short', 'HEAD'], cwd=directory) or 'unknown'
    tree = (
        'clean' if git_output(['status', '--porcelain'], cwd=directory) == '' else 'dirty'
    )
    return f'State: branch {branch} at {sha}; in flight: {_in_flight(slug)}; tree {tree}'


def _in_flight(slug: str) -> str:
    """Name the first brief with an ASKED half and no DONE half, per baton-pass."""
    status = sprint_status(slug)
    task = next((task for task in status.tasks if task.asked and not task.done), None)
    if task is None:
        return 'none'
    return (
        f'{task.task_id} ({MIGHTYMODELS_DIR}/{slug}/briefs/{task.task_id}.md), '
        'DONE half absent'
    )


def _latest_handoff(directory: Path) -> tuple[str, Path] | None:
    for kind in PROMPT_ORDER:
        path = directory.joinpath('handoffs', FILES[kind])
        if path.is_file():
            return kind, path
    return None


def _prompt_closing(
    kind: str, directory: Path, ticket: Ticket, path: Path
) -> tuple[str, list[str]]:
    if kind == REVIEW:
        return 'Invoke `review-circus`.', []
    if kind == SPRINT:
        ramp = _ramp(ticket)
        if ramp.ramp is None:
            return '', ramp.refusals
        return f'Invoke the `{ramp.ramp}` skill and stop at its gate.', []
    focus = _focus(path)
    if not focus:
        return '', [f'{path} carries no {FOCUS_PREFIX.strip()} line']
    skill, refusals = _focus_skill(directory, ticket)
    if refusals:
        return '', refusals
    return f'The focus is "{focus}"; invoke `{skill}` for it.', []


def _focus(path: Path) -> str:
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith(FOCUS_PREFIX):
            return line.removeprefix(FOCUS_PREFIX).strip()
    return ''


def _focus_skill(directory: Path, ticket: Ticket) -> tuple[str, list[str]]:
    """A sprint with briefs continues under agents-assemble; a fresh one ramps."""
    if any(directory.joinpath('briefs').glob('task-*.md')):
        return 'agents-assemble', []
    ramp = _ramp(ticket)
    return ramp.ramp or '', ramp.refusals


def _tracker_sentences(ticket: Ticket) -> list[str]:
    docs = ticket.companion_docs
    sentences = []
    if docs.issue_number:
        sentences.append(f'The checklist is GitHub issue #{docs.issue_number}.')
    if docs.jira_key:
        sentences.append(f'The tracker item is Jira {docs.jira_key}.')
    return sentences


def _ramp(ticket: Ticket) -> RampChoice:
    handoff = ticket.handoff_context
    return route_ramp(handoff.scope, plan_first=handoff.plan_first)


def _next_number(lines: list[str]) -> int:
    numbers = [
        int(match.group(1)) for line in lines if (match := DECISION_NUMBER.match(line))
    ]
    return max(numbers, default=0) + 1
