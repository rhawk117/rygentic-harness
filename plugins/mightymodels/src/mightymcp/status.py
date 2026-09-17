from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

from mightymcp.attempts import attempts_by_task
from mightymcp.brief import brief_halves
from mightymcp.paths import TicketPathError, git_output, repo_root, ticket_dir

NO_UPSTREAM = -1


class TaskStatus(BaseModel):
    """Where one task stands, read from its brief and the attempts log."""

    task_id: str = Field(description='Brief stem, e.g. task-03')
    asked: bool = Field(description='True when the brief carries an ASKED half')
    done: bool = Field(description='True when the engineer appended the DONE half')
    verified: bool = Field(
        description='True when the scout appended the VERIFIED section'
    )
    commit: str | None = Field(default=None, description="The DONE half's commit hash")
    attempts: int = Field(description='Attempts logged for this task in attempts.jsonl')


class SprintStatus(BaseModel):
    """The sprint at a glance: one row per brief, plus the ticket-wide state."""

    slug: str = Field(description='The ticket this status is for')
    tasks: list[TaskStatus] = Field(default_factory=list, description='One row per brief')
    unpushed_commits: int = Field(
        default=NO_UPSTREAM,
        description='Commits ahead of upstream, or -1 with no upstream',
    )
    whats_broken_active: bool = Field(
        default=False, description='True while a whats-broken debug is live'
    )
    report_present: bool = Field(default=False, description='True once REPORT.md exists')
    refusals: list[str] = Field(
        default_factory=list, description='Why the status is empty'
    )


def sprint_status(slug: str) -> SprintStatus:
    """Report every task in a ticket, with unpushed commits and ticket-wide state."""
    try:
        root = repo_root()
        directory = ticket_dir(slug, root)
    except TicketPathError as err:
        return SprintStatus(slug=slug, refusals=[str(err)])
    if not directory.is_dir():
        return SprintStatus(slug=slug, refusals=[f'no ticket directory at {directory}'])

    attempts = attempts_by_task(directory.joinpath('attempts.jsonl'))
    briefs = sorted(directory.joinpath('briefs').glob('task-*.md'))
    return SprintStatus(
        slug=slug,
        tasks=[_task_status(brief, attempts) for brief in briefs],
        unpushed_commits=_unpushed_commits(root),
        whats_broken_active=directory.joinpath('whats-broken.md').is_file(),
        report_present=directory.joinpath('REPORT.md').is_file(),
    )


def render_status(status: SprintStatus) -> str:
    """Render a sprint status as one line per task, then the ticket-wide counters."""
    done = sum(1 for task in status.tasks if task.done)
    verified = sum(1 for task in status.tasks if task.verified)
    unpushed = (
        'no upstream'
        if status.unpushed_commits == NO_UPSTREAM
        else f'{status.unpushed_commits} unpushed'
    )
    summary = (
        f'{status.slug}: {len(status.tasks)} tasks, {done} done, {verified} verified, '
        f'{unpushed}, whats-broken {"yes" if status.whats_broken_active else "no"}, '
        f'report {"yes" if status.report_present else "no"}'
    )
    return '\n'.join([*(_status_line(task) for task in status.tasks), summary])


def _status_line(task: TaskStatus) -> str:
    halves = '/'.join(
        name
        for name, present in (
            ('asked', task.asked),
            ('done', task.done),
            ('verified', task.verified),
        )
        if present
    )
    return (
        f'{task.task_id}: {halves or "empty"}, {task.attempts} attempts, '
        f'commit {task.commit or "none"}'
    )


def _task_status(brief: Path, attempts: Counter[str]) -> TaskStatus:
    halves = brief_halves(brief.read_text(encoding='utf-8'))
    return TaskStatus(
        task_id=brief.stem,
        asked=halves.asked,
        done=halves.done,
        verified=halves.verified,
        commit=halves.commit,
        attempts=attempts[brief.stem],
    )


def _unpushed_commits(root: Path) -> int:
    count = git_output(['rev-list', '@{upstream}..HEAD', '--count'], cwd=root)
    if count is None or not count.isdigit():
        return NO_UPSTREAM
    return int(count)
