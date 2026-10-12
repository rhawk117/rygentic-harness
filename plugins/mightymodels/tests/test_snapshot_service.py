"""The snapshot service on the snapshot store and the git history kept in memory.

What needs a repository on disk is in test_snapshot_in_a_repository.py, and the tool is in
test_snapshot_tool.py.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Self

import pytest
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.core.workspace import Workspace
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
    ReviewScope,
    StartPayload,
)
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.snapshot.schema import DEFAULT_LIMIT, SnapshotView
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.tools.task.schema import Implementer, Status, TaskMark, TaskStart
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.task.store import Attempt, Transition
from mightymodels_plugin.tools.ticket.repository import NotStagedError
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
OLD = 'a' * 40
BRANCH = 'fix/retry'
LEDGER = '20260928-queue'
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': BRANCH,
        'context': ['drain loop sleeps between batches'],
    }
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


@dataclass(frozen=True, slots=True, kw_only=True)
class Handoff:
    snapshots: SnapshotService
    tasks: TaskService
    contracts: ContractService
    reviews: ReviewService
    git: InMemoryGit

    @property
    def root(self) -> Path:
        return self.snapshots.workspace.root

    def head(self) -> str:
        return self.git.commits[-1].sha

    def with_a_tree_of(self, *, dirty: Sequence[str] = (), untracked: Sequence[str] = ()) -> Self:
        git = replace(self.git, dirty=dirty, untracked=untracked)
        return replace(self, git=git, snapshots=replace(self.snapshots, git=git))

    def take(self, limit: int = DEFAULT_LIMIT) -> SnapshotView:
        return self.snapshots.take(TICKET, limit)

    def approve(self, commands: Mapping[str, tuple[str, ...]]) -> None:
        self.contracts.approve(
            TICKET,
            [
                ContractCommand(id=command_id, argv=argv, approved_by='user')
                for command_id, argv in commands.items()
            ],
        )

    def record_pass(self, command_id: str, head: str) -> None:
        receipt = Receipt(
            id=command_id,
            argv=('true',),
            outcome=Outcome.PASSED,
            exit=0,
            duration_ms=0,
            stdout_tail='',
            stderr_tail='',
            digest='',
            head=head,
            phase=Phase.TASK,
            at=now(),
        )
        with self.contracts.store.transaction() as repository:
            repository.record(TICKET, [receipt])

    def record_failed_attempt(self, task_id: str, reason: str) -> None:
        started = Transition(
            task_id=task_id,
            before=Status.PENDING,
            after=Status.IN_PROGRESS,
            reasons=['by engineer'],
            head=OLD,
            at=now(),
        )
        failed = Transition(
            task_id=task_id,
            before=Status.IN_PROGRESS,
            after=Status.FAILED,
            reasons=[reason],
            head=OLD,
            at=now(),
        )
        attempt = Attempt(worker=Implementer.ENGINEER, mode=None, owned=['queue.py'])
        with self.tasks.store.transaction() as repository:
            repository.record_start(TICKET, started, attempt)
        with self.tasks.store.transaction() as repository:
            repository.record_mark(TICKET, failed)

    def review(self, started: datetime, findings: int) -> RunId:
        payload = StartPayload(
            scope=ReviewScope.CODEBASE, depth=Depth.DEEP, emphasis=Emphasis.BALANCED, slug=TICKET
        )
        run = RunId(str(self.reviews.start(payload, started=started).run_id))
        self.reviews.add_findings(run, [reported_finding(n) for n in range(1, findings + 1)])
        return run


@pytest.fixture
def in_memory_git() -> InMemoryGit:
    return InMemoryGit(branch=BRANCH)


@pytest.fixture
def handoff(
    in_memory_snapshot_service: SnapshotService,
    in_memory_task_service: TaskService,
    in_memory_contract_service: ContractService,
    in_memory_review_service: ReviewService,
    in_memory_ticket_service: TicketService,
    in_memory_git: InMemoryGit,
) -> Handoff:
    in_memory_ticket_service.write(TICKET, ANSWERS)
    in_memory_ticket_service.validate(TICKET)
    return Handoff(
        snapshots=in_memory_snapshot_service,
        tasks=in_memory_task_service,
        contracts=in_memory_contract_service,
        reviews=in_memory_review_service,
        git=in_memory_git,
    )


@pytest.fixture
def repo(handoff: Handoff) -> Handoff:
    handoff.git.commit('queue.py')
    return handoff


@pytest.fixture
def repo_linking_an_investigation(repo: Handoff) -> Handoff:
    with repo.snapshots.store.transaction() as repository:
        section = repository.tickets.staged_ticket(TICKET).ticket
        repository.tickets.stage(TICKET, section, [LEDGER])
    return repo


class TestAnUnstagedTicket:
    def test_an_unstaged_ticket_writes_nothing(
        self, in_memory_snapshot_service: SnapshotService, gitless_workspace: Workspace
    ) -> None:
        with pytest.raises(NotStagedError) as refusal:
            in_memory_snapshot_service.take(TICKET, DEFAULT_LIMIT)

        assert f'{SLUG} is not staged' in str(refusal.value)
        assert not gitless_workspace.root.joinpath('.mightymodels', SLUG, 'handoffs').exists()


class TestAStagedTicket:
    def test_missing_sources_read_as_empty(self, repo_linking_an_investigation: Handoff) -> None:
        view = repo_linking_an_investigation.take()
        record = view.record.model_dump(mode='json')

        assert record['repository']['branch'] == 'fix/retry'
        assert (record['checks'], record['subagents'], record['review']) == ([], [], None)
        assert record['warnings'] == ['investigation 20260928-queue is missing']
        assert '- no receipts yet' in view.markdown

    def test_the_sections_no_row_fills_yet_read_empty(self, repo: Handoff) -> None:
        view = repo.take()
        record = view.record.model_dump(mode='json')

        assert [record[key] for key in ('decisions', 'open_questions', 'answers')] == [[], [], []]
        assert record['warnings'] == []
        assert '## Warnings' not in view.markdown

    def test_the_view_names_the_two_files_the_agent_writes(self, repo: Handoff) -> None:
        view = repo.take()

        assert (view.markdown_path, view.record_path) == (
            f'.mightymodels/{SLUG}/handoffs/snapshot.md',
            f'.mightymodels/{SLUG}/handoffs/snapshot.json',
        )
        assert not repo.root.joinpath('.mightymodels', SLUG, 'handoffs').exists()

    def test_the_header_names_the_ticket_and_the_repository(self, repo: Handoff) -> None:
        head = repo.head()

        lines = repo.take().markdown.splitlines()

        assert lines[0] == f'# Snapshot for {SLUG}'
        assert lines[3:5] == [
            'Ticket: Retry queue drains slowly (status staged).',
            f'Repository: fix/retry at {head[:12]}; tree clean.',
        ]


class TestLinkedLedgers:
    TARGET = InvestigationStart(target='queue', kind=TargetKind.BEHAVIOR)
    STARTED = datetime(2026, 9, 28, tzinfo=UTC)
    QUESTION = LedgerEntry(kind=EntryKind.OPEN, text='is backoff capped?', source=Source.PRIMARY)
    DECISION = LedgerEntry(kind=EntryKind.DECISION, text='keep the 10s floor', source=Source.USER)
    ANSWER = LedgerEntry(
        kind=EntryKind.KNOWN,
        text='cap is 60s',
        source=Source.CODE_SCOUT,
        cite='queue.py:9',
        supersedes=(2,),
    )
    LATER_QUESTION = LedgerEntry(
        kind=EntryKind.OPEN,
        text='does the cap hold under load?',
        source=Source.USER,
        cite='queue.py:9',
    )
    LATER_DECISION = LedgerEntry(kind=EntryKind.DECISION, text='ship the cap', source=Source.USER)

    @pytest.fixture
    def repo_with_a_superseded_question(
        self,
        repo_linking_an_investigation: Handoff,
        in_memory_investigation_service: InvestigationService,
    ) -> Handoff:
        in_memory_investigation_service.start(self.TARGET, started=self.STARTED)
        in_memory_investigation_service.add(Slug(LEDGER), 1, [self.QUESTION, self.DECISION])
        in_memory_investigation_service.add(Slug(LEDGER), 2, [self.ANSWER])
        return repo_linking_an_investigation

    @pytest.fixture
    def repo_with_two_decisions_and_a_cited_question(
        self,
        repo_with_a_superseded_question: Handoff,
        in_memory_investigation_service: InvestigationService,
    ) -> Handoff:
        in_memory_investigation_service.add(
            Slug(LEDGER), 3, [self.LATER_QUESTION, self.LATER_DECISION]
        )
        return repo_with_a_superseded_question

    def test_ledger_decisions_and_questions_skip_superseded_entries(
        self, repo_with_a_superseded_question: Handoff
    ) -> None:
        record = repo_with_a_superseded_question.take().record.model_dump(mode='json')

        assert record['open_questions'] == []
        assert record['decisions'] == [
            {
                'kind': 'decision',
                'text': 'keep the 10s floor',
                'cite': None,
                'from': '20260928-queue e3',
            },
        ]

    def test_a_linked_ledger_with_entries_is_not_a_warning(
        self, repo_with_a_superseded_question: Handoff
    ) -> None:
        assert repo_with_a_superseded_question.take().record.warnings == ()

    def test_ledger_lines_name_their_cite_and_the_entry_they_came_from(
        self, repo_with_two_decisions_and_a_cited_question: Handoff
    ) -> None:
        markdown = repo_with_two_decisions_and_a_cited_question.take().markdown

        assert (
            '## Decisions\n\n'
            '- keep the 10s floor (20260928-queue e3)\n'
            '- ship the cap (20260928-queue e6)\n'
        ) in markdown
        assert (
            '## Open questions\n\n'
            '- does the cap hold under load? [queue.py:9] (20260928-queue e5)\n'
        ) in markdown

    def test_the_limit_keeps_the_latest_ledger_decisions(
        self, repo_with_two_decisions_and_a_cited_question: Handoff
    ) -> None:
        record = repo_with_two_decisions_and_a_cited_question.take(limit=1).record

        assert [(line.text, line.origin) for line in record.decisions] == [
            ('ship the cap', '20260928-queue e6')
        ]


class TestChecks:
    COMMANDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
        {
            'T1.AC-1': ('uv', 'run', 'pytest', '-q'),
            'T1.AC-2': ('ruff', 'check'),
            'T2.AC-1': ('make', 'e2e'),
        }
    )

    @pytest.fixture
    def repo_with_a_current_and_a_stale_receipt(self, repo: Handoff) -> Handoff:
        repo.approve(self.COMMANDS)
        repo.record_pass('T1.AC-1', repo.head())
        repo.record_pass('T1.AC-2', OLD)
        return repo

    def test_checks_are_judged_at_head_and_passing_commands_are_kept(
        self, repo_with_a_current_and_a_stale_receipt: Handoff
    ) -> None:
        view = repo_with_a_current_and_a_stale_receipt.take()
        record = view.record.model_dump(mode='json')

        assert record['checks'] == [
            {'id': 'T1.AC-1', 'state': 'pass'},
            {'id': 'T1.AC-2', 'state': f'stale (pass at {OLD[:12]})'},
            {'id': 'T2.AC-1', 'state': 'never-run'},
        ]
        assert [work['id'] for work in record['works']] == ['T1.AC-1', 'T1.AC-2']
        assert '- T1.AC-1: `uv run pytest -q`' in view.markdown

    def test_the_limit_bounds_the_passing_commands(
        self, repo_with_a_current_and_a_stale_receipt: Handoff
    ) -> None:
        record = repo_with_a_current_and_a_stale_receipt.take(limit=1).record

        assert [work.id for work in record.works] == ['T1.AC-1']
        assert len(record.checks) == len(self.COMMANDS)


class TestTasks:
    @pytest.fixture
    def repo_with_a_blocked_task_and_an_unstarted_one(self, repo: Handoff) -> Handoff:
        repo.approve({'T2.AC-1': ('make',)})
        repo.tasks.start(
            TICKET,
            'T1',
            TaskStart(by=Implementer.ENGINEER, owned=('queue.py',), acceptance=('AC-1',)),
        )
        repo.tasks.mark(TICKET, 'T1', TaskMark(to=Status.BLOCKED, reason='T1.AC-1 fail at HEAD'))
        return repo

    @pytest.fixture
    def repo_with_two_failed_attempts(self, repo: Handoff) -> Handoff:
        repo.record_failed_attempt('T1', 'AC-1 still red')
        repo.record_failed_attempt('T2', 'AC-2 times out')
        return repo

    def test_open_tasks_include_contract_tasks_never_started(
        self, repo_with_a_blocked_task_and_an_unstarted_one: Handoff
    ) -> None:
        view = repo_with_a_blocked_task_and_an_unstarted_one.take()
        record = view.record.model_dump(mode='json')

        assert [(task['task'], task['status']) for task in record['tasks']] == [
            ('T1', 'blocked'),
            ('T2', 'not started'),
        ]
        assert '- T1 blocked (engineer 1 | T1.AC-1 fail at HEAD)' in view.markdown

    def test_failed_attempts_become_do_not_retry_lines(
        self, repo_with_two_failed_attempts: Handoff
    ) -> None:
        view = repo_with_two_failed_attempts.take()
        record = view.record.model_dump(mode='json')

        assert [entry['reason'] for entry in record['do_not_retry']] == [
            'AC-1 still red',
            'AC-2 times out',
        ]
        assert f'- T1 failed at {OLD[:12]}: AC-1 still red' in view.markdown

    def test_the_limit_keeps_the_latest_failed_attempts(
        self, repo_with_two_failed_attempts: Handoff
    ) -> None:
        record = repo_with_two_failed_attempts.take(limit=1).record

        assert [(entry.task, entry.to) for entry in record.do_not_retry] == [('T2', 'failed')]


class TestReview:
    EARLIER = datetime(2026, 9, 27, 12, tzinfo=UTC)
    LATEST = datetime(2026, 9, 28, 12, tzinfo=UTC)
    DECISIONS: Mapping[str, Disposition] = MappingProxyType(
        {
            'F1': Disposition(decision=Decision.FIX),
            'F2': Disposition(decision=Decision.ACCEPT_RISK, reason='internal only'),
        }
    )

    @pytest.fixture
    def repo_with_two_review_runs(self, repo: Handoff) -> Handoff:
        repo.review(self.EARLIER, findings=1)
        latest = repo.review(self.LATEST, findings=3)
        repo.reviews.dispose(latest, DisposePayload(by='user', decisions=dict(self.DECISIONS)))
        return repo

    def test_the_latest_review_run_reports_open_remediation(
        self, repo_with_two_review_runs: Handoff
    ) -> None:
        view = repo_with_two_review_runs.take()
        review = view.record.model_dump(mode='json')['review']

        assert (review['undecided'], review['remediation_open']) == (['F3'], ['F1'])
        assert review['decisions'] == [
            {'finding': 'F2', 'decision': 'accept-risk', 'reason': 'internal only'}
        ]

    def test_the_review_section_names_the_run_and_each_kept_decision(
        self, repo_with_two_review_runs: Handoff
    ) -> None:
        head = repo_with_two_review_runs.head()

        review = repo_with_two_review_runs.take().markdown.split('## Review\n\n')[1]

        assert review.splitlines() == [
            f'- run 20260928-120000 (deep) at {head[:12]}: 3 findings',
            '- undecided: F3',
            '- remediation open: F1',
            '- F2 accept-risk: internal only',
        ]


class TestADirtyTree:
    @pytest.fixture
    def repo_with_an_uncommitted_change(self, repo: Handoff) -> Handoff:
        return repo.with_a_tree_of(dirty=['queue.py'])

    @pytest.fixture
    def repo_with_three_untracked_files(self, repo: Handoff) -> Handoff:
        return repo.with_a_tree_of(untracked=['a.py', 'b.py', 'c.py'])

    def test_a_dirty_tree_is_listed(self, repo_with_an_uncommitted_change: Handoff) -> None:
        view = repo_with_an_uncommitted_change.take()
        repository = view.record.model_dump(mode='json')['repository']

        assert (repository['dirty_count'], repository['dirty']) == (1, ['queue.py'])
        assert '- changed: queue.py' in view.markdown

    def test_the_limit_bounds_the_listed_files_and_not_their_count(
        self, repo_with_three_untracked_files: Handoff
    ) -> None:
        view = repo_with_three_untracked_files.take(limit=2)

        assert (view.record.repository.dirty_count, view.record.repository.dirty) == (
            3,
            ('a.py', 'b.py'),
        )
        assert 'tree 3 changed.' in view.markdown
