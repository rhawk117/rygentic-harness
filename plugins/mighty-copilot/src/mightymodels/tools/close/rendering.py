"""The Markdown of an archive: what a closed ticket shipped, in a fixed and bounded set of lines.

Each part of the record is one line, the decisions and the gotchas are bulleted under their own
line and capped, and the last line names the JSON record beside the archive. The decisions are the
linked ledgers' first and the review's reasons after, as many as the cap leaves room for. The
longest archive is well under `ARCHIVE_LINES`.
"""

from collections.abc import Mapping, Sequence
from itertools import islice

from mightymodels.core.workspace import ARCHIVES_DIRECTORY
from mightymodels.head import short_head
from mightymodels.tools.close.schema import (
    ArchivedCommand,
    ArchivedReview,
    ArchivedTask,
    ArchiveRecord,
    WorkerRuns,
)
from mightymodels.tools.contract.schema import Outcome
from mightymodels.tools.snapshot.rendering import bullet_lines
from mightymodels.tools.ticket.schema import Tracker

ARCHIVE_LINES = 30
DECISION_LIMIT = 4
DATE_LENGTH = 10
NONE_RECORDED = 'none recorded'


def tracker_text(tracker: Tracker) -> str:
    issue = '' if tracker.issue is None else f'#{tracker.issue}'
    jira = '' if tracker.jira is None else tracker.jira
    return ' '.join(part for part in (issue, jira) if part) or 'none'


def shipped_line(record: ArchiveRecord) -> str:
    parts = (
        f'shipped: {record.shipped}',
        f'PR: {"none" if record.pr is None else record.pr}',
        f'tracker: {tracker_text(record.tracker)}',
        f'pruned: {record.closed_at[:DATE_LENGTH]}',
        f'head: {short_head(record.head)}',
    )
    return ' · '.join(parts)


def attempts_text(attempts: Mapping[str, int]) -> str:
    return ', '.join(f'{worker} {count}' for worker, count in attempts.items())


def tasks_line(tasks: Mapping[str, ArchivedTask]) -> str:
    shown = '; '.join(
        f'{task_id} ({attempts_text(task.attempts)})' for task_id, task in tasks.items()
    )
    return f'tasks: {shown or NONE_RECORDED}'


def checks_line(verification: Sequence[ArchivedCommand]) -> str:
    not_passing = [command.id for command in verification if command.outcome != Outcome.PASSED]
    passing = len(verification) - len(not_passing)
    tail = f'; not passing: {", ".join(not_passing)}' if not_passing else ''
    return f'checks: {len(verification)} contract commands, {passing} passing at last run{tail}'


def review_line(review: ArchivedReview | None) -> str:
    if review is None:
        return 'review: none'
    decided = '; '.join(
        f'{decision} {", ".join(finding_ids)}'
        for decision, finding_ids in review.by_decision.items()
    )
    run = f'run {review.run} ({review.depth})'
    return f'review: {run}, {review.findings} findings; {decided or "no decisions"}'


def worker_runs_line(agents: WorkerRuns) -> str:
    detail = ', '.join(f'{status} {count}' for status, count in agents.by_status.items())
    return f'agents: {agents.runs} runs' + (f' ({detail})' if detail else '')


def decision_lines(record: ArchiveRecord) -> list[str]:
    decided = [f'{decision.text} ({decision.origin})' for decision in record.decisions]
    reasons = {} if record.review is None else record.review.reasons
    reviewed = (f'review {finding_id}: {reason}' for finding_id, reason in reasons.items())
    accepted = islice(reviewed, DECISION_LIMIT - len(decided))
    return bullet_lines([*decided, *accepted], NONE_RECORDED)


def archive_markdown(record: ArchiveRecord, record_name: str) -> str:
    lines = [
        f'# {record.slug}',
        shipped_line(record),
        tasks_line(record.tasks),
        checks_line(record.verification),
        review_line(record.review),
        worker_runs_line(record.agents),
        f'answers: {record.answers.recorded} recorded through ask_user',
        'decisions:',
        *decision_lines(record),
        'gotchas:',
        *bullet_lines(record.gotchas, NONE_RECORDED),
        f'details: {ARCHIVES_DIRECTORY}/{record_name}',
    ]
    return '\n'.join(lines) + '\n'
