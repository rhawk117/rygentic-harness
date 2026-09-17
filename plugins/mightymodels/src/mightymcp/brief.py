import re
from pathlib import Path

from pydantic import BaseModel, Field

from mightymcp.artifacts import (
    ALIASED,
    bracket_list,
    cap_refusals,
    parse_bracket_list,
    parse_fields,
    ticket_directory,
)
from mightymcp.paths import MIGHTYMODELS_DIR, git_output

TASK_ID = re.compile(r'^task-\d{2,}$')
BRIEF_CAP = 80
DONE_CAP = 65
# contracts.md refuses these at write time: an uncheckable AC makes verification theater
PLACEHOLDERS = (
    'works correctly',
    'handles errors appropriately',
    'consistent with the rest',
)
ASKED_HEADING = '## ASKED'
DONE_HEADING = '## DONE'
VERIFIED_HEADING = '## VERIFIED'
HEADINGS = (ASKED_HEADING, DONE_HEADING, VERIFIED_HEADING)
ASKED_KEYS = (
    'objective',
    'acceptance',
    'verification',
    'files-in-scope',
    'engineer-tier',
    'uses',
    'do-not',
)
DONE_KEYS = ('what', 'commit', 'diff-summary', 'commands-run')
REQUIRED_ASKED = ASKED_KEYS[:5]
DISPATCH = (
    '<objective>Execute the task specified in the ASKED stanza below. Brief path: '
    '{path} — append your ## DONE section there before reporting (≤{cap} lines).'
    '</objective>\n\n{stanza}\n<constraints>Commit when done with message '
    '"{message}".{push}</constraints>\n'
)
PUSH_CLAUSE = ' push after committing.'


class AskedStanza(BaseModel):
    """The ASKED half of a brief: what the engineer is asked to do, per contracts.md."""

    model_config = ALIASED

    objective: str = Field(description='One sentence: what and why')
    acceptance: list[str] = Field(
        description='Checkable criteria, one per line, e.g. "AC-1: <command>"'
    )
    verification: str = Field(description='The verification commands, in order')
    files_in_scope: list[str] = Field(description='The paths this task owns')
    engineer_tier: str = Field(
        description='Model from ticket.yml, or a bump carrying its reason'
    )
    uses: list[str] = Field(
        default_factory=list, description='Repository skills or instruction files'
    )
    do_not: str = Field(default='', description='What this task must leave alone')


class DoneHalf(BaseModel):
    """The DONE half the engineer appends once the task is committed."""

    model_config = ALIASED

    what: str = Field(description='What was done')
    commit: str = Field(description='The commit hash the work landed in')
    diff_summary: str = Field(description='The diff in one paragraph')
    commands_run: str = Field(description='Verification commands and observed results')


class BriefOpen(BaseModel):
    """A brief's ASKED half as written, plus the dispatch that carries it."""

    path: str | None = Field(default=None, description='Absolute path of the brief')
    stanza: str = Field(default='', description='The ASKED half as written')
    dispatch: str = Field(default='', description='The rendered engineer dispatch')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was written'
    )


class BriefWrite(BaseModel):
    """The brief as it now stands on disk, or why nothing was appended."""

    path: str | None = Field(default=None, description='Absolute path of the brief')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was written'
    )


class BriefHalves(BaseModel):
    """Which halves a brief carries, whether or not either one is complete."""

    asked: bool = Field(description='True when the brief carries an ASKED half')
    done: bool = Field(description='True when the brief carries a DONE half')
    verified: bool = Field(description='True when the scout appended ## VERIFIED')
    commit: str | None = Field(default=None, description="The DONE half's commit hash")


class BriefRead(BaseModel):
    """A brief parsed back into its halves, with the verification flag."""

    task_id: str = Field(description='Brief stem, e.g. task-03')
    path: str | None = Field(default=None, description='Absolute path of the brief')
    asked: AskedStanza | None = Field(default=None, description='The ASKED half')
    done: DoneHalf | None = Field(default=None, description='The DONE half')
    verified: bool = Field(
        default=False, description='True when the scout appended ## VERIFIED'
    )
    refusals: list[str] = Field(
        default_factory=list, description='Why the brief could not be read'
    )


