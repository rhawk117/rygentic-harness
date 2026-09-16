import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mightymcp.artifacts import ticket_directory
from mightymcp.brief import task_id_refusals

LOG = 'attempts.jsonl'
FAIL = 'fail'
CI = 'ci'
OUTCOMES = ('pass', FAIL)
# Thresholds quoted from the skills: budgetron "two rounds max"; scout verification
# failing twice on one task routes to whats-broken; whats-broken breaks at three
# failed fixes; stick-the-landing stops after two failed rounds on the same check.
ESCALATIONS = {
    'verification': (2, 'whats-broken', 'second failed verification of {task_id}'),
    'budgetron': (2, 'engineer', 'second failed budgetron round on {task_id}'),
    'fix': (3, 'stop', 'third failed fix on {task_id}'),
    CI: (2, 'stop', 'second failed ci run of check {check}'),
}
KINDS = tuple(ESCALATIONS)


class AttemptRecord(BaseModel):
    """One logged attempt, with the counts it produced and where they route."""

    task_id: str = Field(description='Brief stem, e.g. task-03')
    kind: str = Field(description=f'One of {", ".join(KINDS)}')
    outcome: str = Field(description=f'One of {", ".join(OUTCOMES)}')
    attempts: int = Field(default=0, description='Attempts logged for this task')
    failures: int = Field(
        default=0, description='Failed attempts of this kind for this task'
    )
    escalate_to: str | None = Field(
        default=None, description='whats-broken, engineer, stop, or null'
    )
    rule: str = Field(default='', description='The threshold that fired')
    path: str | None = Field(default=None, description='Absolute path of attempts.jsonl')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was logged'
    )


def task_record_attempt(
    slug: str, task_id: str, kind: str, outcome: str, check: str | None = None
) -> AttemptRecord:
    """Log one attempt on a task and report whether it crosses an escalation threshold."""
    directory, refusals = ticket_directory(slug)
    refusals.extend(task_id_refusals(task_id))
    if kind not in KINDS:
        refusals.append(f'unknown kind {kind!r}; expected {", ".join(KINDS)}')
    if outcome not in OUTCOMES:
        refusals.append(f'unknown outcome {outcome!r}; expected {", ".join(OUTCOMES)}')
    if directory is None or refusals:
        return AttemptRecord(
            task_id=task_id, kind=kind, outcome=outcome, refusals=refusals
        )

    log = directory.joinpath(LOG)
    record = {
        'ts': datetime.now(UTC).isoformat(),
        'task_id': task_id,
        'kind': kind,
        'outcome': outcome,
        'check': check,
    }
    records = [*_read(log), record]
    with log.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record) + '\n')

    failures = _failures(records, record)
    escalate_to, rule = _escalation(kind, outcome, failures, check, task_id)
    return AttemptRecord(
        task_id=task_id,
        kind=kind,
        outcome=outcome,
        attempts=sum(entry.get('task_id') == task_id for entry in records),
        failures=failures,
        escalate_to=escalate_to,
        rule=rule,
        path=str(log),
    )


def _escalation(
    kind: str, outcome: str, failures: int, check: str | None, task_id: str
) -> tuple[str | None, str]:
    threshold, target, rule = ESCALATIONS[kind]
    if outcome != FAIL or failures < threshold:
        return None, ''
    return target, rule.format(task_id=task_id, check=check)


def _failures(records: list[dict[str, Any]], record: dict[str, Any]) -> int:
    """Count this task's failed attempts of this kind; ci counts per check."""
    return sum(
        entry.get('task_id') == record['task_id']
        and entry.get('kind') == record['kind']
        and entry.get('outcome') == FAIL
        and (record['kind'] != CI or entry.get('check') == record['check'])
        for entry in records
    )


def _read(log: Path) -> list[dict[str, Any]]:
    if not log.is_file():
        return []
    entries = (_decode(line) for line in log.read_text(encoding='utf-8').splitlines())
    return [entry for entry in entries if entry is not None]


def _decode(line: str) -> dict[str, Any] | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None
