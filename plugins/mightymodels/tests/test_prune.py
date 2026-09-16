import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from mightymcp.prune import prunable
from mightymcp.ticket import CompanionDocs, HandoffContext, ticket_create

CONTEXT = ['the ticket is done', 'the branch is merged', 'the archive is written']
ISSUE = 7
Install = Callable[..., None]


def make_ticket(issue_number: int | None = None) -> None:
    written = ticket_create(
        'demo',
        'Ship demo',
        CONTEXT,
        HandoffContext(scope='med', plan_first=True, branch_name='main'),
        CompanionDocs(issue_number=issue_number),
    )
    assert written.refusals == [], written.refusals


@pytest.fixture
def ticket(repo: Path) -> Path:
    make_ticket()
    return repo.joinpath('.mightymodels', 'demo')


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Install:
    """Put a gh on PATH that prints the issue body this test wants."""

    def install(body: str, exit_code: int = 0) -> None:
        directory = tmp_path.joinpath('bin')
        directory.mkdir(exist_ok=True)
        script = directory.joinpath('gh')
        script.write_text(
            f'#!{sys.executable}\nimport sys\n'
            f'sys.stdout.write({body!r})\nsys.exit({exit_code})\n',
            encoding='utf-8',
        )
        script.chmod(0o755)
        monkeypatch.setenv('PATH', f'{directory}{os.pathsep}{os.environ["PATH"]}')

    return install


def test_a_quiet_ticket_is_prunable(ticket: Path) -> None:
    check = prunable('demo')

    assert check.prunable
    assert check.reasons == []


def test_an_unread_checklist_is_reported_as_skipped(ticket: Path) -> None:
    assert any('checklist' in skipped for skipped in prunable('demo').skipped)


def test_an_open_report_thread_blocks_the_prune(ticket: Path) -> None:
    ticket.joinpath('REPORT.md').write_text(
        '# REPORT: demo\n\nopen threads:\n- the retry test is still red\n',
        encoding='utf-8',
    )
    check = prunable('demo')

    assert not check.prunable
    assert 'the retry test is still red' in check.reasons[0]


def test_a_report_without_open_threads_does_not_block(ticket: Path) -> None:
    ticket.joinpath('REPORT.md').write_text(
        '# REPORT: demo\n\nescalated:\n- none\nopen threads:\n- none\n',
        encoding='utf-8',
    )

    assert prunable('demo').prunable


def test_an_active_debug_blocks_the_prune(ticket: Path) -> None:
    ticket.joinpath('whats-broken.md').write_text('# broken\n', encoding='utf-8')
    check = prunable('demo')

    assert not check.prunable
    assert 'whats-broken.md' in check.reasons[0]


def test_unpushed_commits_block_the_prune(
    ticket: Path,
    repo: Path,
    tmp_path: Path,
    git: Callable[..., str],
    commit: Callable[[Path, str], str],
) -> None:
    remote = tmp_path.joinpath('remote.git')
    git(repo, 'init', '--bare', '-q', str(remote))
    git(repo, 'remote', 'add', 'origin', str(remote))
    commit(repo, 'README.md')
    git(repo, 'push', '-q', '-u', 'origin', 'main')
    commit(repo, 'limits.py')
    check = prunable('demo')

    assert not check.prunable
    assert 'upstream' in check.reasons[0]


def test_a_branch_without_an_upstream_does_not_block(ticket: Path) -> None:
    assert prunable('demo').prunable


def test_unchecked_issue_boxes_block_the_prune(repo: Path, fake_gh: Install) -> None:
    make_ticket(issue_number=ISSUE)
    fake_gh('## Tasks\n- [x] T1 done\n- [ ] T2 open\n')
    check = prunable('demo')

    assert not check.prunable
    assert f'issue #{ISSUE} has 1 unchecked boxes' in check.reasons[0]


def test_a_fully_checked_issue_does_not_block(repo: Path, fake_gh: Install) -> None:
    make_ticket(issue_number=ISSUE)
    fake_gh('## Tasks\n- [x] T1 done\n- [x] T2 done\n')
    check = prunable('demo')

    assert check.prunable
    assert check.skipped == []


def test_a_failing_gh_is_a_skipped_check_not_a_refusal(
    repo: Path, fake_gh: Install
) -> None:
    make_ticket(issue_number=ISSUE)
    fake_gh('', exit_code=1)
    check = prunable('demo')

    assert check.prunable
    assert f'issue #{ISSUE}' in check.skipped[0]


def test_a_ticket_that_is_not_there_is_refused(repo: Path) -> None:
    check = prunable('nothing')

    assert not check.prunable
    assert check.reasons == []
    assert check.refusals
