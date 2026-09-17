from collections.abc import Callable
from pathlib import Path

import pytest
from mightymcp.paths import (
    ACTIVE_TICKET_VAR,
    PROJECT_DIR_PLACEHOLDER,
    TicketPathError,
    active_ticket,
    repo_root,
    safe_name,
    ticket_dir,
)

UNSAFE_NAMES = ['../evil', 'a/b', 'a\\b', '..', 'nested/../slug', '', '   ']


@pytest.fixture
def other_repo(make_repo: Callable[[str], Path]) -> Path:
    return make_repo('other')


def make_ticket(root: Path, slug: str, branch: str) -> None:
    directory = root.joinpath('.mightymodels', slug)
    directory.mkdir(parents=True)
    directory.joinpath('ticket.yml').write_text(
        f'task: {slug}\nhandoff-context:\n  branch-name: {branch}\n', encoding='utf-8'
    )


def test_mightymcp_project_dir_wins(
    repo: Path, other_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(other_repo))
    assert repo_root() == repo


@pytest.mark.parametrize('value', ['', '   ', PROJECT_DIR_PLACEHOLDER])
def test_unusable_mightymcp_project_dir_falls_through_to_claude(
    value: str, repo: Path, other_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('MIGHTYMCP_PROJECT_DIR', value)
    monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(other_repo))
    assert repo_root() == other_repo


def test_claude_project_dir_is_used_when_mightymcp_is_unset(
    other_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv('MIGHTYMCP_PROJECT_DIR', raising=False)
    monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(other_repo))
    assert repo_root() == other_repo


def test_git_toplevel_is_used_when_no_env_is_set(
    other_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv('MIGHTYMCP_PROJECT_DIR', raising=False)
    monkeypatch.delenv('CLAUDE_PROJECT_DIR', raising=False)
    inside = other_repo.joinpath('src')
    inside.mkdir()
    monkeypatch.chdir(inside)
    assert repo_root() == other_repo


def test_explicit_argument_is_the_last_resort(
    tmp_path: Path, other_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv('MIGHTYMCP_PROJECT_DIR', raising=False)
    monkeypatch.delenv('CLAUDE_PROJECT_DIR', raising=False)
    monkeypatch.chdir(tmp_path)
    assert repo_root(other_repo) == other_repo


def test_no_root_anywhere_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv('MIGHTYMCP_PROJECT_DIR', raising=False)
    monkeypatch.delenv('CLAUDE_PROJECT_DIR', raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(TicketPathError, match='no repository root'):
        repo_root()


def test_a_root_without_a_git_entry_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = tmp_path.joinpath('bare')
    bare.mkdir()
    monkeypatch.setenv('MIGHTYMCP_PROJECT_DIR', str(bare))

    with pytest.raises(TicketPathError, match=r'no \.git entry'):
        repo_root()


@pytest.mark.parametrize('name', UNSAFE_NAMES)
def test_safe_name_rejects_path_fragments(name: str) -> None:
    with pytest.raises(TicketPathError):
        safe_name(name)


@pytest.mark.parametrize('name', ['demo', 'task-03', 'feat.ticket', ' demo '])
def test_safe_name_accepts_one_segment(name: str) -> None:
    assert safe_name(name) == name.strip()


def test_ticket_dir_is_under_mightymodels(repo: Path) -> None:
    assert ticket_dir('demo') == repo.joinpath('.mightymodels', 'demo')


@pytest.mark.parametrize('name', UNSAFE_NAMES)
def test_ticket_dir_rejects_the_slug_before_resolving_a_root(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv('MIGHTYMCP_PROJECT_DIR', raising=False)
    monkeypatch.delenv('CLAUDE_PROJECT_DIR', raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(TicketPathError, match='name'):
        ticket_dir(name)


def test_a_single_ticket_is_the_active_one(repo: Path) -> None:
    make_ticket(repo, 'demo', 'feat/other')

    assert active_ticket() == 'demo'


def test_the_branch_name_picks_one_of_several_tickets(
    repo: Path, git: Callable[..., str], commit: Callable[[Path, str], str]
) -> None:
    make_ticket(repo, 'alpha', 'feat/alpha')
    make_ticket(repo, 'beta', 'feat/beta')
    commit(repo, 'README.md')
    git(repo, 'checkout', '-q', '-b', 'feat/beta')

    assert active_ticket() == 'beta'


def test_the_environment_names_the_ticket_when_no_branch_matches(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_ticket(repo, 'alpha', 'feat/alpha')
    make_ticket(repo, 'beta', 'feat/beta')
    monkeypatch.setenv(ACTIVE_TICKET_VAR, 'alpha')

    assert active_ticket() == 'alpha'


def test_several_tickets_and_no_branch_or_override_is_an_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_ticket(repo, 'alpha', 'feat/alpha')
    make_ticket(repo, 'beta', 'feat/beta')
    monkeypatch.delenv(ACTIVE_TICKET_VAR, raising=False)

    with pytest.raises(TicketPathError, match=ACTIVE_TICKET_VAR):
        active_ticket()
