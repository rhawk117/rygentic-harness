import json
from collections import Counter
from pathlib import Path
from typing import Any

from mightymcp.attempts import AttemptRecord, attempts_by_task, task_record_attempt


def record(kind: str, outcome: str = 'fail', check: str | None = None) -> AttemptRecord:
    return task_record_attempt('demo', 'task-01', kind, outcome, check)


def log_lines(ticket_root: Path) -> list[dict[str, Any]]:
    text = ticket_root.joinpath('attempts.jsonl').read_text(encoding='utf-8')
    return [json.loads(line) for line in text.splitlines()]


def test_one_attempt_is_one_json_line(ticket_root: Path) -> None:
    logged = task_record_attempt('demo', 'task-01', 'ci', 'fail', 'lint')

    assert logged.refusals == []
    assert logged.path == str(ticket_root.joinpath('attempts.jsonl'))
    (entry,) = log_lines(ticket_root)
    assert entry['task_id'] == 'task-01'
    assert entry['kind'] == 'ci'
    assert entry['outcome'] == 'fail'
    assert entry['check'] == 'lint'
    assert entry['ts'].endswith('+00:00')


def test_attempts_accumulate_across_kinds(ticket_root: Path) -> None:
    record('verification', 'pass')
    logged = record('fix')

    assert logged.attempts == 2
    assert logged.failures == 1
    assert len(log_lines(ticket_root)) == 2


def test_a_passing_attempt_never_escalates(ticket_root: Path) -> None:
    record('verification')
    logged = record('verification', 'pass')

    assert logged.escalate_to is None
    assert logged.rule == ''


def test_the_second_failed_verification_routes_to_whats_broken(
    ticket_root: Path,
) -> None:
    assert record('verification').escalate_to is None

    logged = record('verification')

    assert logged.escalate_to == 'whats-broken'
    assert logged.rule == 'second failed verification of task-01'


def test_the_second_failed_budgetron_round_routes_to_the_engineer(
    ticket_root: Path,
) -> None:
    assert record('budgetron').escalate_to is None

    assert record('budgetron').escalate_to == 'engineer'


def test_the_third_failed_fix_stops(ticket_root: Path) -> None:
    assert record('fix').escalate_to is None
    assert record('fix').escalate_to is None

    logged = record('fix')

    assert logged.escalate_to == 'stop'
    assert logged.failures == 3


def test_ci_failures_are_counted_per_check(ticket_root: Path) -> None:
    assert record('ci', check='lint').escalate_to is None
    assert record('ci', check='tests').escalate_to is None

    logged = record('ci', check='lint')

    assert logged.escalate_to == 'stop'
    assert logged.rule == 'second failed ci run of check lint'
    assert logged.failures == 2


def test_an_unknown_kind_or_outcome_is_refused(ticket_root: Path) -> None:
    logged = task_record_attempt('demo', 'task-01', 'vibes', 'maybe')

    assert logged.escalate_to is None
    assert logged.refusals == [
        "unknown kind 'vibes'; expected verification, budgetron, fix, ci",
        "unknown outcome 'maybe'; expected pass, fail",
    ]
    assert not ticket_root.joinpath('attempts.jsonl').exists()


def test_a_task_id_that_is_not_task_nn_is_refused(ticket_root: Path) -> None:
    logged = task_record_attempt('demo', 'task-1', 'fix', 'fail')

    assert logged.refusals == ["task id 'task-1' is not task-NN"]
    assert not ticket_root.joinpath('attempts.jsonl').exists()


def test_a_missing_ticket_is_refused(repo: Path) -> None:
    logged = task_record_attempt('demo', 'task-01', 'fix', 'fail')

    assert logged.refusals[0].startswith('no ticket directory at')


def test_a_log_line_that_is_not_json_is_skipped(ticket_root: Path) -> None:
    ticket_root.joinpath('attempts.jsonl').write_text('not json\n', encoding='utf-8')

    logged = record('verification')

    assert logged.attempts == 1
    assert logged.escalate_to is None


def test_attempts_by_task_counts_every_task_and_skips_junk(ticket_root: Path) -> None:
    log = ticket_root.joinpath('attempts.jsonl')
    log.write_text(
        '\n'.join([
            json.dumps({'task_id': 'task-01', 'outcome': 'fail'}),
            json.dumps({'task_id': 'task-01', 'outcome': 'pass'}),
            json.dumps({'task_id': 'task-02', 'outcome': 'fail'}),
            json.dumps({'outcome': 'fail'}),
            'not json at all',
            '',
        ])
        + '\n',
        encoding='utf-8',
    )

    assert attempts_by_task(log) == Counter({'task-01': 2, 'task-02': 1})


def test_attempts_by_task_without_a_log_counts_nothing(ticket_root: Path) -> None:
    assert attempts_by_task(ticket_root.joinpath('attempts.jsonl')) == Counter()
