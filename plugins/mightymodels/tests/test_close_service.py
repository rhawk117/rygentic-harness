"""The close service on the close store and the git history kept in memory.

What needs a repository on disk or the stored row is in test_close_in_a_repository.py, and the
tool is in test_close_tool.py.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Self

import pytest
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.tools.close.rendering import ARCHIVE_LINES
from mightymodels_plugin.tools.close.schema import CloseView, Closing
from mightymodels_plugin.tools.close.service import (
    CloseService,
    ShippedRequiredError,
    TooManyGotchasError,
)
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
from mightymodels_plugin.tools.task.schema import Implementer, Status, TaskStart
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.task.store import Attempt, Transition
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
OLD = 'a' * 40
CHECKED_OUT = 'feature'
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
    git: InMemoryGit

    @property
    def root(self) -> Path:
        return self.closings.workspace.root

    @property
    def state(self) -> Path:
        return self.root.joinpath('.mightymodels')

    def head(self) -> str:
        return self.git.commits[-1].sha

    def seeing(self, git: InMemoryGit) -> Self:
        return replace(self, git=git, closings=replace(self.closings, git=git))

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
        with self.closings.store.transaction() as repository:
            repository.recorded.tickets.mark_in_progress(TICKET)
            for worker in workers:
                attempt = Attempt(worker=worker, mode=None, owned=['queue.py'])
                repository.recorded.tasks.record_start(TICKET, started, attempt)
        with self.closings.store.transaction() as repository:
            repository.recorded.tasks.record_mark(TICKET, transition_to(task_id, after))

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
        with self.closings.store.transaction() as repository:
            return repository.recorded.tickets.staged_ticket(TICKET).status


@pytest.fixture
def ticket_branch() -> str:
    return 'main'


@pytest.fixture
def in_memory_git() -> InMemoryGit:
    return InMemoryGit(branch=CHECKED_OUT)


@pytest.fixture
def staged(
    in_memory_close_service: CloseService,
    in_memory_ticket_service: TicketService,
    in_memory_contract_service: ContractService,
    in_memory_review_service: ReviewService,
    in_memory_git: InMemoryGit,
    ticket_branch: str,
) -> Repo:
    space = Repo(
        closings=in_memory_close_service,
        tickets=in_memory_ticket_service,
        contracts=in_memory_contract_service,
        reviews=in_memory_review_service,
        git=in_memory_git,
    )
    space.stage(ticket_branch)
    space.approve_with_a_passing_receipt('T1.AC-1', ('uv', 'run', 'pytest'))
    return space


@pytest.fixture
def committed(staged: Repo) -> Repo:
    staged.git.commit('queue.py')
    return staged


@pytest.fixture
def repo(committed: Repo) -> Repo:
    committed.record_verified_work()
    return committed


@pytest.fixture
def repo_with_a_ledger_decision(
    repo: Repo, in_memory_investigation_service: InvestigationService
) -> Repo:
    in_memory_investigation_service.start(LEDGER_TARGET, started=LEDGER_STARTED)
    in_memory_investigation_service.add(Slug(LEDGER), 1, [LEDGER_DECISION])
    with repo.closings.store.transaction() as repository:
        section = repository.recorded.tickets.staged_ticket(TICKET).ticket
        repository.recorded.tickets.stage(TICKET, section, [LEDGER])
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
    def in_memory_git(self) -> InMemoryGit:
        return InMemoryGit(branch=CHECKED_OUT, branches=[CHECKED_OUT], unpushed={CHECKED_OUT: 1})

    @pytest.fixture
    def repo_with_an_uncommitted_change(self, repo: Repo) -> Repo:
        return repo.seeing(replace(repo.git, dirty=['queue.py']))

    @pytest.fixture
    def repo_with_the_branch_on_a_remote(self, repo: Repo) -> Repo:
        return repo.seeing(replace(repo.git, unpushed={CHECKED_OUT: 0}))

    @pytest.fixture
    def repo_on_another_branch_with_an_uncommitted_change(
        self, repo_with_an_uncommitted_change: Repo
    ) -> Repo:
        elsewhere = replace(repo_with_an_uncommitted_change.git, branch='elsewhere')
        return repo_with_an_uncommitted_change.seeing(elsewhere)

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
    def in_memory_git(self) -> InMemoryGit:
        return InMemoryGit(branch=CHECKED_OUT, branches=[CHECKED_OUT], unpushed={CHECKED_OUT: 1})

    @pytest.fixture
    def repo_with_the_branch_deleted(self, repo: Repo) -> Repo:
        return repo.seeing(replace(repo.git, branch='elsewhere', branches=[]))

    @pytest.fixture
    def repo_whose_unpushed_commits_git_cannot_count(self, repo: Repo) -> Repo:
        return repo.seeing(replace(repo.git, unpushed={}))

    @pytest.fixture
    def repo_whose_status_git_cannot_read(self, repo: Repo) -> Repo:
        return repo.seeing(replace(repo.git, dirty=None))

    def test_a_branch_that_is_no_longer_in_the_repository_does_not_block(
        self, repo_with_the_branch_deleted: Repo
    ) -> None:
        view = repo_with_the_branch_deleted.closings.check(TICKET)

        assert (view.blocked, view.blockers) == (False, ())

    def test_a_branch_whose_unpushed_commits_git_cannot_count_blocks(
        self, repo_whose_unpushed_commits_git_cannot_count: Repo
    ) -> None:
        view = repo_whose_unpushed_commits_git_cannot_count.closings.check(TICKET)

        assert view.blockers == (
            'branch feature could not be checked: git could not count its commits on no remote',
        )

    def test_a_checked_out_branch_whose_status_git_cannot_read_blocks(
        self, repo_whose_status_git_cannot_read: Repo
    ) -> None:
        view = repo_whose_status_git_cannot_read.closings.check(TICKET)

        assert view.blockers == (
            'branch feature has 1 commits on no remote',
            'branch feature could not be checked: git could not read the working-tree status',
        )


class TestClose:
    UNSHIPPED = Closing(gotchas=())
    FOUR_GOTCHAS = ('one', 'two', 'three', 'four')
    OVER_THE_GOTCHA_LIMIT = CLOSING.model_copy(update={'gotchas': FOUR_GOTCHAS})
    LEAKING = CLOSING.model_copy(
        update={'gotchas': ('token=abc123 was in the log',), 'pr': 'https://bot:hunter2@x/pull/7'}
    )

    @pytest.fixture
    def closed(self, repo: Repo) -> CloseView:
        return repo.closings.close(TICKET, CLOSING)

    def test_close_returns_the_archive_for_the_agent_to_write(self, repo: Repo) -> None:
        head = repo.head()

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

    @pytest.mark.usefixtures('closed')
    def test_check_answers_for_a_closed_ticket(self, repo: Repo) -> None:
        view = repo.closings.check(TICKET)

        assert (view.blocked, view.text) == (False, f'{SLUG} has no live work\n')
        assert repo.ticket_status() == 'closed'


class TestAClosedTicket:
    CI_FIX = TaskStart(by=Implementer.ENGINEER, owned=('src/lint.py',))

    @pytest.fixture
    def closed(self, repo: Repo) -> Repo:
        repo.closings.close(TICKET, CLOSING)
        return repo

    def test_a_closed_ticket_takes_no_new_task_and_stays_closed(
        self, closed: Repo, in_memory_task_service: TaskService
    ) -> None:
        with pytest.raises(StateError) as refusal:
            in_memory_task_service.start(TICKET, 'C1', self.CI_FIX)

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
