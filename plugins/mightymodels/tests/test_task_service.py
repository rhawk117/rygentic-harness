"""The task service on the stores and the git history kept in memory.

A commit is one recorded in the history, a receipt goes in through the contract store, and a
task's brief is a file under the workspace root. The test of a revision that git itself refuses is
in test_task_revisions.py.
"""

from dataclasses import replace

import pytest
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.core.workspace import NotARepositoryError
from mightymodels_plugin.tools.task.schema import TaskVerification
from mightymodels_plugin.tools.task.tests.repo import (
    ADVANCED,
    BLOCKED,
    REJECTED,
    SLUG,
    TICKET,
    TaskRepo,
    act,
    record_receipt,
    start,
)


def test_start_records_the_attempt_and_its_base(task_repo: TaskRepo) -> None:
    base = task_repo.head()
    outcome = start(task_repo)
    task = task_repo.task('T1')
    assert outcome.code == ADVANCED
    assert (task.status, task.base, task.attempts) == (
        'in-progress',
        base,
        {'engineer': 1},
    )


def test_a_task_with_passing_receipts_and_owned_changes_verifies(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    head = task_repo.commit('src/queue.py')
    task_repo.receipt('T1.AC-1', 'pass', head)
    outcome = task_repo.run('verify', 'T1', commit=head)
    assert (outcome.code, outcome.out.strip()) == (ADVANCED, 'T1 verified')
    assert [after for _, after in task_repo.transitions()] == ['in-progress', 'verified']


def test_verify_raises_the_refusal_when_git_cannot_answer(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    refusal = NotARepositoryError(task_repo.root, 'no .git directory')
    refused = replace(task_repo.tasks, git=InMemoryGit(refused=refusal))
    with pytest.raises(NotARepositoryError) as raised:
        refused.verify(TICKET, 'T1', TaskVerification(commit=task_repo.head()))
    assert raised.value is refusal
    assert (
        str(raised.value) == f'{task_repo.root} is not inside a git repository: no .git directory'
    )


def test_changes_outside_the_owned_set_block_the_task(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    task_repo.commit('src/queue.py')
    head = task_repo.commit('deploy/values.yaml')
    task_repo.receipt('T1.AC-1', 'pass', head)
    outcome = task_repo.run('verify', 'T1', commit=head)
    assert outcome.code == BLOCKED
    assert 'changed outside the owned set: deploy/values.yaml' in outcome.out


def test_a_receipt_from_an_older_head_does_not_count(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    old = task_repo.head()
    head = task_repo.commit('src/queue.py')
    task_repo.receipt('T1.AC-1', 'pass', old)
    outcome = task_repo.run('verify', 'T1', commit=head)
    assert outcome.code == BLOCKED
    assert 'T1.AC-1 has no receipt at the current HEAD' in outcome.out


def test_a_failing_receipt_blocks_the_task(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    head = task_repo.commit('src/queue.py')
    task_repo.receipt('T1.AC-1', 'fail', head)
    outcome = task_repo.run('verify', 'T1', commit=head)
    assert 'T1.AC-1 fail at HEAD' in outcome.out


def test_brief_criteria_need_a_command_or_a_citation(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    brief = task_repo.ticket_dir.joinpath('briefs', 'task-01.md')
    brief.parent.mkdir()
    brief.write_text('## ASKED\nacceptance:\n  - AC-1: tests pass\n  - AC-2: docs updated\n')
    start(task_repo)
    head = task_repo.commit('src/queue.py')
    task_repo.receipt('T1.AC-1', 'pass', head)
    blocked = task_repo.run('verify', 'T1', commit=head)
    start(task_repo)
    verified = task_repo.run('verify', 'T1', commit=head, assertions={'AC-2': 'README.md:12'})
    assert 'AC-2 has neither a contract command nor a citation' in blocked.out
    assert verified.code == ADVANCED


def test_a_task_needs_some_proof(task_repo: TaskRepo) -> None:
    start(task_repo)
    head = task_repo.commit('src/queue.py')
    outcome = task_repo.run('verify', 'T1', commit=head)
    assert 'no contract command and no cited assertion proves this task' in outcome.out


def test_architect_recovers_a_task_only_once(task_repo: TaskRepo) -> None:
    start(task_repo)
    task_repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
    start(task_repo, 'architect')
    task_repo.run('mark', 'T1', to='blocked', reason='needs a decision')
    outcome = start(task_repo, 'architect')
    assert outcome.code == REJECTED
    assert 'route it to whats-broken' in outcome.err


def test_a_verified_task_cannot_restart(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    head = task_repo.commit('src/queue.py')
    task_repo.receipt('T1.AC-1', 'pass', head)
    task_repo.run('verify', 'T1', commit=head)
    outcome = start(task_repo)
    assert 'cannot move from verified to in-progress' in outcome.err


def test_an_unstaged_ticket_is_refused(unstaged_task_repo: TaskRepo) -> None:
    outcome = start(unstaged_task_repo)
    assert 'stage the ticket with open-ticket first' in outcome.err


def test_an_approved_scope_expansion_allows_one_more_architect_pass(task_repo: TaskRepo) -> None:
    start(task_repo)
    task_repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
    start(task_repo, 'architect')
    task_repo.run('mark', 'T1', to='blocked', reason='scope-expansion-requested')
    expanded = ('src/queue.py', 'src/client.py')
    outcome = task_repo.run(
        'start', 'T1', by='architect', owned=expanded, acceptance=['AC-1'], mode='systemic-refactor'
    )
    task = task_repo.task('T1')
    assert outcome.code == ADVANCED
    assert list(task.owned) == ['src/client.py', 'src/queue.py']


def verified_task(repo: TaskRepo) -> str:
    repo.approve('T1.AC-1')
    start(repo)
    head = repo.commit('src/queue.py')
    repo.receipt('T1.AC-1', 'pass', head)
    repo.run('verify', 'T1', commit=head)
    return head


def test_ready_when_every_task_is_verified_at_head(task_repo: TaskRepo) -> None:
    head = verified_task(task_repo)
    outcome = task_repo.run('ready')
    assert (outcome.code, outcome.out) == (ADVANCED, f'ready at {head[:12]}\n')


def test_a_contract_task_never_started_is_not_ready(task_repo: TaskRepo) -> None:
    verified_task(task_repo)
    task_repo.approve('T1.AC-1', 'T2.AC-1')
    outcome = task_repo.run('ready')
    assert outcome.code == BLOCKED
    assert 'T2 has contract commands but was never started' in outcome.out


def test_a_ci_fix_makes_earlier_receipts_stale(task_repo: TaskRepo) -> None:
    verified_task(task_repo)
    task_repo.run('start', 'C1', by='engineer', owned=['src/lint.py'], acceptance=['AC-1'])
    task_repo.commit('src/lint.py')
    outcome = task_repo.run('ready')
    assert outcome.code == BLOCKED
    assert outcome.out.splitlines()[1:] == ['  - T1.AC-1 has no receipt at the current HEAD']


def test_a_ci_fix_verifies_on_the_check_it_repaired(task_repo: TaskRepo) -> None:
    verified_task(task_repo)
    task_repo.run('start', 'C1', by='engineer', owned=['src/lint.py'], acceptance=['AC-1'])
    head = task_repo.commit('src/lint.py')
    task_repo.receipt('T1.AC-1', 'pass', head)
    check = {'AC-1': 'https://github.com/o/r/actions/runs/99'}
    outcome = task_repo.run('verify', 'C1', commit=head, assertions=check)
    assert (outcome.code, outcome.out.strip()) == (ADVANCED, 'C1 verified')
    assert task_repo.run('ready').code == ADVANCED


def test_a_stuck_ci_fix_blocks_the_push(task_repo: TaskRepo) -> None:
    head = verified_task(task_repo)
    task_repo.run('start', 'C1', by='engineer', owned=['src/lint.py'], acceptance=['AC-1'])
    task_repo.run('mark', 'C1', to='failed', reason='lint still red')
    task_repo.receipt('T1.AC-1', 'pass', head)
    outcome = task_repo.run('ready')
    assert outcome.code == BLOCKED
    assert 'C1 is failed: lint still red' in outcome.out


def test_ready_needs_some_verified_work(task_repo: TaskRepo) -> None:
    outcome = task_repo.run('ready')
    assert 'no plan task has been started' in outcome.out


def test_a_failed_review_remediation_blocks_the_push(task_repo: TaskRepo) -> None:
    head = verified_task(task_repo)
    task_repo.run('start', 'R3', by='engineer', owned=['src/queue.py'], acceptance=['AC-1'])
    task_repo.run('mark', 'R3', to='blocked', reason='needs a decision')
    task_repo.receipt('T1.AC-1', 'pass', head)
    outcome = task_repo.run('ready')
    assert 'R3 is blocked: needs a decision' in outcome.out


def test_an_old_report_cannot_hide_new_outside_changes(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    old = task_repo.commit('src/queue.py')
    head = task_repo.commit('deploy/values.yaml')
    task_repo.receipt('T1.AC-1', 'pass', head)
    outcome = task_repo.run('verify', 'T1', commit=old)
    assert outcome.code == BLOCKED
    assert 'reported commit must resolve to the current HEAD' in outcome.out


def spoil_brief(repo: TaskRepo, brief_state: str, old: str) -> None:
    brief = repo.ticket_dir.joinpath('briefs', 'task-01.md')
    if brief_state == 'missing':
        brief.unlink()
        return
    if brief_state == 'no-done':
        brief.write_text('## ASKED\n')
        return
    repo.done('T1', old)


@pytest.mark.parametrize('brief_state', ['missing', 'no-done', 'old-commit'])
def test_done_evidence_must_exist_and_match_head(task_repo: TaskRepo, brief_state: str) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    old = task_repo.head()
    head = task_repo.commit('src/queue.py')
    task_repo.receipt('T1.AC-1', 'pass', head)
    spoil_brief(task_repo, brief_state, old)
    assert task_repo.run('verify', 'T1', commit=head).code == BLOCKED


def test_short_commit_ids_are_saved_as_full_ids(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    head = task_repo.commit('src/queue.py')
    task_repo.receipt('T1.AC-1', 'pass', head)
    task_repo.done('T1', head[:12])
    assert task_repo.run('verify', 'T1', commit=head[:12]).code == ADVANCED
    assert task_repo.task('T1').commit == head


def test_a_task_base_from_another_history_is_blocked(task_repo: TaskRepo) -> None:
    task_repo.approve('T1.AC-1')
    start(task_repo)
    head = task_repo.commit('src/queue.py', unrelated=True)
    task_repo.receipt('T1.AC-1', 'pass', head)
    outcome = task_repo.run('verify', 'T1', commit=head)
    assert outcome.code == BLOCKED
    assert 'base is not an ancestor' in outcome.out


class TestVerify:
    def test_a_task_that_never_started_cannot_be_verified(self, task_repo: TaskRepo) -> None:
        outcome = task_repo.run('verify', 'T1', commit=task_repo.head())

        assert outcome.code == REJECTED
        assert 'T1 cannot move from pending to verified' in outcome.err

    def test_a_task_started_before_the_first_commit_has_no_base(
        self, unborn_task_repo: TaskRepo
    ) -> None:
        start(unborn_task_repo)
        head = unborn_task_repo.commit('src/queue.py')

        outcome = unborn_task_repo.run(
            'verify', 'T1', commit=head, assertions={'AC-1': 'README.md:1'}
        )

        assert outcome.code == BLOCKED
        assert outcome.out == 'T1 blocked\n  - the task has no valid base commit\n'


class TestReadyBeforeTheFirstCommit:
    @pytest.fixture
    def unborn_with_a_passing_receipt(
        self, unborn_task_repo: TaskRepo, taken_at: str | None
    ) -> TaskRepo:
        unborn_task_repo.approve('T1.AC-1')
        record_receipt(unborn_task_repo.contracts, 'T1.AC-1', 'pass', taken_at)
        return unborn_task_repo

    @pytest.mark.parametrize(
        'taken_at',
        [pytest.param(None, id='at-no-head'), pytest.param('a' * 40, id='at-a-commit')],
    )
    def test_no_receipt_is_at_the_current_head_while_there_is_no_head(
        self, unborn_with_a_passing_receipt: TaskRepo
    ) -> None:
        outcome = unborn_with_a_passing_receipt.run('ready')

        assert outcome.code == BLOCKED
        assert '  - T1.AC-1 has no receipt at the current HEAD' in outcome.out.splitlines()


def ticket_status(repo: TaskRepo) -> str:
    with repo.store.transaction() as repository:
        return repository.tickets.staged_ticket(TICKET).status


def task_row_counts(repo: TaskRepo) -> list[int]:
    return [len(repo.store.held), len(repo.store.attempts), len(repo.store.transitions)]


class TestAClosedTicket:
    REFUSAL = (
        f'{SLUG} is closed, and a closed ticket is final; '
        'new work needs a new ticket, staged with open-ticket'
    )

    @pytest.fixture
    def closed(self, task_repo: TaskRepo) -> TaskRepo:
        start(task_repo)
        with task_repo.store.transaction() as repository:
            repository.tickets.mark_closed(TICKET)
        return task_repo

    @pytest.fixture
    def task_row_counts_when_closed(self, closed: TaskRepo) -> list[int]:
        return task_row_counts(closed)

    @pytest.mark.parametrize(
        ('action', 'task_id', 'change'),
        [
            pytest.param(
                'start',
                'T2',
                {'by': 'engineer', 'owned': ['src/queue.py'], 'acceptance': ['AC-1']},
                id='start',
            ),
            pytest.param('verify', 'T1', {'commit': 'HEAD'}, id='verify'),
            pytest.param('mark', 'T1', {'to': 'failed', 'reason': 'AC-1 still red'}, id='mark'),
        ],
    )
    def test_a_closed_ticket_refuses_the_action_stays_closed_and_gains_no_row(
        self,
        closed: TaskRepo,
        task_row_counts_when_closed: list[int],
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
    def test_a_closed_ticket_still_answers_show_and_ready(
        self, closed: TaskRepo, action: str
    ) -> None:
        outcome = closed.run(action)

        assert (outcome.err, 'T1' in outcome.out) == ('', True)
        assert ticket_status(closed) == 'closed'


class TestShow:
    def test_lists_started_and_planned_tasks_in_plan_order(self, task_repo: TaskRepo) -> None:
        task_repo.approve('T2.AC-1', 'T10.AC-1', 'I1')
        task_repo.run('start', 'C1', by='engineer', owned=['src/lint.py'], acceptance=['AC-1'])
        start(task_repo)

        outcome = task_repo.run('show')

        assert [line.split('\t')[:2] for line in outcome.out.splitlines()] == [
            ['T1', 'in-progress'],
            ['T2', 'pending'],
            ['T10', 'pending'],
            ['C1', 'in-progress'],
        ]

    def test_an_owned_set_cannot_be_empty(self, task_repo: TaskRepo) -> None:
        outcome = task_repo.run('start', 'T1', by='engineer', owned=[], acceptance=['AC-1'])

        assert outcome.code == REJECTED
        assert 'owned' in outcome.err
