import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from mightymcp.artifacts import ALIASED
from mightymcp.paths import (
    MIGHTYMODELS_DIR,
    TicketPathError,
    git_output,
    repo_root,
    ticket_dir,
)
from mightymcp.routing import ModelChoice, Scope, choose_model, default_models

ISSUE_NUMBER = 'issue-number'
PR_NUMBER = 'pr-number'
COMPANION_KEYS = (ISSUE_NUMBER, PR_NUMBER)
CONTEXT_MIN = 3
CONTEXT_MAX = 6
CITATION = re.compile(r'\S+\.[A-Za-z0-9_]+:\d+')
IGNORE_LINE = f'{MIGHTYMODELS_DIR}/\n'


class CompanionDocs(BaseModel):
    """Tracker keys and triage reading, per the ticket schema's companion-docs block."""

    model_config = ALIASED

    issue_number: int | None = Field(default=None, description='GitHub issue number')
    jira_key: str | None = Field(default=None, description='Jira key, e.g. PROJ-123')
    pr_number: int | None = Field(
        default=None, description='Pull request number, once stick-the-landing opens it'
    )
    reference_urls: list[str] = Field(
        default_factory=list, description='External docs read during triage, never issues'
    )


class HandoffContext(BaseModel):
    """The answers that drive ramp and engineer-tier selection for the whole ticket."""

    model_config = ALIASED

    scope: Scope = Field(description='Ticket scope: sm, med, or large')
    plan_first: bool = Field(
        description='True when the user expects at least one compaction'
    )
    branch_name: str = Field(description='The branch the sprint runs on')
    worktrees_okay: bool = Field(
        default=False, description='Dormant until engineers run in parallel'
    )


class Ticket(BaseModel):
    """A ticket.yml file: the per-ticket source of truth every session reads first."""

    model_config = ALIASED

    task: str = Field(description='Slug, and the directory name under .mightymodels/')
    summary: str = Field(description='What the ticket is, in one sentence')
    triaged_at: datetime = Field(description='When the ticket was triaged')
    context: list[str] = Field(
        description='Triage rollup: 3-6 lines, no file:line citations'
    )
    companion_docs: CompanionDocs = Field(default_factory=CompanionDocs)
    subagent_models: dict[str, str | None] = Field(
        default_factory=dict, description='Per-role model pins, keyed by fleet role'
    )
    handoff_context: HandoffContext

    @field_validator('context', mode='before')
    @classmethod
    def _fold_prose(cls, value: Any) -> Any:
        """A context line carrying a colon parses as a mapping; fold it back to prose."""
        if not isinstance(value, list):
            return value
        return [_context_line(entry) for entry in value]


class TicketRead(BaseModel):
    """The parsed ticket, or the reasons it could not be read."""

    ticket: Ticket | None = Field(default=None, description='The parsed ticket.yml')
    refusals: list[str] = Field(
        default_factory=list, description='Why the read was refused'
    )


class TicketWrite(BaseModel):
    """The ticket as written, or the reasons nothing was written."""

    ticket: Ticket | None = Field(default=None, description='The ticket now on disk')
    path: str | None = Field(
        default=None, description='Absolute path of the written ticket.yml'
    )
    refusals: list[str] = Field(
        default_factory=list, description='Why the write was refused'
    )


def ticket_read(slug: str) -> TicketRead:
    """Read .mightymodels/<slug>/ticket.yml and return the parsed ticket."""
    try:
        path = ticket_dir(slug).joinpath('ticket.yml')
    except TicketPathError as err:
        return TicketRead(refusals=[str(err)])
    raw, refusals = _read_mapping(path)
    if raw is None:
        return TicketRead(refusals=refusals)
    ticket, refusals = _validate(raw, path)
    return TicketRead(ticket=ticket, refusals=refusals)


def ticket_create(
    slug: str,
    summary: str,
    context: list[str],
    handoff: HandoffContext,
    docs: CompanionDocs | None = None,
) -> TicketWrite:
    """Create .mightymodels/<slug>/ with ticket.yml, handoffs/, and briefs/."""
    try:
        root = repo_root()
        directory = ticket_dir(slug, root)
    except TicketPathError as err:
        return TicketWrite(refusals=[str(err)])
    refusals = context_refusals(context)
    if directory.exists():
        refusals.append(f'ticket {slug!r} already exists at {directory}')
    if refusals:
        return TicketWrite(refusals=refusals)

    ticket = Ticket(
        task=slug,
        summary=summary,
        triaged_at=datetime.now(UTC),
        context=list(context),
        companion_docs=docs or CompanionDocs(),
        subagent_models=default_models(handoff.scope),
        handoff_context=handoff,
    )
    ensure_ignored(root)
    directory.joinpath('handoffs').mkdir(parents=True)
    directory.joinpath('briefs').mkdir()
    path = directory.joinpath('ticket.yml')
    _write_yaml(path, ticket.model_dump(mode='json', by_alias=True))
    return TicketWrite(ticket=ticket, path=str(path))


