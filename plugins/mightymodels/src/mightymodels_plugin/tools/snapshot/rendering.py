"""The Markdown of a snapshot: a header, one bulleted section per part of the record, the review.

A section with nothing to show says so in one line, so a reader can tell an empty section from a
missing one. Warnings get a section only when there are any.
"""

from collections.abc import Iterable

from mightymodels_plugin.head import short_head
from mightymodels_plugin.tools.snapshot.schema import (
    CheckState,
    FailedAttempt,
    LedgerLine,
    PassingCommand,
    ReviewDecision,
    ReviewState,
    SnapshotRecord,
    TaskState,
)


def bullet_lines(items: Iterable[str], empty: str) -> list[str]:
    lines = [f'- {item}' for item in items]
    return lines or [f'- {empty}']


def section_lines(title: str, items: Iterable[str], *, empty: str) -> list[str]:
    return ['', f'## {title}', '', *bullet_lines(items, empty)]


def tree_text(dirty_count: int | None) -> str:
    if dirty_count is None:
        return 'unknown'
    return 'clean' if dirty_count == 0 else f'{dirty_count} changed'


def header_lines(record: SnapshotRecord) -> list[str]:
    repository = record.repository
    branch = 'detached' if repository.branch is None else repository.branch
    return [
        f'# Snapshot for {record.slug}',
        '',
        f'Generated {record.generated_at} from durable files only.',
        f'Ticket: {record.ticket.summary} (status {record.ticket.status}).',
        (
            f'Repository: {branch} at {short_head(repository.head)}; '
            f'tree {tree_text(repository.dirty_count)}.'
        ),
        *(f'- changed: {path}' for path in repository.dirty),
    ]


def task_line(task: TaskState) -> str:
    attempts = ', '.join(f'{worker} {count}' for worker, count in task.attempts.items())
    detail = ' | '.join(part for part in (attempts, '; '.join(task.reasons)) if part)
    return f'{task.task} {task.status}' + (f' ({detail})' if detail else '')


def check_line(check: CheckState) -> str:
    return f'{check.id} {check.state}'


def passing_command_line(command: PassingCommand) -> str:
    return f'{command.id}: `{" ".join(command.argv)}`'


def ledger_line(line: LedgerLine) -> str:
    cite = '' if line.cite is None else f' [{line.cite}]'
    return f'{line.text}{cite} ({line.origin})'


def failed_attempt_line(attempt: FailedAttempt) -> str:
    return f'{attempt.task} {attempt.to} at {attempt.head}: {attempt.reason}'


def review_decision_line(decided: ReviewDecision) -> str:
    return f'- {decided.finding} {decided.decision}: {decided.reason or "no reason"}'


def review_lines(review: ReviewState | None) -> list[str]:
    if review is None:
        return ['- no review run']
    return [
        f'- run {review.run} ({review.depth}) at {review.head}: {review.findings} findings',
        f'- undecided: {", ".join(review.undecided) or "none"}',
        f'- remediation open: {", ".join(review.remediation_open) or "none"}',
        *map(review_decision_line, review.decisions),
    ]


def warning_lines(warnings: Iterable[str]) -> list[str]:
    lines = [f'- {warning}' for warning in warnings]
    return ['', '## Warnings', '', *lines] if lines else []


def snapshot_markdown(record: SnapshotRecord) -> str:
    lines = [
        *header_lines(record),
        *section_lines('Tasks', map(task_line, record.tasks), empty='none started'),
        *section_lines('Checks at HEAD', map(check_line, record.checks), empty='no contract'),
        *section_lines(
            'Works', map(passing_command_line, record.works), empty='no passing command yet'
        ),
        *section_lines('Decisions', map(ledger_line, record.decisions), empty='none recorded'),
        *section_lines(
            'Open questions', map(ledger_line, record.open_questions), empty='none recorded'
        ),
        *section_lines(
            'Do not retry',
            map(failed_attempt_line, record.do_not_retry),
            empty='no failed attempt recorded',
        ),
        *section_lines('Answers', record.answers, empty='no recorded answers'),
        *section_lines('Subagents', record.subagents, empty='no receipts yet'),
        *('', '## Review', ''),
        *review_lines(record.review),
        *warning_lines(record.warnings),
    ]
    return '\n'.join(lines) + '\n'
