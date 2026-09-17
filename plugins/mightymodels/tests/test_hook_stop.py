import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.brief import AskedStanza, DoneHalf, brief_append_done, brief_open
from mightymcp.ticket import HandoffContext, ticket_create

HOOK = Path(__file__).resolve().parents[1].joinpath('hooks', 'stop.py')
CONTEXT = ['durable before advance', 'the brief records the commit', 'git is history']
SHORT_SHA = 7

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]
Commit = Callable[[Path, str], str]
Halt = Callable[[], dict[str, Any]]


def write_brief(task_id: str) -> None:
    written = brief_open(
        'demo',
        task_id,
        AskedStanza(
            objective='Cap the retry backoff',
            acceptance=['AC-1: uv run pytest -q passes'],
            verification='uv run pytest -q',
            files_in_scope=['src/app/**'],
            engineer_tier='claude-sonnet-5',
        ),
        'feat(app): cap the retry backoff',
    )
    assert written.refusals == [], written.refusals


def record_done(task_id: str, sha: str) -> None:
    written = brief_append_done(
        'demo',
        task_id,
        DoneHalf(
            what='capped the backoff',
            commit=sha,
            diff_summary='one guard in retry.py',
            commands_run='uv run pytest -q: 12 passed',
        ),
    )
    assert written.refusals == [], written.refusals


@pytest.fixture
def ticket(repo: Path) -> Path:
    written = ticket_create(
        'demo',
        'Ship demo',
        CONTEXT,
        HandoffContext(scope='med', plan_first=True, branch_name='main'),
    )
    assert written.refusals == [], written.refusals
    return repo.joinpath('.mightymodels', 'demo')


@pytest.fixture
def halt(repo: Path, payload: Load, run_hook_script: RunScript) -> Halt:
    """Stop the session through the hook and return what it told the user."""

    def run() -> dict[str, Any]:
        hook = payload('Stop') | {'cwd': str(repo)}
        proc = run_hook_script(HOOK, json.dumps(hook), repo)
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == '', proc.stderr
        output: dict[str, Any] = json.loads(proc.stdout)
        assert 'decision' not in output
        return output

    return run


def test_a_commit_with_no_done_half_behind_it_is_reminded(
    ticket: Path, repo: Path, commit: Commit, halt: Halt
) -> None:
    write_brief('task-03')
    sha = commit(repo, 'retry.py')
    output = halt()

    assert str(ticket.joinpath('briefs', 'task-03.md')) in output['systemMessage']
    assert sha[:SHORT_SHA] in output['systemMessage']


def test_a_recorded_commit_is_not_reminded(
    ticket: Path, repo: Path, commit: Commit, halt: Halt
) -> None:
    write_brief('task-03')
    write_brief('task-04')
    record_done('task-03', commit(repo, 'retry.py'))

    assert halt() == {}


def test_a_commit_above_the_recorded_one_is_reminded(
    ticket: Path, repo: Path, commit: Commit, halt: Halt
) -> None:
    write_brief('task-03')
    write_brief('task-04')
    record_done('task-03', commit(repo, 'retry.py'))
    sha = commit(repo, 'backoff.py')
    output = halt()

    assert str(ticket.joinpath('briefs', 'task-04.md')) in output['systemMessage']
    assert sha[:SHORT_SHA] in output['systemMessage']


def test_a_lint_sweep_on_top_is_not_work_to_record(
    ticket: Path, repo: Path, commit: Commit, halt: Halt
) -> None:
    write_brief('task-03')
    write_brief('task-04')
    record_done('task-03', commit(repo, 'retry.py'))
    commit(repo, 'chore(lint) sweep the formatting')

    assert halt() == {}


def test_a_lint_sweep_does_not_hide_the_commit_under_it(
    ticket: Path, repo: Path, commit: Commit, halt: Halt
) -> None:
    write_brief('task-03')
    write_brief('task-04')
    record_done('task-03', commit(repo, 'retry.py'))
    sha = commit(repo, 'backoff.py')
    commit(repo, 'chore(lint) sweep the formatting')

    assert sha[:SHORT_SHA] in halt()['systemMessage']


def test_a_sprint_with_every_done_half_written_is_not_reminded(
    ticket: Path, repo: Path, commit: Commit, halt: Halt
) -> None:
    write_brief('task-03')
    record_done('task-03', commit(repo, 'retry.py'))
    commit(repo, 'backoff.py')

    assert halt() == {}


def test_a_ticket_with_no_briefs_is_not_reminded(
    ticket: Path, repo: Path, commit: Commit, halt: Halt
) -> None:
    commit(repo, 'retry.py')

    assert halt() == {}


def test_a_repository_with_no_commits_is_not_reminded(ticket: Path, halt: Halt) -> None:
    write_brief('task-03')

    assert halt() == {}


def test_a_session_with_no_active_ticket_is_not_reminded(
    repo: Path, commit: Commit, halt: Halt
) -> None:
    commit(repo, 'retry.py')

    assert halt() == {}


def test_the_off_switch_stands_the_hook_down(
    ticket: Path, repo: Path, commit: Commit, payload: Load, run_hook_script: RunScript
) -> None:
    write_brief('task-03')
    commit(repo, 'retry.py')
    hook = payload('Stop') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo, MIGHTYMCP_OFF='1')

    assert proc.returncode == 0
    assert proc.stdout == ''
