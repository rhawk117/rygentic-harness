import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from mightymcp.artifacts import NONE_ITEM, ticket_directory
from mightymcp.report import REPORT
from mightymcp.status import NO_UPSTREAM, SprintStatus, sprint_status
from mightymcp.ticket import ticket_read

OPEN_THREADS = 'open threads:'
UNCHECKED_BOX = '- [ ]'


class PruneCheck(BaseModel):
    """Whether a ticket directory may be deleted, and what live work is still in it."""

    slug: str = Field(description='The ticket the check ran against')
    prunable: bool = Field(
        default=False, description='True when nothing live blocks deletion'
    )
    reasons: list[str] = Field(
        default_factory=list, description='The live work prune-ticket refuses on'
    )
    skipped: list[str] = Field(
        default_factory=list, description='Checks that could not be run'
    )
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was checked'
    )


def prunable(slug: str) -> PruneCheck:
    """Report whether .mightymodels/<slug> is safe to delete, per prune-ticket."""
    directory, refusals = ticket_directory(slug)
    status = sprint_status(slug)
    refusals.extend(status.refusals)
    if directory is None or refusals:
        return PruneCheck(slug=slug, refusals=refusals)

    issue_reasons, skipped = _issue_reasons(slug, directory)
    reasons = [
        *_thread_reasons(directory),
        *_broken_reasons(status),
        *_commit_reasons(status),
        *issue_reasons,
    ]
    return PruneCheck(slug=slug, prunable=not reasons, reasons=reasons, skipped=skipped)


def _thread_reasons(directory: Path) -> list[str]:
    report = directory.joinpath(REPORT)
    if not report.is_file():
        return []
    threads = _threads(report.read_text(encoding='utf-8'))
    if not threads:
        return []
    return [f'{REPORT} still lists {len(threads)} open threads: {"; ".join(threads)}']


def _threads(text: str) -> list[str]:
    lines = text.splitlines()
    if OPEN_THREADS not in lines:
        return []
    block = lines[lines.index(OPEN_THREADS) + 1 :]
    return [
        line.removeprefix('- ').strip()
        for line in block
        if line.startswith('- ') and line.strip() != NONE_ITEM
    ]


def _broken_reasons(status: SprintStatus) -> list[str]:
    if not status.whats_broken_active:
        return []
    return ['whats-broken.md is still active; the debug is live']


def _commit_reasons(status: SprintStatus) -> list[str]:
    if status.unpushed_commits in (NO_UPSTREAM, 0):
        return []
    return [f'the branch is ahead of its upstream by {status.unpushed_commits}']


def _issue_reasons(slug: str, directory: Path) -> tuple[list[str], list[str]]:
    read = ticket_read(slug)
    number = read.ticket.companion_docs.issue_number if read.ticket else None
    if number is None:
        return [], ['the ticket names no issue; the checklist was not read']
    body = _issue_body(number, directory)
    if body is None:
        return [], [f'gh could not read issue #{number}; the checklist was not read']
    boxes = [line for line in body.splitlines() if line.strip().startswith(UNCHECKED_BOX)]
    if not boxes:
        return [], []
    return [f'issue #{number} has {len(boxes)} unchecked boxes'], []


def _issue_body(number: int, cwd: Path) -> str | None:
    """Read the issue body through gh; an unavailable or failing gh reads as None."""
    try:
        proc = subprocess.run(  # noqa: S603 -- argv list built here, never a shell string
            ['gh', 'issue', 'view', str(number), '--json', 'body', '-q', '.body'],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None