def ticket_update_context(slug: str, context: list[str]) -> TicketWrite:
    """Replace the ticket's context rollup with 3-6 citation-free lines."""
    try:
        path = ticket_dir(slug).joinpath('ticket.yml')
    except TicketPathError as err:
        return TicketWrite(refusals=[str(err)])
    raw, refusals = _read_mapping(path)
    refusals.extend(context_refusals(context))
    if raw is None or refusals:
        return TicketWrite(refusals=refusals)

    raw['context'] = list(context)
    ticket, refusals = _validate(raw, path)
    if ticket is None:
        return TicketWrite(refusals=refusals)
    _write_yaml(path, raw)
    return TicketWrite(ticket=ticket, path=str(path))


def ticket_set_companion(slug: str, key: str, value: int) -> TicketWrite:
    """Set one companion-docs number, leaving every other field of the ticket as it is."""
    try:
        path = ticket_dir(slug).joinpath('ticket.yml')
    except TicketPathError as err:
        return TicketWrite(refusals=[str(err)])
    raw, refusals = _read_mapping(path)
    if key not in COMPANION_KEYS:
        refusals.append(
            f'unknown companion-docs key {key!r}; expected {", ".join(COMPANION_KEYS)}'
        )
    if raw is None or refusals:
        return TicketWrite(refusals=refusals)

    docs = raw.get('companion-docs')
    raw['companion-docs'] = (docs if isinstance(docs, dict) else {}) | {key: value}
    ticket, refusals = _validate(raw, path)
    if ticket is None:
        return TicketWrite(refusals=refusals)
    _write_yaml(path, raw)
    return TicketWrite(ticket=ticket, path=str(path))


def resolve_model(role: str, slug: str | None = None) -> ModelChoice:
    """Resolve a fleet role's model: the ticket's pin when set, else the default."""
    if slug is None:
        return choose_model(role, pinned=None, scope=None)
    read = ticket_read(slug)
    if read.ticket is None:
        return ModelChoice(role=role, source='none', refusals=read.refusals)
    return choose_model(
        role,
        pinned=read.ticket.subagent_models.get(role),
        scope=read.ticket.handoff_context.scope,
    )


def context_refusals(context: list[str]) -> list[str]:
    """Return why this context rollup is not writable: wrong length, or citations."""
    refusals = []
    if not CONTEXT_MIN <= len(context) <= CONTEXT_MAX:
        refusals.append(
            f'context is {len(context)} lines; the schema allows '
            f'{CONTEXT_MIN}-{CONTEXT_MAX}'
        )
    refusals.extend(
        f'context line {number} carries a file:line citation: {line!r}'
        for number, line in enumerate(context, start=1)
        if CITATION.search(line)
    )
    return refusals


def ensure_ignored(root: Path) -> None:
    """Add .mightymodels/ to .git/info/exclude unless git already ignores it."""
    if git_output(['check-ignore', '-q', MIGHTYMODELS_DIR], cwd=root) is not None:
        return
    exclude = root.joinpath('.git', 'info', 'exclude')
    if exclude.is_file() and IGNORE_LINE in exclude.read_text(encoding='utf-8'):
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open('a', encoding='utf-8') as handle:
        handle.write(IGNORE_LINE)


def _context_line(entry: Any) -> Any:
    """Render one context entry as the prose line it was written as."""
    if isinstance(entry, dict) and len(entry) == 1:
        key, value = next(iter(entry.items()))
        return f'{key}: {value}'
    if isinstance(entry, dict | list):
        return entry
    return str(entry)


def _read_mapping(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, [f'no ticket.yml at {path}']
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as err:
        return None, [f'{path} is not valid YAML: {err}']
    if not isinstance(raw, dict):
        return None, [f'{path} is not a YAML mapping']
    return raw, []


def _validate(raw: dict[str, Any], path: Path) -> tuple[Ticket | None, list[str]]:
    try:
        return Ticket.model_validate(raw), []
    except ValidationError as err:
        return None, [f'{path} does not match the ticket schema: {err}']


def _write_yaml(path: Path, mapping: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(mapping, sort_keys=False, allow_unicode=True), encoding='utf-8'
    )
