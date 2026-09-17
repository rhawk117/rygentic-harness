import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from mightymcp.artifacts import NONE_ITEM, cap_refusals, ticket_directory
from mightymcp.paths import TicketPathError, repo_root
from mightymcp.report import REPORT
from mightymcp.status import NO_UPSTREAM, SprintStatus, sprint_status
from mightymcp.ticket import ticket_read

OPEN_THREADS = 'open threads:'
UNCHECKED_BOX = '- [ ]'
ARCHIVES_DIR = 'archives'
# prune-ticket sets the archive cap; pre_write_edit holds it for hand-written ones
ARCHIVE_CAP = 30

# How prunable reads an issue checklist: the number in, the body out, None when it
# could not be read. The gh gateway below is the default; a caller may pass its own.
IssueReader = Callable[[int], str | None]


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


class ArchiveWrite(BaseModel):
    """The archive as written, or why nothing was written."""

    path: str | None = Field(default=None, description='Absolute path of the archive')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was written'
    )


class PruneDelete(BaseModel):
    """The ticket directory as deleted, or why it is still there."""

    path: str | None = Field(default=None, description='The directory that was deleted')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was deleted'
    )


def _gh_issue_body(number: int) -> str | None:
    """Read the issue body through gh in the repository; a failing gh reads as None."""
    try:
        proc = subprocess.run(  # noqa: S603 -- argv list built here, never a shell string
            ['gh', 'issue', 'view', str(number), '--json', 'body', '-q', '.body'],  # noqa: S607
            cwd=repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError, TicketPathError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def prunable(slug: str, *, read_issue: IssueReader = _gh_issue_body) -> PruneCheck:
    """Report whether .mightymodels/<slug> is safe to delete, per prune-ticket."""
    directory, refusals = ticket_directory(slug)
    status = sprint_status(slug)
    refusals.extend(status.refusals)
    if directory is None or refusals:
        return PruneCheck(slug=slug, refusals=refusals)

    issue_reasons, skipped = _issue_reasons(slug, read_issue)
    reasons = [
        *_thread_reasons(directory),
        *_broken_reasons(status),
        *_commit_reasons(status),
        *issue_reasons,
    ]
    return PruneCheck(slug=slug, prunable=not reasons, reasons=reasons, skipped=skipped)


def ticket_prunable(slug: str) -> PruneCheck:
    """Report the live work that blocks pruning this ticket, or that nothing does."""
    return prunable(slug)


def ticket_archive(slug: str, body: str) -> ArchiveWrite:
    """Write the archive that outlives the ticket directory, per prune-ticket."""
    directory, refusals = ticket_directory(slug)
    if directory is None:
        return ArchiveWrite(refusals=refusals)

    path = _archive_path(directory)
    refusals.extend(cap_refusals('the archive', body, ARCHIVE_CAP))
    if path.exists():
        refusals.append(f'{path} already exists; a ticket is archived once')
    if refusals:
        return ArchiveWrite(refusals=refusals)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')
    return ArchiveWrite(path=str(path))


def prune_ticket(
    slug: str,
    *,
    accept_skipped: bool = False,
    read_issue: IssueReader = _gh_issue_body,
) -> PruneDelete:
    """Delete .mightymodels/<slug>, once it is archived and nothing live is left in it."""
    directory, refusals = ticket_directory(slug)
    if directory is None:
        return PruneDelete(refusals=refusals)

    check = prunable(slug, read_issue=read_issue)
    refusals.extend(check.refusals)
    refusals.extend(check.reasons)
    archive = _archive_path(directory)
    if not archive.is_file():
        refusals.append(f'no archive at {archive}; the archive is written first')
    if check.skipped and not accept_skipped:
        refusals.append(
            f'{len(check.skipped)} checks did not run ({"; ".join(check.skipped)}); '
            'the delete is unrecoverable, so pass accept_skipped to take it anyway'
        )
    if refusals:
        return PruneDelete(refusals=refusals)

    shutil.rmtree(directory)
    return PruneDelete(path=str(directory))


def ticket_delete(slug: str, *, accept_skipped: bool = False) -> PruneDelete:
    """Delete a ticket directory; a check that could not run blocks it until accepted."""
    return prune_ticket(slug, accept_skipped=accept_skipped)


def _archive_path(directory: Path) -> Path:
    """Return the archive beside the vetted ticket directory: archives/<slug>.md."""
    return directory.parent.joinpath(ARCHIVES_DIR, f'{directory.name}.md')


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


def _issue_reasons(slug: str, read_issue: IssueReader) -> tuple[list[str], list[str]]:
    read = ticket_read(slug)
    number = read.ticket.companion_docs.issue_number if read.ticket else None
    if number is None:
        return [], ['the ticket names no issue; the checklist was not read']
    body = read_issue(number)
    if body is None:
        return [], [f'gh could not read issue #{number}; the checklist was not read']
    boxes = [line for line in body.splitlines() if line.strip().startswith(UNCHECKED_BOX)]
    if not boxes:
        return [], []
    return [f'issue #{number} has {len(boxes)} unchecked boxes'], []
