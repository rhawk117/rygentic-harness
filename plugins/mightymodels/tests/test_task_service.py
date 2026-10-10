"""The `task` tool's service against a real git repository, moved from task_state.py's tests."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pytest
import sqlalchemy as sql
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.contract.repository import contract_transaction
from mightymodels_plugin.tools.contract.schema import ContractCommand, Phase, Receipt
from mightymodels_plugin.tools.contract.schema import Outcome as ReceiptOutcome
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.task.repository import task_transaction
from mightymodels_plugin.tools.task.schema import (
    TaskMark,
    TaskRecord,
    TaskStart,
    TaskVerification,
    TaskView,
)
from mightymodels_plugin.tools.task.service import TaskService, records_of
from mightymodels_plugin.tools.task.tables import AttemptRow, TaskRow, TransitionRow
from mightymodels_plugin.tools.ticket.repository import ticket_transaction
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.tools.ticket.tables import TicketRow
from pydantic import BaseModel, ValidationError

type GitRunner = Callable[..., str]

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
ADVANCED, BLOCKED, REJECTED = 0, 1, 2
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
TASK_TABLES = (TaskRow, AttemptRow, TransitionRow)
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': 'fix/retry-queue',
        'context': ['drain loop sleeps between batches'],
    }
)


LISTINGS: Mapping[str, Callable[..., TaskView]] = MappingProxyType(
    {'show': TaskService.show, 'ready': TaskService.ready}
)
CHANGES: Mapping[str, tuple[Callable[..., TaskView], type[BaseModel]]] = MappingProxyType(
    {
        'start': (TaskService.start, TaskStart),
        'verify': (TaskService.verify, TaskVerification),
        'mark': (TaskService.mark, TaskMark),
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Outcome:
    code: int
    out: str
    err: str


def act(
    tasks: TaskService, action: str, task_id: str | None, change: dict[str, object]
) -> TaskView:
    if action in LISTINGS:
        return LISTINGS[action](tasks, TICKET)
    service, model = CHANGES[action]
    return service(tasks, TICKET, task_id, model.model_validate(change))


def record_receipt(
    contracts: ContractService, command_id: str, outcome: str, head: str | None
) -> None:
    entry = Receipt(
        id=command_id,
        argv=('true',),
        outcome=ReceiptOutcome(outcome),
        exit=0,
        duration_ms=0,
        stdout_tail='',
        stderr_tail='',
        digest='',
        head=head,
        phase=Phase.TASK,
        at=now(),
    )
    with contract_transaction(contracts.database) as repository:
        repository.record(TICKET, [entry])


@dataclass(frozen=True, slots=True, kw_only=True)
class Repo:
    tasks: TaskService
    contracts: ContractService
    runner: GitRunner

    @property
    def root(self) -> Path:
        return self.tasks.workspace.root

    def git(self, *args: str) -> str:
        return self.runner(self.root, *IDENTITY, *args).strip()

    def commit(self, relative: str, text: str) -> str:
        path = self.root.joinpath(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        self.git('add', relative)
        self.git('commit', '-q', '-m', f'change {relative}')
        return self.git('rev-parse', 'HEAD')

    def run(self, action: str, task_id: str | None = None, **change: object) -> Outcome:
        try:
            view = act(self.tasks, action, task_id, change)
        except (StateError, ValidationError) as error:
            return Outcome(code=REJECTED, out='', err=str(error))
        return Outcome(code=ADVANCED if view.advanced else BLOCKED, out=view.text, err='')

    @property
    def ticket_dir(self) -> Path:
        return self.root.joinpath('.mightymodels', SLUG)

    def task(self, task_id: str) -> TaskRecord:
        with task_transaction(self.tasks.database) as repository:
            return records_of(repository, TICKET)[task_id]

    def transitions(self) -> list[tuple[str, str]]:
        query = sql.select(TransitionRow).order_by(TransitionRow.id)
        with self.tasks.database.transaction() as session:
            return [(row.before, row.after) for row in session.scalars(query)]

    def approve(self, *command_ids: str) -> None:
        commands = [
            ContractCommand(id=command_id, argv=('true',), approved_by='user')
            for command_id in command_ids
        ]
        self.contracts.approve(TICKET, commands)

    def receipt(self, command_id: str, outcome: str, head: str) -> None:
        record_receipt(self.contracts, command_id, outcome, head)
        if command_id.startswith('T'):
            task_id = command_id.split('.', 1)[0]
            self.done(task_id, head)

    def done(self, task_id: str, head: str) -> None:
        brief = self.ticket_dir.joinpath('briefs', f'task-{int(task_id[1:]):02d}.md')
        brief.parent.mkdir(exist_ok=True)
        asked = brief.read_text().split('## DONE', 1)[0] if brief.exists() else '## ASKED\n'
        brief.write_text(f'{asked}\n## DONE\ncommit: {head}\n')


@pytest.fixture
def repo(
    task_service: TaskService,
    ticket_service: TicketService,
    contract_service: ContractService,
    git: GitRunner,
) -> Repo:
    space = Repo(tasks=task_service, contracts=contract_service, runner=git)
    space.commit('src/queue.py', 'base\n')
    ticket_service.write(TICKET, ANSWERS)
    ticket_service.validate(TICKET)
    return space


@pytest.fixture
def unborn(
    task_service: TaskService,
    ticket_service: TicketService,
    contract_service: ContractService,
    git: GitRunner,
) -> Repo:
    ticket_service.write(TICKET, ANSWERS)
    ticket_service.validate(TICKET)
    return Repo(tasks=task_service, contracts=contract_service, runner=git)


def start(repo: Repo, worker: str = 'engineer') -> Outcome:
    return repo.run('start', 'T1', by=worker, owned=['src/queue.py'])


def test_start_records_the_attempt_and_its_base(repo: Repo) -> None:
    base = repo.git('rev-parse', 'HEAD')
    outcome = start(repo)
    task = repo.task('T1')
    assert outcome.code == ADVANCED
    assert (task.status, task.base, task.attempts) == (
        'in-progress',
        base,
        {'engineer': 1},
    )


def test_a_task_with_passing_receipts_and_owned_changes_verifies(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('verify', 'T1', commit=head)
    assert (outcome.code, outcome.out.strip()) == (ADVANCED, 'T1 verified')
    assert [after for _, after in repo.transitions()] == ['in-progress', 'verified']


def test_changes_outside_the_owned_set_block_the_task(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    repo.commit('src/queue.py', 'fixed\n')
    head = repo.commit('deploy/values.yaml', 'pool: 5\n')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('verify', 'T1', commit=head)
    assert outcome.code == BLOCKED
    assert 'changed outside the owned set: deploy/values.yaml' in outcome.out


def test_a_receipt_from_an_older_head_does_not_count(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    old = repo.git('rev-parse', 'HEAD')
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', old)
    outcome = repo.run('verify', 'T1', commit=head)
    assert outcome.code == BLOCKED
    assert 'T1.AC-1 has no receipt at the current HEAD' in outcome.out


def test_a_failing_receipt_blocks_the_task(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'fail', head)
    outcome = repo.run('verify', 'T1', commit=head)
    assert 'T1.AC-1 fail at HEAD' in outcome.out


def test_brief_criteria_need_a_command_or_a_citation(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    brief = repo.ticket_dir.joinpath('briefs', 'task-01.md')
    brief.parent.mkdir()
    brief.write_text('## ASKED\nacceptance:\n  - AC-1: tests pass\n  - AC-2: docs updated\n')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    blocked = repo.run('verify', 'T1', commit=head)
    start(repo)
    verified = repo.run('verify', 'T1', commit=head, assertions={'AC-2': 'README.md:12'})
    assert 'AC-2 has neither a contract command nor a citation' in blocked.out
    assert verified.code == ADVANCED


def test_a_task_needs_some_proof(repo: Repo) -> None:
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    outcome = repo.run('verify', 'T1', commit=head)
    assert 'no contract command and no cited assertion proves this task' in outcome.out


def test_architect_recovers_a_task_only_once(repo: Repo) -> None:
    start(repo)
    repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
    start(repo, 'architect')
    repo.run('mark', 'T1', to='blocked', reason='needs a decision')
    outcome = start(repo, 'architect')
    assert outcome.code == REJECTED
    assert 'route it to whats-broken' in outcome.err


def test_a_verified_task_cannot_restart(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    repo.run('verify', 'T1', commit=head)
    outcome = start(repo)
    assert 'cannot move from verified to in-progress' in outcome.err


def test_option_shaped_revisions_are_refused(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    outcome = repo.run('verify', 'T1', commit='--output=/tmp/pwned')
    assert outcome.code == REJECTED
    assert 'is not a plain revision name' in outcome.err


def test_an_unstaged_ticket_is_refused(repo: Repo) -> None:
    with repo.tasks.database.transaction() as session:
        session.execute(sql.delete(TicketRow))
    outcome = start(repo)
    assert 'stage the ticket with open-ticket first' in outcome.err


def test_an_approved_scope_expansion_allows_one_more_architect_pass(repo: Repo) -> None:
    start(repo)
    repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
    start(repo, 'architect')
    repo.run('mark', 'T1', to='blocked', reason='scope-expansion-requested')
    expanded = ('src/queue.py', 'src/client.py')
    outcome = repo.run('start', 'T1', by='architect', owned=expanded, mode='systemic-refactor')
    task = repo.task('T1')
    assert outcome.code == ADVANCED
    assert list(task.owned) == ['src/client.py', 'src/queue.py']


def verified_task(repo: Repo) -> str:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    repo.run('verify', 'T1', commit=head)
    return head


def test_ready_when_every_task_is_verified_at_head(repo: Repo) -> None:
    head = verified_task(repo)
    outcome = repo.run('ready')
    assert (outcome.code, outcome.out) == (ADVANCED, f'ready at {head[:12]}\n')


def test_a_contract_task_never_started_is_not_ready(repo: Repo) -> None:
    verified_task(repo)
    repo.approve('T1.AC-1', 'T2.AC-1')
    outcome = repo.run('ready')
    assert outcome.code == BLOCKED
    assert 'T2 has contract commands but was never started' in outcome.out


def test_a_ci_fix_makes_earlier_receipts_stale(repo: Repo) -> None:
    verified_task(repo)
    repo.run('start', 'C1', by='engineer', owned=['src/lint.py'])
    repo.commit('src/lint.py', 'clean\n')
    outcome = repo.run('ready')
    assert outcome.code == BLOCKED
    assert outcome.out.splitlines()[1:] == ['  - T1.AC-1 has no receipt at the current HEAD']


def test_a_ci_fix_verifies_on_the_check_it_repaired(repo: Repo) -> None:
    verified_task(repo)
    repo.run('start', 'C1', by='engineer', owned=['src/lint.py'])
    head = repo.commit('src/lint.py', 'clean\n')
    repo.receipt('T1.AC-1', 'pass', head)
    check = {'AC-1': 'https://github.com/o/r/actions/runs/99'}
    outcome = repo.run('verify', 'C1', commit=head, assertions=check)
    assert (outcome.code, outcome.out.strip()) == (ADVANCED, 'C1 verified')
    assert repo.run('ready').code == ADVANCED


def test_a_stuck_ci_fix_blocks_the_push(repo: Repo) -> None:
    head = verified_task(repo)
    repo.run('start', 'C1', by='engineer', owned=['src/lint.py'])
    repo.run('mark', 'C1', to='failed', reason='lint still red')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('ready')
    assert outcome.code == BLOCKED
    assert 'C1 is failed: lint still red' in outcome.out


def test_ready_needs_some_verified_work(repo: Repo) -> None:
    outcome = repo.run('ready')
    assert 'no plan task has been started' in outcome.out


def test_a_failed_review_remediation_blocks_the_push(repo: Repo) -> None:
    head = verified_task(repo)
    repo.run('start', 'R3', by='engineer', owned=['src/queue.py'])
    repo.run('mark', 'R3', to='blocked', reason='needs a decision')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('ready')
    assert 'R3 is blocked: needs a decision' in outcome.out


def test_an_old_report_cannot_hide_new_outside_changes(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    old = repo.commit('src/queue.py', 'fixed\n')
    head = repo.commit('deploy/values.yaml', 'pool: 5\n')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('verify', 'T1', commit=old)
    assert outcome.code == BLOCKED
    assert 'reported commit must resolve to the current HEAD' in outcome.out


def spoil_brief(repo: Repo, brief_state: str, old: str) -> None:
    brief = repo.ticket_dir.joinpath('briefs', 'task-01.md')
    if brief_state == 'missing':
        brief.unlink()
        return
    if brief_state == 'no-done':
        brief.write_text('## ASKED\n')
        return
    repo.done('T1', old)


@pytest.mark.parametrize('brief_state', ['missing', 'no-done', 'old-commit'])
def test_done_evidence_must_exist_and_match_head(repo: Repo, brief_state: str) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    old = repo.git('rev-parse', 'HEAD')
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    spoil_brief(repo, brief_state, old)
    assert repo.run('verify', 'T1', commit=head).code == BLOCKED


def test_short_commit_ids_are_saved_as_full_ids(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py', 'fixed\n')
    repo.receipt('T1.AC-1', 'pass', head)
    repo.done('T1', head[:12])
    assert repo.run('verify', 'T1', commit=head[:12]).code == ADVANCED
    assert repo.task('T1').commit == head


def test_a_task_base_from_another_history_is_blocked(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    repo.git('checkout', '--orphan', 'unrelated')
    head = repo.commit('src/queue.py', 'other history\n')
    repo.receipt('T1.AC-1', 'pass', head)
    outcome = repo.run('verify', 'T1', commit=head)
    assert outcome.code == BLOCKED
    assert 'base is not an ancestor' in outcome.out


class TestEscalationLadder:
    EXPANDED = ('src/queue.py', 'src/client.py')

    def test_scope_expansion_hands_an_in_progress_task_to_the_architect(self, repo: Repo) -> None:
        start(repo)

        outcome = repo.run(
            'start', 'T1', by='architect', owned=self.EXPANDED, mode='systemic-refactor'
        )

        task = repo.task('T1')
        assert outcome.code == ADVANCED
        assert (task.status, task.attempts) == ('in-progress', {'engineer': 1, 'architect': 1})
        assert list(task.owned) == ['src/client.py', 'src/queue.py']
        assert repo.transitions() == [('pending', 'in-progress'), ('in-progress', 'in-progress')]

    @pytest.mark.parametrize(
        ('worker', 'mode', 'reason'),
        [
            pytest.param('engineer', None, 'cannot move from in-progress', id='engineer'),
            pytest.param('architect', None, 'cannot move from in-progress', id='recovery'),
            pytest.param(
                'architect', 'diagnose-replan', 'cannot move from in-progress', id='replan'
            ),
            pytest.param(
                'engineer', 'systemic-refactor', 'is an architect mode', id='not-architect'
            ),
        ],
    )
    def test_only_an_architect_scope_expansion_takes_over_an_in_progress_task(
        self, repo: Repo, worker: str, mode: str | None, reason: str
    ) -> None:
        start(repo)

        outcome = repo.run('start', 'T1', by=worker, owned=self.EXPANDED, mode=mode)

        assert outcome.code == REJECTED
        assert reason in outcome.err
        assert repo.task('T1').attempts == {'engineer': 1}

    def test_a_scope_expansion_is_spent_after_its_one_pass(self, repo: Repo) -> None:
        start(repo)
        repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
        start(repo, 'architect')
        repo.run('start', 'T1', by='architect', owned=self.EXPANDED, mode='systemic-refactor')
        repo.run('mark', 'T1', to='blocked', reason='still red')

        outcome = repo.run(
            'start', 'T1', by='architect', owned=self.EXPANDED, mode='systemic-refactor'
        )

        assert outcome.code == REJECTED
        assert 'route it to whats-broken' in outcome.err

    def test_a_replanned_task_closes_as_superseded_and_ready_passes(self, repo: Repo) -> None:
        repo.approve('T1.AC-1', 'T2.AC-1')
        start(repo)
        repo.run('mark', 'T1', to='failed', reason='AC-1 cannot pass as planned')
        stuck = repo.run('ready')
        repo.run('start', 'T2', by='engineer', owned=['src/queue.py'])
        head = repo.commit('src/queue.py', 'replanned\n')
        repo.receipt('T2.AC-1', 'pass', head)
        repo.run('verify', 'T2', commit=head)

        closed = repo.run('mark', 'T1', to='superseded', reason='replanned as T2')

        assert (stuck.code, 'T1 is failed, not verified' in stuck.out) == (BLOCKED, True)
        assert (closed.code, repo.task('T1').status) == (ADVANCED, 'superseded')
        assert (repo.run('ready').code, repo.run('ready').out) == (
            ADVANCED,
            f'ready at {head[:12]}\n',
        )

    def test_a_superseded_task_cannot_restart(self, repo: Repo) -> None:
        start(repo)
        repo.run('mark', 'T1', to='superseded', reason='replanned as T2')

        outcome = start(repo)

        assert outcome.code == REJECTED
        assert 'cannot move from superseded to in-progress' in outcome.err

    def test_a_task_that_never_started_cannot_be_superseded(self, repo: Repo) -> None:
        outcome = repo.run('mark', 'T1', to='superseded', reason='replanned as T2')

        assert outcome.code == REJECTED
        assert 'cannot move from pending to superseded' in outcome.err

    def test_diagnose_replan_is_allowed_after_the_architects_one_implementation_attempt(
        self, repo: Repo
    ) -> None:
        start(repo)
        repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
        start(repo, 'architect')
        repo.run('mark', 'T1', to='failed', reason='the contract cannot pass')
        spent = start(repo, 'architect')

        first = repo.run(
            'start', 'T1', by='architect', owned=['src/queue.py'], mode='diagnose-replan'
        )
        repo.run('mark', 'T1', to='blocked', reason='revised contract proposed')
        second = repo.run(
            'start', 'T1', by='architect', owned=['src/queue.py'], mode='diagnose-replan'
        )

        assert (spent.code, first.code, second.code) == (REJECTED, ADVANCED, ADVANCED)
        assert repo.task('T1').attempts == {'engineer': 1, 'architect': 3}

    def test_diagnose_replan_does_not_spend_the_architects_implementation_attempt(
        self, repo: Repo
    ) -> None:
        start(repo)
        repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
        repo.run('start', 'T1', by='architect', owned=['src/queue.py'], mode='diagnose-replan')
        repo.run('mark', 'T1', to='blocked', reason='revised contract approved')

        assert start(repo, 'architect').code == ADVANCED


class TestVerify:
    def test_a_task_that_never_started_cannot_be_verified(self, repo: Repo) -> None:
        outcome = repo.run('verify', 'T1', commit=repo.git('rev-parse', 'HEAD'))

        assert outcome.code == REJECTED
        assert 'T1 cannot move from pending to verified' in outcome.err

    def test_a_task_started_before_the_first_commit_has_no_base(self, unborn: Repo) -> None:
        start(unborn)
        head = unborn.commit('src/queue.py', 'first\n')

        outcome = unborn.run('verify', 'T1', commit=head, assertions={'AC-1': 'README.md:1'})

        assert outcome.code == BLOCKED
        assert outcome.out == 'T1 blocked\n  - the task has no valid base commit\n'


class TestReadyBeforeTheFirstCommit:
    @pytest.fixture
    def unborn_with_a_passing_receipt(self, unborn: Repo, taken_at: str | None) -> Repo:
        unborn.approve('T1.AC-1')
        record_receipt(unborn.contracts, 'T1.AC-1', 'pass', taken_at)
        return unborn

    @pytest.mark.parametrize(
        'taken_at',
        [pytest.param(None, id='at-no-head'), pytest.param('a' * 40, id='at-a-commit')],
    )
    def test_no_receipt_is_at_the_current_head_while_there_is_no_head(
        self, unborn_with_a_passing_receipt: Repo
    ) -> None:
        outcome = unborn_with_a_passing_receipt.run('ready')

        assert outcome.code == BLOCKED
        assert '  - T1.AC-1 has no receipt at the current HEAD' in outcome.out.splitlines()


@dataclass(frozen=True, slots=True, kw_only=True)
class Restarted:
    first_base: str
    head: str
    blocked: Outcome
    restart: Outcome


class TestARestart:
    OUTSIDE = 'deploy/values.yaml'
    BLOCKED_ON_THE_CHANGE = f'T1 blocked\n  - changed outside the owned set: {OUTSIDE}\n'
    TRANSITIONS = (
        ('pending', 'in-progress'),
        ('in-progress', 'blocked'),
        ('blocked', 'in-progress'),
    )

    @pytest.fixture
    def restarted(self, repo: Repo) -> Restarted:
        repo.approve('T1.AC-1')
        first_base = repo.git('rev-parse', 'HEAD')
        start(repo)
        head = repo.commit(self.OUTSIDE, 'pool: 5\n')
        repo.receipt('T1.AC-1', 'pass', head)
        blocked = repo.run('verify', 'T1', commit=head)
        return Restarted(first_base=first_base, head=head, blocked=blocked, restart=start(repo))

    def test_a_restart_keeps_the_base_of_the_first_start(
        self, repo: Repo, restarted: Restarted
    ) -> None:
        task = repo.task('T1')

        assert restarted.restart.code == ADVANCED
        assert (task.status, task.base, task.owned, task.attempts) == (
            'in-progress',
            restarted.first_base,
            ('src/queue.py',),
            {'engineer': 2},
        )
        assert repo.transitions() == list(self.TRANSITIONS)

    def test_a_restarted_task_stays_blocked_on_the_same_change_outside_the_owned_set(
        self, repo: Repo, restarted: Restarted
    ) -> None:
        outcome = repo.run('verify', 'T1', commit=restarted.head)

        assert restarted.blocked.out == self.BLOCKED_ON_THE_CHANGE
        assert (outcome.code, outcome.out) == (BLOCKED, self.BLOCKED_ON_THE_CHANGE)


def ticket_status(repo: Repo) -> str:
    with ticket_transaction(repo.tasks.database) as repository:
        return repository.staged_row(TICKET).status


def task_row_counts(repo: Repo) -> list[int | None]:
    queries = [sql.select(sql.func.count()).select_from(table) for table in TASK_TABLES]
    with repo.tasks.database.transaction() as session:
        return [session.scalar(query) for query in queries]


class TestAClosedTicket:
    REFUSAL = (
        f'{SLUG} is closed, and a closed ticket is final; '
        'new work needs a new ticket, staged with open-ticket'
    )

    @pytest.fixture
    def closed(self, repo: Repo) -> Repo:
        start(repo)
        with ticket_transaction(repo.tasks.database) as repository:
            repository.mark_closed(TICKET)
        return repo

    @pytest.fixture
    def task_row_counts_when_closed(self, closed: Repo) -> list[int | None]:
        return task_row_counts(closed)

    @pytest.mark.parametrize(
        ('action', 'task_id', 'change'),
        [
            pytest.param('start', 'T2', {'by': 'engineer', 'owned': ['src/queue.py']}, id='start'),
            pytest.param('verify', 'T1', {'commit': 'HEAD'}, id='verify'),
            pytest.param('mark', 'T1', {'to': 'failed', 'reason': 'AC-1 still red'}, id='mark'),
        ],
    )
    def test_a_closed_ticket_refuses_the_action_stays_closed_and_gains_no_row(
        self,
        closed: Repo,
        task_row_counts_when_closed: list[int | None],
        *,
        action: str,
        task_id: str,
        change: dict[str, object],
    ) -> None:
        with pytest.raises(StateError) as refusal:
            act(closed.tasks, action, task_id, change)

        assert str(refusal.value) == self.REFUSAL
        assert ticket_status(closed) == 'closed'
        assert task_row_counts(closed) == task_row_counts_when_closed

    @pytest.mark.parametrize(
        'action', [pytest.param('show', id='show'), pytest.param('ready', id='ready')]
    )
    def test_a_closed_ticket_still_answers_show_and_ready(self, closed: Repo, action: str) -> None:
        outcome = closed.run(action)

        assert (outcome.err, 'T1' in outcome.out) == ('', True)
        assert ticket_status(closed) == 'closed'


class TestShow:
    def test_lists_started_and_planned_tasks_in_plan_order(self, repo: Repo) -> None:
        repo.approve('T2.AC-1', 'T10.AC-1', 'I1')
        repo.run('start', 'C1', by='engineer', owned=['src/lint.py'])
        start(repo)

        outcome = repo.run('show')

        assert [line.split('\t')[:2] for line in outcome.out.splitlines()] == [
            ['T1', 'in-progress'],
            ['T2', 'pending'],
            ['T10', 'pending'],
            ['C1', 'in-progress'],
        ]

    def test_an_owned_set_cannot_be_empty(self, repo: Repo) -> None:
        outcome = repo.run('start', 'T1', by='engineer', owned=[])

        assert outcome.code == REJECTED
        assert 'owned' in outcome.err
