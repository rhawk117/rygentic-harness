"""The close service on a real repository and SQLite: what git answers, and the stored row.

These tests take git off PATH, stand outside a repository, name a branch git is never asked
about, and read the closing's row, which the stores and the git history kept in memory have none
of.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import git_at
from mightymodels_plugin.tools.close.rendering import ARCHIVE_LINES
from mightymodels_plugin.tools.close.schema import Closing
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.tools.close.tables import ClosingRow
from mightymodels_plugin.tools.contract.schema import ContractCommand, Outcome, Phase, Receipt
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.investigation.schema import (
    EntryKind,
    InvestigationStart,
    LedgerEntry,
    Source,
    TargetKind,
)
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.task.repository import task_store
from mightymodels_plugin.tools.task.schema import Implementer, Status
from mightymodels_plugin.tools.task.store import Attempt, Transition
from mightymodels_plugin.tools.ticket.repository import ticket_store
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

type GitRunner = Callable[..., str]

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
OLD = 'a' * 40
CHECKED_OUT = 'feature'
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
NEEDS_GIT = 'git was not consulted: this needs git and no git executable is on PATH\n'
ARCHIVE = f'.mightymodels/archives/{SLUG}.md'
LEDGER = '20260928-queue'
LEDGER_TARGET = InvestigationStart(target='queue', kind=TargetKind.BEHAVIOR)
LEDGER_STARTED = datetime(2026, 9, 28, tzinfo=UTC)
LEDGER_DECISION = LedgerEntry(
    kind=EntryKind.DECISION, text='keep the\n10s floor', source=Source.USER
)
ANSWERS: Mapping[str, object] = MappingProxyType(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'context': ['drain loop sleeps between batches'],
        'issue': 42,
    }
)
CLOSING = Closing(
    shipped='Retry queue drains in under a second',
    pr='https://x/pull/7',
    gotchas=('the backoff floor is load-bearing',),
)


def transition_to(task_id: str, after: Status) -> Transition:
    before = Status.PENDING if after is Status.IN_PROGRESS else Status.IN_PROGRESS
    return Transition(task_id=task_id, before=before, after=after, reasons=[], head=OLD, at=now())


@dataclass(frozen=True, slots=True, kw_only=True)
class Repo:
    closings: CloseService
    tickets: TicketService
    contracts: ContractService
    database: Database
    runner: GitRunner

    @property
    def root(self) -> Path:
        return self.closings.workspace.root

    @property
    def state(self) -> Path:
        return self.root.joinpath('.mightymodels')

    def git(self, *arguments: str) -> str:
        return self.runner(self.root, *IDENTITY, *arguments).strip()

    def stage(self, branch: str) -> None:
        self.tickets.write(TICKET, TicketAnswers.model_validate({**ANSWERS, 'branch': branch}))
        self.tickets.validate(TICKET)

    def approve_with_a_passing_receipt(self, command_id: str, argv: tuple[str, ...]) -> None:
        command = ContractCommand(id=command_id, argv=argv, approved_by='user')
        self.contracts.approve(TICKET, [command])
        receipt = Receipt(
            id=command_id,
            argv=argv,
            outcome=Outcome.PASSED,
            exit=0,
            duration_ms=0,
            stdout_tail='',
            stderr_tail='',
            digest='d' * 64,
            head=OLD,
            phase=Phase.TASK,
            at=now(),
        )
        with self.contracts.store.transaction() as repository:
            repository.record(TICKET, [receipt])

    def record_task(self, task_id: str, after: Status, *workers: Implementer) -> None:
        started = transition_to(task_id, Status.IN_PROGRESS)
        with task_store(self.database).transaction() as repository:
            repository.tickets.mark_in_progress(TICKET)
            for worker in workers:
                attempt = Attempt(worker=worker, mode=None, owned=['queue.py'])
                repository.record_start(TICKET, started, attempt)
        with task_store(self.database).transaction() as repository:
            repository.record_mark(TICKET, transition_to(task_id, after))

    def record_verified_work(self) -> None:
        self.record_task('T1', Status.VERIFIED, Implementer.ENGINEER)
        self.record_task('C1', Status.VERIFIED, Implementer.ENGINEER, Implementer.ARCHITECT)

    def ticket_status(self) -> str:
        with ticket_store(self.database).transaction() as repository:
            return repository.staged_ticket(TICKET).status

    def recorded_archive(self) -> str | None:
        with self.database.transaction() as session:
            key = (self.database.repository_key.root, SLUG)
            closing = session.get(ClosingRow, key)
            return None if closing is None else closing.archive


@pytest.fixture
def ticket_branch() -> str:
    return 'main'


@pytest.fixture
def staged(
    close_service: CloseService,
    ticket_service: TicketService,
    contract_service: ContractService,
    repository_database: Database,
    git: GitRunner,
    ticket_branch: str,
) -> Repo:
    space = Repo(
        closings=close_service,
        tickets=ticket_service,
        contracts=contract_service,
        database=repository_database,
        runner=git,
    )
    space.stage(ticket_branch)
    space.approve_with_a_passing_receipt('T1.AC-1', ('uv', 'run', 'pytest'))
    return space


@pytest.fixture
def committed(staged: Repo) -> Repo:
    staged.git('symbolic-ref', 'HEAD', f'refs/heads/{CHECKED_OUT}')
    staged.root.joinpath('queue.py').write_text('base\n', encoding='utf-8')
    staged.git('add', 'queue.py')
    staged.git('commit', '-q', '-m', 'base')
    return staged


@pytest.fixture
def repo(committed: Repo) -> Repo:
    committed.record_verified_work()
    return committed


@pytest.fixture
def repo_with_a_ledger_decision(repo: Repo, investigation_service: InvestigationService) -> Repo:
    investigation_service.start(LEDGER_TARGET, started=LEDGER_STARTED)
    investigation_service.add(Slug(LEDGER), 1, [LEDGER_DECISION])
    with ticket_store(repo.database).transaction() as repository:
        section = repository.staged_ticket(TICKET).ticket
        repository.stage(TICKET, section, [LEDGER])
    return repo


class TestUnverifiedTasks:
    @pytest.fixture
    def repo_with_a_blocked_task(self, committed: Repo) -> Repo:
        committed.record_task('T1', Status.BLOCKED, Implementer.ENGINEER)
        return committed

    @pytest.fixture
    def repo_with_a_blocked_task_and_a_live_debug(self, repo_with_a_blocked_task: Repo) -> Repo:
        note = repo_with_a_blocked_task.state.joinpath(SLUG, 'whats-broken.md')
        note.write_text('hypothesis\n', encoding='utf-8')
        return repo_with_a_blocked_task

    def test_a_refused_close_stores_nothing_and_leaves_the_ticket_open(
        self, repo_with_a_blocked_task_and_a_live_debug: Repo
    ) -> None:
        view = repo_with_a_blocked_task_and_a_live_debug.closings.close(TICKET, CLOSING)

        assert view.text.startswith('not closed; live work remains\n')
        assert view.archive is None
        assert repo_with_a_blocked_task_and_a_live_debug.ticket_status() == 'in-progress'
        assert repo_with_a_blocked_task_and_a_live_debug.recorded_archive() is None


class TestWhenGitIsMissing:
    @pytest.fixture
    def ticket_branch(self) -> str:
        return CHECKED_OUT

    @pytest.fixture
    def repo_without_git(self, repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
        monkeypatch.setenv('PATH', str(tmp_path.joinpath('no-binaries')))
        return replace(repo, closings=replace(repo.closings, git=git_at(repo.root)))

    def test_when_git_is_missing_the_branch_is_not_asked_about_and_the_text_says_so(
        self, repo_without_git: Repo
    ) -> None:
        view = repo_without_git.closings.check(TICKET)

        assert (view.blocked, view.text) == (False, f'{SLUG} has no live work\n{NEEDS_GIT}')

    def test_when_git_is_missing_a_close_says_git_was_not_consulted(
        self, repo_without_git: Repo
    ) -> None:
        view = repo_without_git.closings.close(TICKET, CLOSING)

        assert view.text == f'closed {SLUG}; archive at {ARCHIVE}\n{NEEDS_GIT}'
        assert view.archive is not None
        assert view.archive.record.head is None


class TestABranchNameGitCannotTake:
    BRANCH = '--all'
    UNCHECKED = f"branch {BRANCH} could not be checked: '{BRANCH}' is not a plain revision name"

    @pytest.fixture
    def ticket_branch(self) -> str:
        return self.BRANCH

    def test_a_branch_name_that_is_not_a_plain_revision_blocks_and_is_named(
        self, repo: Repo
    ) -> None:
        view = repo.closings.check(TICKET)

        assert (view.blocked, view.text) == (True, f'live work remains\n  - {self.UNCHECKED}\n')


class TestALegalBranchNameOutsideTheRevisionPattern:
    BRANCH = 'feat/a+b'
    UNCHECKED = f"branch {BRANCH} could not be checked: '{BRANCH}' is not a plain revision name"

    @pytest.fixture
    def ticket_branch(self) -> str:
        return self.BRANCH

    @pytest.fixture
    def repo_with_the_branch_unpushed(self, repo: Repo) -> Repo:
        repo.git('branch', self.BRANCH)
        return repo

    def test_a_branch_whose_name_cannot_be_asked_about_blocks_and_is_named(
        self, repo_with_the_branch_unpushed: Repo
    ) -> None:
        view = repo_with_the_branch_unpushed.closings.check(TICKET)

        assert (view.blocked, view.blockers) == (True, (self.UNCHECKED,))


class TestClose:
    @pytest.fixture
    def repo_with_an_older_archive(self, repo: Repo) -> Repo:
        archives = repo.state.joinpath('archives')
        archives.mkdir(parents=True)
        archives.joinpath(f'{SLUG}.md').write_text('# older\n', encoding='utf-8')
        return repo

    def test_close_writes_a_bounded_archive_and_marks_the_unit_closed(
        self, repo_with_a_ledger_decision: Repo
    ) -> None:
        view = repo_with_a_ledger_decision.closings.close(TICKET, CLOSING)

        assert view.archive is not None
        record = view.archive.record.model_dump(mode='json')
        assert not view.blocked
        assert len(view.archive.markdown.splitlines()) <= ARCHIVE_LINES
        assert 'PR: https://x/pull/7 · tracker: #42' in view.archive.markdown
        assert '- keep the 10s floor (20260928-queue e2)' in view.archive.markdown
        assert record['verification'][0]['argv'] == ['uv', 'run', 'pytest']
        assert (
            repo_with_a_ledger_decision.ticket_status(),
            repo_with_a_ledger_decision.recorded_archive(),
        ) == ('closed', ARCHIVE)

    def test_a_repeated_slug_gets_its_own_archive(self, repo_with_an_older_archive: Repo) -> None:
        view = repo_with_an_older_archive.closings.close(TICKET, CLOSING)

        assert view.archive is not None
        assert repo_with_an_older_archive.recorded_archive() == (
            f'.mightymodels/archives/{SLUG}-2.md'
        )
        assert view.archive.record_path == f'.mightymodels/archives/{SLUG}-2.json'
        assert view.archive.markdown.endswith(f'details: archives/{SLUG}-2.json\n')


class TestOutsideARepository:
    @pytest.fixture
    def repository(self, tmp_path: Path) -> Path:
        directory = tmp_path.joinpath('plain-directory')
        directory.mkdir()
        return directory

    @pytest.fixture
    def verified_work_outside_a_repository(self, staged: Repo) -> Repo:
        staged.record_verified_work()
        return staged

    def test_outside_a_repository_check_answers_and_says_git_was_not_consulted(
        self, verified_work_outside_a_repository: Repo
    ) -> None:
        view = verified_work_outside_a_repository.closings.check(TICKET)

        assert not view.blocked
        assert view.text.startswith(f'{SLUG} has no live work\ngit was not consulted: ')
        assert 'is not inside a git repository' in view.text
