import json
from collections.abc import Callable
from pathlib import Path

import pytest
from mightymcp.status import sprint_status

BRIEFS = {
    'task-01.md': '## ASKED\nobjective: one\n\n## DONE\nwhat: done\ncommit: abc1234\n\n'
    '## VERIFIED\nscout: matches ASKED\n',
    'task-02.md': '## ASKED\nobjective: two\n\n## DONE\nwhat: done\ncommit: def5678\n',
    'task-03.md': '## ASKED\nobjective: three\n',
}
ATTEMPTS = [
    json.dumps({'task_id': 'task-01', 'outcome': 'failed'}),
    json.dumps({'task_id': 'task-01', 'outcome': 'failed'}),
    json.dumps({'task_id': 'task-02', 'outcome': 'failed'}),
    'not json at all',
    '',
]


def commit(git: Callable[..., str], repo: Path, name: str) -> None:
    repo.joinpath(name).write_text(name, encoding='utf-8')
    git(repo, 'add', '-A')
    git(
        repo,
        '-c',
        'user.email=test@example.com',
        '-c',
        'user.name=test',
        '-c',
        'commit.gpgsign=false',
        'commit',
        '-q',
        '-m',
        name,
    )


@pytest.fixture
def sprint(ticket_root: Path) -> Path:
    for name, text in BRIEFS.items():
        ticket_root.joinpath('briefs', name).write_text(text, encoding='utf-8')
    ticket_root.joinpath('attempts.jsonl').write_text(
        '\n'.join(ATTEMPTS) + '\n', encoding='utf-8'
    )
    return ticket_root


def test_one_row_per_brief_in_order(sprint: Path) -> None:
    status = sprint_status('demo')

    assert status.refusals == []
    assert [task.task_id for task in status.tasks] == ['task-01', 'task-02', 'task-03']
    assert all(task.asked for task in status.tasks)


def test_done_and_commit_come_from_the_done_half(sprint: Path) -> None:
    tasks = {task.task_id: task for task in sprint_status('demo').tasks}

    assert [tasks[name].done for name in ('task-01', 'task-02', 'task-03')] == [
        True,
        True,
        False,
    ]
    assert tasks['task-01'].commit == 'abc1234'
    assert tasks['task-02'].commit == 'def5678'
    assert tasks['task-03'].commit is None


def test_verified_needs_the_verified_section(sprint: Path) -> None:
    tasks = {task.task_id: task for task in sprint_status('demo').tasks}

    assert tasks['task-01'].verified
    assert not tasks['task-02'].verified
    assert not tasks['task-03'].verified


def test_attempts_are_counted_per_task(sprint: Path) -> None:
    tasks = {task.task_id: task for task in sprint_status('demo').tasks}

    assert tasks['task-01'].attempts == 2
    assert tasks['task-02'].attempts == 1
    assert tasks['task-03'].attempts == 0


def test_attempts_are_zero_without_the_log(sprint: Path) -> None:
    sprint.joinpath('attempts.jsonl').unlink()

    assert [task.attempts for task in sprint_status('demo').tasks] == [0, 0, 0]


def test_ticket_wide_state_is_reported(sprint: Path) -> None:
    status = sprint_status('demo')
    assert not status.whats_broken_active
    assert not status.report_present

    sprint.joinpath('whats-broken.md').write_text('attempt 1\n', encoding='utf-8')
    sprint.joinpath('REPORT.md').write_text('shipped\n', encoding='utf-8')
    status = sprint_status('demo')

    assert status.whats_broken_active
    assert status.report_present


def test_unpushed_commits_is_minus_one_without_an_upstream(
    sprint: Path, repo: Path, git: Callable[..., str]
) -> None:
    commit(git, repo, 'one.txt')

    assert sprint_status('demo').unpushed_commits == -1


def test_unpushed_commits_counts_what_the_remote_lacks(
    sprint: Path, repo: Path, tmp_path: Path, git: Callable[..., str]
) -> None:
    origin = tmp_path.joinpath('origin.git')
    git(tmp_path, 'init', '--bare', '-q', '-b', 'main', str(origin))
    commit(git, repo, 'one.txt')
    git(repo, 'remote', 'add', 'origin', str(origin))
    git(repo, 'push', '-q', '-u', 'origin', 'main')

    assert sprint_status('demo').unpushed_commits == 0

    commit(git, repo, 'two.txt')
    assert sprint_status('demo').unpushed_commits == 1


def test_a_ticket_without_briefs_has_no_rows(ticket_root: Path) -> None:
    status = sprint_status('demo')

    assert status.tasks == []
    assert status.refusals == []


def test_a_missing_ticket_is_refused(repo: Path) -> None:
    status = sprint_status('demo')

    assert status.tasks == []
    assert 'no ticket directory at' in status.refusals[0]


def test_an_unsafe_slug_is_refused(repo: Path) -> None:
    status = sprint_status('../evil')

    assert status.tasks == []
    assert status.refusals[0].startswith('name')