def brief_open(
    slug: str,
    task_id: str,
    asked: AskedStanza,
    commit_message: str,
    *,
    push: bool = False,
) -> BriefOpen:
    """Write the ASKED half of briefs/<task_id>.md and render the engineer dispatch."""
    directory, refusals = ticket_directory(slug)
    refusals.extend(task_id_refusals(task_id))
    refusals.extend(_asked_refusals(asked))
    stanza = render_asked(asked)
    refusals.extend(cap_refusals('the ASKED stanza', stanza, BRIEF_CAP))
    if directory is None or refusals:
        return BriefOpen(refusals=refusals)

    path = directory.joinpath('briefs', f'{task_id}.md')
    if path.is_file() and ASKED_HEADING in _halves(path.read_text(encoding='utf-8')):
        return BriefOpen(refusals=[f'{path} already carries an ASKED half'])
    path.parent.mkdir(exist_ok=True)
    path.write_text(stanza, encoding='utf-8')
    return BriefOpen(
        path=str(path),
        stanza=stanza,
        dispatch=DISPATCH.format(
            path=f'{MIGHTYMODELS_DIR}/{slug}/briefs/{task_id}.md',
            cap=DONE_CAP,
            stanza=stanza,
            message=commit_message,
            push=PUSH_CLAUSE if push else '',
        ),
    )


def brief_append_done(slug: str, task_id: str, done: DoneHalf) -> BriefWrite:
    """Append the DONE half to briefs/<task_id>.md, under the caps contracts.md sets."""
    directory, refusals = ticket_directory(slug)
    refusals.extend(task_id_refusals(task_id))
    if directory is None or refusals:
        return BriefWrite(refusals=refusals)

    path = directory.joinpath('briefs', f'{task_id}.md')
    if not path.is_file():
        return BriefWrite(refusals=[f'no brief at {path}'])
    text = path.read_text(encoding='utf-8')
    halves = _halves(text)
    half = render_done(done)
    brief = f'{text.rstrip("\n")}\n\n{half}'
    refusals = [
        *([] if ASKED_HEADING in halves else [f'{path} has no ASKED half']),
        *([f'{path} already carries a DONE half'] if DONE_HEADING in halves else []),
        *_commit_refusals(done.commit, directory),
        *cap_refusals('the DONE half', half, DONE_CAP),
        *cap_refusals('the brief', brief, BRIEF_CAP),
    ]
    if refusals:
        return BriefWrite(refusals=refusals)
    path.write_text(brief, encoding='utf-8')
    return BriefWrite(path=str(path))


def brief_read(slug: str, task_id: str) -> BriefRead:
    """Read briefs/<task_id>.md back: both halves parsed, plus the verified flag."""
    directory, refusals = ticket_directory(slug)
    refusals.extend(task_id_refusals(task_id))
    if directory is None or refusals:
        return BriefRead(task_id=task_id, refusals=refusals)

    path = directory.joinpath('briefs', f'{task_id}.md')
    if not path.is_file():
        return BriefRead(task_id=task_id, refusals=[f'no brief at {path}'])
    halves = _halves(path.read_text(encoding='utf-8'))
    asked, refusals = _parse_asked(halves.get(ASKED_HEADING), path)
    done, done_refusals = _parse_done(halves.get(DONE_HEADING), path)
    return BriefRead(
        task_id=task_id,
        path=str(path),
        asked=asked,
        done=done,
        verified=VERIFIED_HEADING in halves,
        refusals=[*refusals, *done_refusals],
    )


def brief_halves(text: str) -> BriefHalves:
    """Report which halves a brief carries and the commit its DONE half names."""
    halves = _halves(text)
    done = halves.get(DONE_HEADING)
    return BriefHalves(
        asked=ASKED_HEADING in halves,
        done=done is not None,
        verified=VERIFIED_HEADING in halves,
        commit=parse_fields('\n'.join(done or []), DONE_KEYS).get('commit') or None,
    )


