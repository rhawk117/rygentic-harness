"""The close service against a real git repository, with archive_ticket.py's tests moved here."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import workspace_at
from mightymodels_plugin.tools.close.rendering import ARCHIVE_LINES
from mightymodels_plugin.tools.close.schema import CloseView, Closing
from mightymodels_plugin.tools.close.service import (
    CloseService,
    ShippedRequiredError,
    TooManyGotchasError,
)
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
from mightymodels_plugin.tools.review.schema import (
    Decision,
    DisposePayload,
    Disposition,
    Emphasis,
    FindingInput,
    ReportedSeverity,
    ResolvePayload,
    Result,
    ReviewScope,
    StartPayload,
)
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.task.repository import task_store
from mightymodels_plugin.tools.task.schema import Implementer, Status, TaskStart
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.task.store import Attempt, Transition
from mightymodels_plugin.tools.tests.support import StateServer
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
REVIEWED = datetime(2026, 9, 28, 12, tzinfo=UTC)
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


def reported_finding(number: int) -> FindingInput:
    return FindingInput(
        sources=(f'MV-{number}',),
        severity=ReportedSeverity.HIGH,
        title=f'finding {number}',
        location=f'src/module_{number}.py:1',
        fix='fix it',
        verify='run the tests',
    )


def transition_to(task_id: str, after: Status) -> Transition:
    before = Status.PENDING if after is Status.IN_PROGRESS else Status.IN_PROGRESS
    return Transition(task_id=task_id, before=before, after=after, reasons=[], head=OLD, at=now())


@dataclass(frozen=True, slots=True, kw_only=True)
class Repo:
    closings: CloseService
    tickets: TicketService
    contracts: ContractService
    reviews: ReviewService
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
        with task_store(self.closings.database).transaction() as repository:
            repository.tickets.mark_in_progress(TICKET)
            for worker in workers:
                attempt = Attempt(worker=worker, mode=None, owned=['queue.py'])
                repository.record_start(TICKET, started, attempt)
        with task_store(self.closings.database).transaction() as repository:
            repository.record_mark(TICKET, transition_to(task_id, after))

    def record_verified_work(self) -> None:
        self.record_task('T1', Status.VERIFIED, Implementer.ENGINEER)
        self.record_task('C1', Status.VERIFIED, Implementer.ENGINEER, Implementer.ARCHITECT)

    def review(self, findings: int) -> RunId:
        payload = StartPayload(
            scope=ReviewScope.CODEBASE, depth=Depth.DEEP, emphasis=Emphasis.BALANCED, slug=TICKET
        )
        run = RunId(str(self.reviews.start(payload, started=REVIEWED).run_id))
        self.reviews.add_findings(run, [reported_finding(n) for n in range(1, findings + 1)])
        return run

    def ticket_status(self) -> str:
        with ticket_store(self.closings.database).transaction() as repository:
            return repository.staged_ticket(TICKET).status

    def recorded_archive(self) -> str | None:
        with self.closings.database.transaction() as session:
            key = (self.closings.database.repository_key.root, SLUG)
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
    review_service: ReviewService,
    git: GitRunner,
    ticket_branch: str,
) -> Repo:
    space = Repo(
        closings=close_service,
        tickets=ticket_service,
        contracts=contract_service,
        reviews=review_service,
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
    with ticket_store(repo.closings.database).transaction() as repository:
        section = repository.staged_ticket(TICKET).ticket
        repository.stage(TICKET, section, [LEDGER])
    return repo


class TestCheck:
    def test_a_ticket_with_everything_verified_has_no_live_work(self, repo: Repo) -> None:
        view = repo.closings.check(TICKET)

        assert (view.blocked, view.text) == (False, f'{SLUG} has no live work\n')

    def test_a_staged_ticket_without_verified_work_cannot_close(self, committed: Repo) -> None:
        view = committed.closings.close(TICKET, CLOSING)

        assert view.blocked
        assert view.blockers == (
            'T1 has contract commands but was never started',
            'no verified task work is recorded',
        )


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

    def test_an_unverified_task_blocks(self, repo_with_a_blocked_task: Repo) -> None:
        view = repo_with_a_blocked_task.closings.check(TICKET)

        assert view.blocked
        assert view.text == 'live work remains\n  - T1 is blocked, not verified\n'

    def test_unverified_tasks_and_a_live_debug_block_closing(
        self, repo_with_a_blocked_task_and_a_live_debug: Repo
    ) -> None:
        view = repo_with_a_blocked_task_and_a_live_debug.closings.close(TICKET, CLOSING)

        assert view.blocked
        assert 'T1 is blocked, not verified' in view.text
        assert 'whats-broken.md is present' in view.text
        assert not repo_with_a_blocked_task_and_a_live_debug.state.joinpath('archives').exists()

    def test_a_refused_close_stores_nothing_and_leaves_the_ticket_open(
        self, repo_with_a_blocked_task_and_a_live_debug: Repo
    ) -> None:
        view = repo_with_a_blocked_task_and_a_live_debug.closings.close(TICKET, CLOSING)

        assert view.text.startswith('not closed; live work remains\n')
        assert view.archive is None
        assert repo_with_a_blocked_task_and_a_live_debug.ticket_status() == 'in-progress'
        assert repo_with_a_blocked_task_and_a_live_debug.recorded_archive() is None


class TestALiveDebug:
    @pytest.fixture
    def repo_with_a_live_debug(self, repo: Repo) -> Repo:
        repo.state.joinpath(SLUG, 'whats-broken.md').write_text('hypothesis\n', encoding='utf-8')
        return repo

    def test_a_live_debug_note_blocks(self, repo_with_a_live_debug: Repo) -> None:
        view = repo_with_a_live_debug.closings.check(TICKET)

        assert view.blockers == ('whats-broken.md is present: a debug is still live',)


class TestReviewFindings:
    @pytest.fixture
    def repo_with_an_unfixed_and_an_undecided_finding(self, repo: Repo) -> Repo:
        run = repo.review(findings=2)
        decisions = {'F1': Disposition(decision=Decision.FIX)}
        repo.reviews.dispose(run, DisposePayload(by='user', decisions=decisions))
        return repo

    @pytest.fixture
    def repo_with_every_finding_settled(
        self, repo_with_an_unfixed_and_an_undecided_finding: Repo
    ) -> Repo:
        space = repo_with_an_unfixed_and_an_undecided_finding
        run = RunId(REVIEWED.strftime('%Y%m%d-%H%M%S'))
        dismissed = {'F2': Disposition(decision=Decision.DISMISS, reason='not reachable')}
        space.reviews.dispose(run, DisposePayload(by='user', decisions=dismissed))
        space.reviews.resolve(run, ResolvePayload(finding='F1', result=Result.FIXED, commit=OLD))
        return space

    def test_undecided_and_unfixed_review_findings_block(
        self, repo_with_an_unfixed_and_an_undecided_finding: Repo
    ) -> None:
        view = repo_with_an_unfixed_and_an_undecided_finding.closings.check(TICKET)

        assert 'review finding F2 has no decision' in view.text
        assert 'review finding F1 was chosen for fixing and is not fixed' in view.text

    def test_a_fixed_finding_and_a_dismissed_one_no_longer_block(
        self, repo_with_every_finding_settled: Repo
    ) -> None:
        view = repo_with_every_finding_settled.closings.close(TICKET, CLOSING)

        assert not view.blocked
        assert view.archive is not None
        assert 'review: run 20260928-120000 (deep), 2 findings; fixed F1; dismiss F2' in (
            view.archive.markdown
        )
        assert '- review F2: not reachable' in view.archive.markdown


class TestTheTicketBranch:
    @pytest.fixture
    def ticket_branch(self) -> str:
        return CHECKED_OUT

    @pytest.fixture
    def repo_with_an_uncommitted_change(self, repo: Repo) -> Repo:
        repo.root.joinpath('queue.py').write_text('changed\n', encoding='utf-8')
        return repo

    @pytest.fixture
    def repo_with_the_branch_on_a_remote(self, repo: Repo) -> Repo:
        repo.git('update-ref', f'refs/remotes/origin/{CHECKED_OUT}', 'HEAD')
        return repo

    @pytest.fixture
    def repo_on_another_branch_with_an_uncommitted_change(
        self, repo_with_an_uncommitted_change: Repo
    ) -> Repo:
        repo_with_an_uncommitted_change.git('symbolic-ref', 'HEAD', 'refs/heads/elsewhere')
        return repo_with_an_uncommitted_change

    def test_a_branch_with_commits_on_no_remote_blocks(self, repo: Repo) -> None:
        view = repo.closings.check(TICKET)

        assert 'branch feature has 1 commits on no remote' in view.text

    def test_a_checked_out_branch_with_uncommitted_changes_blocks(
        self, repo_with_an_uncommitted_change: Repo
    ) -> None:
        view = repo_with_an_uncommitted_change.closings.check(TICKET)

        assert view.blockers == (
            'branch feature has 1 commits on no remote',
            'branch feature is checked out with uncommitted changes',
        )

    def test_a_branch_whose_commits_are_on_a_remote_does_not_block(
        self, repo_with_the_branch_on_a_remote: Repo
    ) -> None:
        view = repo_with_the_branch_on_a_remote.closings.check(TICKET)

        assert (view.blocked, view.blockers) == (False, ())

    def test_uncommitted_changes_on_another_branch_do_not_block(
        self, repo_on_another_branch_with_an_uncommitted_change: Repo
    ) -> None:
        view = repo_on_another_branch_with_an_uncommitted_change.closings.check(TICKET)

        assert view.blockers == ('branch feature has 1 commits on no remote',)


class TestABranchGitHasNoAnswerFor:
    @pytest.fixture
    def ticket_branch(self) -> str:
        return CHECKED_OUT

    @pytest.fixture
    def repo_with_the_branch_deleted(self, repo: Repo) -> Repo:
        repo.git('checkout', '-q', '-b', 'elsewhere')
        repo.git('branch', '-q', '-D', CHECKED_OUT)
        return repo

    @pytest.fixture
    def repo_with_a_lost_parent_commit(self, repo: Repo) -> Repo:
        parent = repo.git('rev-parse', 'HEAD')
        repo.git('commit', '-q', '--allow-empty', '-m', 'second')
        repo.root.joinpath('.git', 'objects', parent[:2], parent[2:]).unlink()
        return repo

    @pytest.fixture
    def repo_with_an_unreadable_index(self, repo: Repo) -> Repo:
        repo.root.joinpath('.git', 'index').write_bytes(b'not an index')
        return repo

    def test_a_branch_that_is_no_longer_in_the_repository_does_not_block(
        self, repo_with_the_branch_deleted: Repo
    ) -> None:
        view = repo_with_the_branch_deleted.closings.check(TICKET)

        assert (view.blocked, view.blockers) == (False, ())

    def test_a_branch_whose_unpushed_commits_git_cannot_count_blocks(
        self, repo_with_a_lost_parent_commit: Repo
    ) -> None:
        view = repo_with_a_lost_parent_commit.closings.check(TICKET)

        assert view.blockers == (
            'branch feature could not be checked: git could not count its commits on no remote',
        )

    def test_a_checked_out_branch_whose_status_git_cannot_read_blocks(
        self, repo_with_an_unreadable_index: Repo
    ) -> None:
        view = repo_with_an_unreadable_index.closings.check(TICKET)

        assert view.blockers == (
            'branch feature has 1 commits on no remote',
            'branch feature could not be checked: git could not read the working-tree status',
        )


class TestWhenGitIsMissing:
    @pytest.fixture
    def ticket_branch(self) -> str:
        return CHECKED_OUT

    @pytest.fixture
    def repo_without_git(self, repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
        monkeypatch.setenv('PATH', str(tmp_path.joinpath('no-binaries')))
        return replace(repo, closings=replace(repo.closings, workspace=workspace_at(repo.root)))

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
    UNSHIPPED = Closing(gotchas=())
    FOUR_GOTCHAS = ('one', 'two', 'three', 'four')
    OVER_THE_GOTCHA_LIMIT = CLOSING.model_copy(update={'gotchas': FOUR_GOTCHAS})
    LEAKING = CLOSING.model_copy(
        update={'gotchas': ('token=abc123 was in the log',), 'pr': 'https://bot:hunter2@x/pull/7'}
    )

    @pytest.fixture
    def repo_with_an_older_archive(self, repo: Repo) -> Repo:
        archives = repo.state.joinpath('archives')
        archives.mkdir(parents=True)
        archives.joinpath(f'{SLUG}.md').write_text('# older\n', encoding='utf-8')
        return repo

    @pytest.fixture
    def closed(self, repo: Repo) -> CloseView:
        return repo.closings.close(TICKET, CLOSING)

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

    def test_close_returns_the_archive_for_the_agent_to_write(self, repo: Repo) -> None:
        head = repo.git('rev-parse', 'HEAD')

        view = repo.closings.close(TICKET, CLOSING)

        assert view.archive is not None
        assert view.text == f'closed {SLUG}; archive at {ARCHIVE}\n'
        assert view.archive.record_path == f'.mightymodels/archives/{SLUG}.json'
        title, shipped, *rest = view.archive.markdown.splitlines()
        assert title == f'# {SLUG}'
        assert shipped.split(' · ') == [
            'shipped: Retry queue drains in under a second',
            'PR: https://x/pull/7',
            'tracker: #42',
            f'pruned: {view.archive.record.closed_at[:10]}',
            f'head: {head[:12]}',
        ]
        assert rest == [
            'tasks: T1 (engineer 1); C1 (engineer 1, architect 1)',
            'checks: 1 contract commands, 1 passing at last run',
            'review: none',
            'agents: 0 runs',
            'answers: 0 recorded through ask_user',
            'decisions:',
            '- none recorded',
            'gotchas:',
            '- the backoff floor is load-bearing',
            f'details: archives/{SLUG}.json',
        ]
        assert not repo.state.joinpath('archives').exists()

    def test_close_needs_a_shipped_line(self, repo: Repo) -> None:
        with pytest.raises(ShippedRequiredError) as refusal:
            repo.closings.close(TICKET, self.UNSHIPPED)

        assert 'shipped is required' in str(refusal.value)
        assert repo.ticket_status() == 'in-progress'

    def test_more_than_three_gotchas_are_refused(self, repo: Repo) -> None:
        with pytest.raises(TooManyGotchasError) as refusal:
            repo.closings.close(TICKET, self.OVER_THE_GOTCHA_LIMIT)

        assert refusal.value.given == len(self.FOUR_GOTCHAS)
        assert 'at most 3 gotchas' in str(refusal.value)
        assert repo.ticket_status() == 'in-progress'

    def test_secrets_in_closing_lines_are_redacted(self, repo: Repo) -> None:
        view = repo.closings.close(TICKET, self.LEAKING)

        assert view.archive is not None
        assert 'abc123' not in view.archive.markdown
        assert 'hunter2' not in view.archive.markdown
        assert 'abc123' not in view.archive.record.model_dump_json()

    def test_a_repeated_slug_gets_its_own_archive(self, repo_with_an_older_archive: Repo) -> None:
        view = repo_with_an_older_archive.closings.close(TICKET, CLOSING)

        assert view.archive is not None
        assert repo_with_an_older_archive.recorded_archive() == (
            f'.mightymodels/archives/{SLUG}-2.md'
        )
        assert view.archive.record_path == f'.mightymodels/archives/{SLUG}-2.json'
        assert view.archive.markdown.endswith(f'details: archives/{SLUG}-2.json\n')

    @pytest.mark.usefixtures('closed')
    def test_check_answers_for_a_closed_ticket(self, repo: Repo) -> None:
        view = repo.closings.check(TICKET)

        assert (view.blocked, view.text) == (False, f'{SLUG} has no live work\n')
        assert repo.ticket_status() == 'closed'

    def test_a_path_shaped_slug_is_refused(
        self, connected_server: StateServer, tree_after_the_connect: dict[str, bytes]
    ) -> None:
        (refused,) = connected_server.call(('close', {'action': 'check', 'slug': '..'}))

        assert refused.is_error
        assert connected_server.files_on_disk() == tree_after_the_connect


class TestAClosedTicket:
    CI_FIX = TaskStart(by=Implementer.ENGINEER, owned=('src/lint.py',))

    @pytest.fixture
    def closed(self, repo: Repo) -> Repo:
        repo.closings.close(TICKET, CLOSING)
        return repo

    def test_a_closed_ticket_takes_no_new_task_and_stays_closed(
        self, closed: Repo, task_service: TaskService
    ) -> None:
        with pytest.raises(StateError) as refusal:
            task_service.start(TICKET, 'C1', self.CI_FIX)

        assert f'{SLUG} is closed, and a closed ticket is final' in str(refusal.value)
        assert closed.ticket_status() == 'closed'


class TestLedgerDecisions:
    def test_the_archive_record_holds_each_ledger_decision_on_one_line(
        self, repo_with_a_ledger_decision: Repo
    ) -> None:
        view = repo_with_a_ledger_decision.closings.close(TICKET, CLOSING)

        assert view.archive is not None
        assert view.archive.record.model_dump(mode='json')['decisions'] == [
            {'text': 'keep the 10s floor', 'from': '20260928-queue e2'}
        ]


class TestTheLongestArchive:
    FOUR_LINES_ONE_BLANK = CLOSING.model_copy(
        update={'gotchas': ('first', '   ', 'second\nline', 'third')}
    )
    REASONS: Mapping[str, str] = MappingProxyType(
        {f'F{number}': f'reason {number}' for number in range(1, 7)}
    )

    @pytest.fixture
    def repo_with_six_accepted_findings(self, repo: Repo) -> Repo:
        run = repo.review(findings=len(self.REASONS))
        decisions = {
            finding_id: Disposition(decision=Decision.ACCEPT_RISK, reason=reason)
            for finding_id, reason in self.REASONS.items()
        }
        repo.reviews.dispose(run, DisposePayload(by='user', decisions=decisions))
        return repo

    @pytest.mark.usefixtures('repo_with_a_ledger_decision')
    def test_ledger_decisions_come_first_and_review_reasons_fill_what_is_left_of_four(
        self, repo_with_six_accepted_findings: Repo
    ) -> None:
        view = repo_with_six_accepted_findings.closings.close(TICKET, self.FOUR_LINES_ONE_BLANK)

        assert view.archive is not None
        assert view.archive.markdown.splitlines()[7:12] == [
            'decisions:',
            '- keep the 10s floor (20260928-queue e2)',
            '- review F1: reason 1',
            '- review F2: reason 2',
            '- review F3: reason 3',
        ]

    def test_the_longest_archive_keeps_three_gotchas_and_four_decisions(
        self, repo_with_six_accepted_findings: Repo
    ) -> None:
        view = repo_with_six_accepted_findings.closings.close(TICKET, self.FOUR_LINES_ONE_BLANK)

        assert view.archive is not None
        lines = view.archive.markdown.splitlines()
        assert len(lines) <= ARCHIVE_LINES
        assert lines[7:] == [
            'decisions:',
            '- review F1: reason 1',
            '- review F2: reason 2',
            '- review F3: reason 3',
            '- review F4: reason 4',
            'gotchas:',
            '- first',
            '- second line',
            '- third',
            f'details: archives/{SLUG}.json',
        ]
        assert view.archive.record.gotchas == ('first', 'second line', 'third')


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
