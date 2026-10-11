"""The snapshot service on a real repository and SQLite: what it shows when git has no answer.

These tests take git off PATH and stand outside a repository, which a git history kept in memory
has neither of.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import git_at
from mightymodels_plugin.tools.snapshot.schema import DEFAULT_LIMIT, SnapshotView
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

type GitRunner = Callable[..., str]

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
BRANCH = 'fix/retry'
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
NEEDS_GIT = 'git was not consulted: this needs git and no git executable is on PATH'
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': BRANCH,
        'context': ['drain loop sleeps between batches'],
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Handoff:
    snapshots: SnapshotService
    runner: GitRunner

    @property
    def root(self) -> Path:
        return self.snapshots.workspace.root

    def git(self, *arguments: str) -> str:
        return self.runner(self.root, *IDENTITY, *arguments).strip()

    def commit(self, relative: str, text: str) -> str:
        self.root.joinpath(relative).write_text(text, encoding='utf-8')
        self.git('add', relative)
        self.git('commit', '-q', '-m', f'change {relative}')
        return self.git('rev-parse', 'HEAD')

    def take(self, limit: int = DEFAULT_LIMIT) -> SnapshotView:
        return self.snapshots.take(TICKET, limit)


@pytest.fixture
def handoff(
    snapshot_service: SnapshotService, ticket_service: TicketService, git: GitRunner
) -> Handoff:
    ticket_service.write(TICKET, ANSWERS)
    ticket_service.validate(TICKET)
    return Handoff(snapshots=snapshot_service, runner=git)


@pytest.fixture
def repo(handoff: Handoff) -> Handoff:
    handoff.git('symbolic-ref', 'HEAD', f'refs/heads/{BRANCH}')
    handoff.commit('queue.py', 'base\n')
    return handoff


class TestWhenGitIsMissing:
    @pytest.fixture
    def repo_without_git(
        self, repo: Handoff, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Handoff:
        monkeypatch.setenv('PATH', str(tmp_path.joinpath('no-binaries')))
        return replace(repo, snapshots=replace(repo.snapshots, git=git_at(repo.root)))

    def test_when_git_is_missing_the_repository_section_is_empty_and_a_warning_says_why(
        self, repo_without_git: Handoff
    ) -> None:
        view = repo_without_git.take()
        record = view.record.model_dump(mode='json')

        assert record['repository'] == {
            'branch': None,
            'head': None,
            'dirty_count': None,
            'dirty': [],
        }
        assert record['warnings'] == [NEEDS_GIT]
        assert view.markdown.endswith(f'## Warnings\n\n- {NEEDS_GIT}\n')


class TestOutsideARepository:
    @pytest.fixture
    def repository(self, tmp_path: Path) -> Path:
        directory = tmp_path.joinpath('plain-directory')
        directory.mkdir()
        return directory

    def test_outside_a_repository_the_snapshot_answers_and_a_warning_says_why(
        self, handoff: Handoff
    ) -> None:
        view = handoff.take()

        assert view.record.repository.head is None
        assert 'is not inside a git repository' in view.record.warnings[0]
        assert 'Repository: detached at unknown; tree unknown.' in view.markdown