def asked_half(text: str) -> str:
    """Return a brief's ASKED half as written, or '' when the text carries none."""
    return '\n'.join(_halves(text).get(ASKED_HEADING, []))


def render_asked(asked: AskedStanza) -> str:
    """Render the ASKED stanza in the shape contracts.md specifies."""
    lines = [ASKED_HEADING, f'objective: {asked.objective}', 'acceptance:']
    lines.extend(f'  - {criterion}' for criterion in asked.acceptance)
    lines.extend((
        f'verification: {asked.verification}',
        f'files-in-scope: {bracket_list(asked.files_in_scope)}',
        f'engineer-tier: {asked.engineer_tier}',
        f'uses: {bracket_list(asked.uses)}',
        f'do-not: {asked.do_not}',
    ))
    return '\n'.join(lines) + '\n'


def render_done(done: DoneHalf) -> str:
    """Render the DONE half in the shape contracts.md specifies."""
    return (
        f'{DONE_HEADING}\n'
        f'what: {done.what}\n'
        f'commit: {done.commit}\n'
        f'diff-summary: {done.diff_summary}\n'
        f'commands-run: {done.commands_run}\n'
    )


def task_id_refusals(task_id: str) -> list[str]:
    """Refuse anything that is not a task-NN brief stem."""
    if TASK_ID.match(task_id):
        return []
    return [f'task id {task_id!r} is not task-NN']


def _asked_refusals(asked: AskedStanza) -> list[str]:
    refusals = [
        f'acceptance criterion {number} is a placeholder: {criterion!r}'
        for number, criterion in enumerate(asked.acceptance, start=1)
        if any(phrase in criterion.casefold() for phrase in PLACEHOLDERS)
    ]
    if not asked.acceptance:
        refusals.append('acceptance is empty; contracts.md wants at least one criterion')
    if not asked.files_in_scope:
        refusals.append('files-in-scope is empty; a task owns the paths it may write')
    return refusals


def _commit_refusals(commit: str, directory: Path) -> list[str]:
    if git_output(['cat-file', '-e', f'{commit}^{{commit}}'], cwd=directory) is None:
        return [f'commit {commit!r} is not a commit in this repository']
    return []


def _halves(text: str) -> dict[str, list[str]]:
    halves: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        heading = line.strip()
        if heading in HEADINGS:
            current = halves.setdefault(heading, [])
        elif current is not None:
            current.append(line)
    return halves


def _parse_asked(
    block: list[str] | None, path: Path
) -> tuple[AskedStanza | None, list[str]]:
    if block is None:
        return None, [f'{path} has no ASKED half']
    fields = parse_fields('\n'.join(block), ASKED_KEYS)
    missing = [key for key in REQUIRED_ASKED if not fields.get(key)]
    if missing:
        return None, [f'the ASKED half of {path} is missing {", ".join(missing)}']
    return AskedStanza(
        objective=fields['objective'],
        acceptance=_items(fields['acceptance']),
        verification=fields['verification'],
        files_in_scope=parse_bracket_list(fields['files-in-scope']),
        engineer_tier=fields['engineer-tier'],
        uses=parse_bracket_list(fields.get('uses', '')),
        do_not=fields.get('do-not', ''),
    ), []


def _parse_done(block: list[str] | None, path: Path) -> tuple[DoneHalf | None, list[str]]:
    if block is None:
        return None, []
    fields = parse_fields('\n'.join(block), DONE_KEYS)
    missing = [key for key in DONE_KEYS if not fields.get(key)]
    if missing:
        return None, [f'the DONE half of {path} is missing {", ".join(missing)}']
    return DoneHalf(
        what=fields['what'],
        commit=fields['commit'],
        diff_summary=fields['diff-summary'],
        commands_run=fields['commands-run'],
    ), []


def _items(block: str) -> list[str]:
    return [
        line.strip().removeprefix('- ') for line in block.splitlines() if line.strip()
    ]
