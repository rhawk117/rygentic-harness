"""The close service on the close store and the git history kept in memory.

What needs a repository on disk or the stored row is in test_close_in_a_repository.py, and the
tool is in test_close_tool.py.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

import pytest
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.tools.close.rendering import ARCHIVE_LINES
from mightymodels_plugin.tools.close.schema import CloseView, Closing
from mightymodels_plugin.tools.close.service import ShippedRequiredError, TooManyGotchasError
from mightymodels_plugin.tools.close.tests.repo import (
    CHECKED_OUT,
    OLD,
    REVIEWED,
    SLUG,
    TICKET,
    CloseRepo,
)
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
    ResolvePayload,
    Result,
)
from mightymodels_plugin.tools.task.schema import Implementer, Status, TaskStart
from mightymodels_plugin.tools.task.service import TaskService

ARCHIVE = f'.mightymodels/archives/{SLUG}.md'
LEDGER = '20260928-queue'
LEDGER_TARGET = InvestigationStart(target='queue', kind=TargetKind.BEHAVIOR)
LEDGER_STARTED = datetime(2026, 9, 28, tzinfo=UTC)
LEDGER_DECISION = LedgerEntry(
    kind=EntryKind.DECISION, text='keep the\n10s floor', source=Source.USER
)
CLOSING = Closing(
    shipped='Retry queue drains in under a second',
    pr='https://x/pull/7',
    gotchas=('the backoff floor is load-bearing',),
)


@pytest.fixture
def ticket_branch() -> str:
    return 'main'


@pytest.fixture
def in_memory_git() -> InMemoryGit:
    return InMemoryGit(branch=CHECKED_OUT)


@pytest.fixture
def repo_with_a_ledger_decision(
    close_repo: CloseRepo, in_memory_investigation_service: InvestigationService
) -> CloseRepo:
    in_memory_investigation_service.start(LEDGER_TARGET, started=LEDGER_STARTED)
    in_memory_investigation_service.add(Slug(LEDGER), 1, [LEDGER_DECISION])
    with close_repo.closings.store.transaction() as repository:
        section = repository.recorded.tickets.staged_ticket(TICKET).ticket
        repository.recorded.tickets.stage(TICKET, section, [LEDGER])
    return close_repo


class TestCheck:
    def test_a_ticket_with_everything_verified_has_no_live_work(
        self, close_repo: CloseRepo
    ) -> None:
        view = close_repo.closings.check(TICKET)

        assert (view.blocked, view.text) == (False, f'{SLUG} has no live work\n')

    def test_a_staged_ticket_without_verified_work_cannot_close(
        self, committed_close_repo: CloseRepo
    ) -> None:
        view = committed_close_repo.closings.close(TICKET, CLOSING)

        assert view.blocked
        assert view.blockers == (
            'T1 has contract commands but was never started',
            'no verified task work is recorded',
        )


class TestUnverifiedTasks:
    @pytest.fixture
    def repo_with_a_blocked_task(self, committed_close_repo: CloseRepo) -> CloseRepo:
        committed_close_repo.record_task('T1', Status.BLOCKED, Implementer.ENGINEER)
        return committed_close_repo

    @pytest.fixture
    def repo_with_a_blocked_task_and_a_live_debug(
        self, repo_with_a_blocked_task: CloseRepo
    ) -> CloseRepo:
        note = repo_with_a_blocked_task.state.joinpath(SLUG, 'whats-broken.md')
        note.write_text('hypothesis\n', encoding='utf-8')
        return repo_with_a_blocked_task

    def test_an_unverified_task_blocks(self, repo_with_a_blocked_task: CloseRepo) -> None:
        view = repo_with_a_blocked_task.closings.check(TICKET)

        assert view.blocked
        assert view.text == 'live work remains\n  - T1 is blocked, not verified\n'

    def test_unverified_tasks_and_a_live_debug_block_closing(
        self, repo_with_a_blocked_task_and_a_live_debug: CloseRepo
    ) -> None:
        view = repo_with_a_blocked_task_and_a_live_debug.closings.close(TICKET, CLOSING)

        assert view.blocked
        assert 'T1 is blocked, not verified' in view.text
        assert 'whats-broken.md is present' in view.text
        assert not repo_with_a_blocked_task_and_a_live_debug.state.joinpath('archives').exists()


class TestALiveDebug:
    @pytest.fixture
    def repo_with_a_live_debug(self, close_repo: CloseRepo) -> CloseRepo:
        close_repo.state.joinpath(SLUG, 'whats-broken.md').write_text(
            'hypothesis\n', encoding='utf-8'
        )
        return close_repo

    def test_a_live_debug_note_blocks(self, repo_with_a_live_debug: CloseRepo) -> None:
        view = repo_with_a_live_debug.closings.check(TICKET)

        assert view.blockers == ('whats-broken.md is present: a debug is still live',)


class TestReviewFindings:
    @pytest.fixture
    def repo_with_an_unfixed_and_an_undecided_finding(self, close_repo: CloseRepo) -> CloseRepo:
        run = close_repo.review(findings=2)
        decisions = {'F1': Disposition(decision=Decision.FIX)}
        close_repo.reviews.dispose(run, DisposePayload(by='user', decisions=decisions))
        return close_repo

    @pytest.fixture
    def repo_with_every_finding_settled(
        self, repo_with_an_unfixed_and_an_undecided_finding: CloseRepo
    ) -> CloseRepo:
        space = repo_with_an_unfixed_and_an_undecided_finding
        run = RunId(REVIEWED.strftime('%Y%m%d-%H%M%S'))
        dismissed = {'F2': Disposition(decision=Decision.DISMISS, reason='not reachable')}
        space.reviews.dispose(run, DisposePayload(by='user', decisions=dismissed))
        space.reviews.resolve(run, ResolvePayload(finding='F1', result=Result.FIXED, commit=OLD))
        return space

    def test_undecided_and_unfixed_review_findings_block(
        self, repo_with_an_unfixed_and_an_undecided_finding: CloseRepo
    ) -> None:
        view = repo_with_an_unfixed_and_an_undecided_finding.closings.check(TICKET)

        assert 'review finding F2 has no decision' in view.text
        assert 'review finding F1 was chosen for fixing and is not fixed' in view.text

    def test_a_fixed_finding_and_a_dismissed_one_no_longer_block(
        self, repo_with_every_finding_settled: CloseRepo
    ) -> None:
        view = repo_with_every_finding_settled.closings.close(TICKET, CLOSING)

        assert not view.blocked
        assert view.archive is not None
        assert 'review: run 20260928-120000 (deep), 2 findings; fixed F1; dismiss F2' in (
            view.archive.markdown
        )
        assert '- review F2: not reachable' in view.archive.markdown


class TestClose:
    UNSHIPPED = Closing(gotchas=())
    FOUR_GOTCHAS = ('one', 'two', 'three', 'four')
    OVER_THE_GOTCHA_LIMIT = CLOSING.model_copy(update={'gotchas': FOUR_GOTCHAS})
    LEAKING = CLOSING.model_copy(
        update={'gotchas': ('token=abc123 was in the log',), 'pr': 'https://bot:hunter2@x/pull/7'}
    )

    @pytest.fixture
    def closed(self, close_repo: CloseRepo) -> CloseView:
        return close_repo.closings.close(TICKET, CLOSING)

    def test_close_returns_the_archive_for_the_agent_to_write(self, close_repo: CloseRepo) -> None:
        head = close_repo.head()

        view = close_repo.closings.close(TICKET, CLOSING)

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
        assert not close_repo.state.joinpath('archives').exists()

    def test_close_needs_a_shipped_line(self, close_repo: CloseRepo) -> None:
        with pytest.raises(ShippedRequiredError) as refusal:
            close_repo.closings.close(TICKET, self.UNSHIPPED)

        assert 'shipped is required' in str(refusal.value)
        assert close_repo.ticket_status() == 'in-progress'

    def test_more_than_three_gotchas_are_refused(self, close_repo: CloseRepo) -> None:
        with pytest.raises(TooManyGotchasError) as refusal:
            close_repo.closings.close(TICKET, self.OVER_THE_GOTCHA_LIMIT)

        assert refusal.value.given == len(self.FOUR_GOTCHAS)
        assert 'at most 3 gotchas' in str(refusal.value)
        assert close_repo.ticket_status() == 'in-progress'

    def test_secrets_in_closing_lines_are_redacted(self, close_repo: CloseRepo) -> None:
        view = close_repo.closings.close(TICKET, self.LEAKING)

        assert view.archive is not None
        assert 'abc123' not in view.archive.markdown
        assert 'hunter2' not in view.archive.markdown
        assert 'abc123' not in view.archive.record.model_dump_json()

    @pytest.mark.usefixtures('closed')
    def test_check_answers_for_a_closed_ticket(self, close_repo: CloseRepo) -> None:
        view = close_repo.closings.check(TICKET)

        assert (view.blocked, view.text) == (False, f'{SLUG} has no live work\n')
        assert close_repo.ticket_status() == 'closed'


class TestAClosedTicket:
    CI_FIX = TaskStart(by=Implementer.ENGINEER, owned=('src/lint.py',), acceptance=('AC-1',))

    @pytest.fixture
    def closed(self, close_repo: CloseRepo) -> CloseRepo:
        close_repo.closings.close(TICKET, CLOSING)
        return close_repo

    def test_a_closed_ticket_takes_no_new_task_and_stays_closed(
        self, closed: CloseRepo, in_memory_task_service: TaskService
    ) -> None:
        with pytest.raises(StateError) as refusal:
            in_memory_task_service.start(TICKET, 'C1', self.CI_FIX)

        assert f'{SLUG} is closed, and a closed ticket is final' in str(refusal.value)
        assert closed.ticket_status() == 'closed'


class TestLedgerDecisions:
    def test_the_archive_record_holds_each_ledger_decision_on_one_line(
        self, repo_with_a_ledger_decision: CloseRepo
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
    def repo_with_six_accepted_findings(self, close_repo: CloseRepo) -> CloseRepo:
        run = close_repo.review(findings=len(self.REASONS))
        decisions = {
            finding_id: Disposition(decision=Decision.ACCEPT_RISK, reason=reason)
            for finding_id, reason in self.REASONS.items()
        }
        close_repo.reviews.dispose(run, DisposePayload(by='user', decisions=decisions))
        return close_repo

    @pytest.mark.usefixtures('repo_with_a_ledger_decision')
    def test_ledger_decisions_come_first_and_review_reasons_fill_what_is_left_of_four(
        self, repo_with_six_accepted_findings: CloseRepo
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
        self, repo_with_six_accepted_findings: CloseRepo
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
