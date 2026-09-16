import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from mightymcp.prune import prunable, ticket_archive, ticket_delete, ticket_prunable
from mightymcp.ticket import CompanionDocs, HandoffContext, ticket_create

CONTEXT = ['the ticket is done', 'the branch is merged', 'the archive is written']
ARCHIVE = '# demo\nshipped: the retry cap · PR: #12 · pruned: 2026-09-16\n'
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


def test_the_prunable_tool_reports_a_quiet_ticket(ticket: Path) -> None:
    check = ticket_prunable('demo')

    assert check.prunable
    assert check.reasons == []


def test_the_prunable_tool_reports_an_open_report_thread(ticket: Path) -> None:
    ticket.joinpath('REPORT.md').write_text(
        '# REPORT: demo\n\nopen threads:\n- the retry test is still red\n',
        encoding='utf-8',
    )
    check = ticket_prunable('demo')

    assert not check.prunable
    assert 'the retry test is still red' in check.reasons[0]


def test_the_prunable_tool_reports_an_active_debug(ticket: Path) -> None:
    ticket.joinpath('whats-broken.md').write_text('# broken\n', encoding='utf-8')
    check = ticket_prunable('demo')

    assert not check.prunable
    assert 'whats-broken.md' in check.reasons[0]


def test_the_prunable_tool_reports_unpushed_commits(
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
    check = ticket_prunable('demo')

    assert not check.prunable
    assert 'upstream' in check.reasons[0]


def test_the_prunable_tool_reports_unchecked_issue_boxes(
    repo: Path, fake_gh: Install
) -> None:
    make_ticket(issue_number=ISSUE)
    fake_gh('## Tasks\n- [x] T1 done\n- [ ] T2 open\n')
    check = ticket_prunable('demo')

    assert not check.prunable
    assert f'issue #{ISSUE} has 1 unchecked boxes' in check.reasons[0]


def test_the_archive_lands_under_the_archives_directory(ticket: Path, repo: Path) -> None:
    written = ticket_archive('demo', ARCHIVE)
    path = repo.joinpath('.mightymodels', 'archives', 'demo.md')

    assert written.refusals == []
    assert written.path == str(path)
    assert path.read_text(encoding='utf-8') == ARCHIVE


def test_an_archive_over_the_cap_is_refused(ticket: Path, repo: Path) -> None:
    refused = ticket_archive('demo', '\n'.join(f'line {number}' for number in range(31)))

    assert 'the cap is 30' in refused.refusals[0]
    assert not repo.joinpath('.mightymodels', 'archives').exists()


def test_a_second_archive_is_refused(ticket: Path, repo: Path) -> None:
    assert ticket_archive('demo', ARCHIVE).refusals == []
    refused = ticket_archive('demo', 'a rewritten archive\n')

    assert 'already exists' in refused.refusals[0]
    assert (
        repo.joinpath('.mightymodels', 'archives', 'demo.md').read_text(encoding='utf-8')
        == ARCHIVE
    )


def test_an_archived_and_quiet_ticket_is_deleted(ticket: Path) -> None:
    ticket_archive('demo', ARCHIVE)
    deleted = ticket_delete('demo')

    assert deleted.refusals == []
    assert deleted.path == str(ticket)
    assert not ticket.exists()


def test_a_ticket_without_an_archive_is_not_deleted(ticket: Path) -> None:
    refused = ticket_delete('demo')

    assert 'no archive at' in refused.refusals[0]
    assert ticket.is_dir()


def test_live_work_blocks_the_delete(ticket: Path) -> None:
    ticket_archive('demo', ARCHIVE)
    ticket.joinpath('whats-broken.md').write_text('# broken\n', encoding='utf-8')
    refused = ticket_delete('demo')

    assert 'whats-broken.md' in refused.refusals[0]
    assert ticket.is_dir()


def test_an_archive_for_a_ticket_that_is_not_there_is_refused(repo: Path) -> None:
    refused = ticket_archive('nothing', ARCHIVE)

    assert 'no ticket directory' in refused.refusals[0]
    assert refused.path is None


def test_a_slug_that_is_not_one_path_segment_is_refused(repo: Path) -> None:
    assert ticket_archive('../evil', ARCHIVE).refusals
    assert ticket_delete('../evil').refusals
