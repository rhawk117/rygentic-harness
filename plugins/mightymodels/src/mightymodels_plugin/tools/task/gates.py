"""The two gates of the task domain: what keeps a task from verified and a ticket from ready.

A task is proven only when the reported commit is the current HEAD and descends from the task's
base, every contract command for it passed at that HEAD, its DONE brief names the commit, every
other acceptance criterion carries a citation, and the commit touched only the files the task
owns. A ticket is ready only when a plan task has been started, every plan task is closed, no
fix is stuck and every live contract command passed at HEAD. With no HEAD to compare against, no
receipt counts as taken at it.

Each function returns its problems as the lines the caller shows, and an empty list is a pass.
They read git, the brief file and records the caller already holds, and never the database.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from mightymodels_plugin.core.task_id import is_plan_task
from mightymodels_plugin.core.workspace import GitQueries
from mightymodels_plugin.tools.contract.assessment import Assessment, Taken
from mightymodels_plugin.tools.contract.schema import Outcome, Receipt
from mightymodels_plugin.tools.contract.store import RecordedCommand
from mightymodels_plugin.tools.task.schema import Status, TaskRecord

DONE_HEADING = '## DONE'
ASKED_CRITERION = re.compile(r'^\s*-\s*(AC-\d+)\s*:', re.MULTILINE)
DONE_COMMIT = re.compile(r'^\s*commit:\s*([0-9a-fA-F]{7,64})\s*$', re.MULTILINE)
STUCK = frozenset({Status.FAILED, Status.BLOCKED})
CLOSED = frozenset({Status.VERIFIED, Status.SUPERSEDED})


@dataclass(slots=True, kw_only=True, frozen=True)
class Evidence:
    commit: str
    brief: Path | None
    assertions: Mapping[str, str]
    commands: Sequence[RecordedCommand]
    receipts: Mapping[str, Receipt]


def commit_problems(git: GitQueries, base: str | None, commit: str) -> list[str]:
    if commit != git.resolve_head():
        return ['the reported commit must resolve to the current HEAD']
    if base is None or git.resolve_commit(base) is None:
        return ['the task has no valid base commit']
    if not git.is_ancestor(base, commit):
        return ['the task base is not an ancestor of the reported commit']
    return []


def done_commit(brief_text: str) -> str | None:
    _, separator, done = brief_text.partition(DONE_HEADING)
    named = DONE_COMMIT.search(done)
    return str(named[1]) if separator and named is not None else None


def brief_problems(git: GitQueries, evidence: Evidence) -> list[str]:
    if evidence.brief is None:
        return []
    if not evidence.brief.is_file():
        return ['the task brief is missing']
    named = done_commit(evidence.brief.read_text(encoding='utf-8'))
    if named is None or git.resolve_commit(named) != evidence.commit:
        return ['the DONE brief must name the reported HEAD commit']
    return []


def receipt_problem(command_id: str, receipt: Receipt | None, head: str | None) -> str | None:
    taken = None if receipt is None else Taken(outcome=receipt.outcome, head=receipt.head)
    outcome = Assessment(taken=taken, head=head).outcome_at_head
    if outcome is None:
        return f'{command_id} has no receipt at the current HEAD'
    if outcome != Outcome.PASSED:
        return f'{command_id} {outcome} at HEAD'
    return None


def receipt_problems(
    commands: Sequence[RecordedCommand], receipts: Mapping[str, Receipt], head: str | None
) -> list[str]:
    problems = (receipt_problem(command.id, receipts.get(command.id), head) for command in commands)
    return [problem for problem in problems if problem is not None]


def criteria_in_brief(brief: Path | None) -> list[str]:
    if brief is None or not brief.is_file():
        return []
    asked = brief.read_text(encoding='utf-8').split(DONE_HEADING, 1)[0]
    return [found[1] for found in ASKED_CRITERION.finditer(asked)]


def criteria_problems(evidence: Evidence) -> list[str]:
    by_command = {command.id.split('.', 1)[1] for command in evidence.commands}
    proven = by_command | set(evidence.assertions)
    problems = [
        f'{criterion} has neither a contract command nor a citation'
        for criterion in criteria_in_brief(evidence.brief)
        if criterion not in proven
    ]
    if not evidence.commands and not evidence.assertions:
        problems.append('no contract command and no cited assertion proves this task')
    return problems


def ownership_problems(git: GitQueries, task: TaskRecord, *, base: str, commit: str) -> list[str]:
    outside = sorted(git.changed_files(base, commit) - set(task.owned))
    return [f'changed outside the owned set: {path}' for path in outside]


def verification_problems(git: GitQueries, task: TaskRecord, evidence: Evidence) -> list[str]:
    base = task.base
    problems = commit_problems(git, base, evidence.commit)
    if problems or base is None:
        return problems
    return [
        *receipt_problems(evidence.commands, evidence.receipts, git.resolve_head()),
        *brief_problems(git, evidence),
        *criteria_problems(evidence),
        *ownership_problems(git, task, base=base, commit=evidence.commit),
    ]


def plan_task_problem(record: TaskRecord) -> str | None:
    if record.status is Status.PENDING:
        return f'{record.id} has contract commands but was never started'
    if record.status in CLOSED:
        return None
    return f'{record.id} is {record.status}, not verified'


def readiness_problems(records: Sequence[TaskRecord]) -> list[str]:
    planned = [record for record in records if is_plan_task(record.id)]
    unproven = (plan_task_problem(record) for record in planned)
    return [
        *([] if planned else ['no plan task has been started']),
        *(problem for problem in unproven if problem is not None),
        *(
            f'{record.id} is {record.status}: {"; ".join(record.reasons)}'
            for record in records
            if not is_plan_task(record.id) and record.status in STUCK
        ),
    ]
