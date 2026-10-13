from dataclasses import dataclass

import pytest
from mightymodels.tools.task.tests.repo import (
    ADVANCED,
    BLOCKED,
    REJECTED,
    TaskOutcome,
    TaskRepo,
    start,
)


class TestEscalationLadder:
    EXPANDED = ('src/queue.py', 'src/client.py')

    def test_scope_expansion_hands_an_in_progress_task_to_the_architect(
        self, task_repo: TaskRepo
    ) -> None:
        start(task_repo)

        outcome = task_repo.run(
            'start',
            'T1',
            by='architect',
            owned=self.EXPANDED,
            acceptance=['AC-1'],
            mode='systemic-refactor',
        )

        task = task_repo.task('T1')
        assert outcome.code == ADVANCED
        assert (task.status, task.attempts) == ('in-progress', {'engineer': 1, 'architect': 1})
        assert list(task.owned) == ['src/client.py', 'src/queue.py']
        assert task_repo.transitions() == [
            ('pending', 'in-progress'),
            ('in-progress', 'in-progress'),
        ]

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
            pytest.param(
                'intern', 'systemic-refactor', 'is an architect mode', id='intern-in-a-mode'
            ),
        ],
    )
    def test_only_an_architect_scope_expansion_takes_over_an_in_progress_task(
        self, task_repo: TaskRepo, worker: str, mode: str | None, reason: str
    ) -> None:
        start(task_repo)

        outcome = task_repo.run(
            'start', 'T1', by=worker, owned=self.EXPANDED, acceptance=['AC-1'], mode=mode
        )

        assert outcome.code == REJECTED
        assert reason in outcome.err
        assert task_repo.task('T1').attempts == {'engineer': 1}

    def test_a_scope_expansion_is_spent_after_its_one_pass(self, task_repo: TaskRepo) -> None:
        start(task_repo)
        task_repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
        start(task_repo, 'architect')
        task_repo.run(
            'start',
            'T1',
            by='architect',
            owned=self.EXPANDED,
            acceptance=['AC-1'],
            mode='systemic-refactor',
        )
        task_repo.run('mark', 'T1', to='blocked', reason='still red')

        outcome = task_repo.run(
            'start',
            'T1',
            by='architect',
            owned=self.EXPANDED,
            acceptance=['AC-1'],
            mode='systemic-refactor',
        )

        assert outcome.code == REJECTED
        assert 'route it to whats-broken' in outcome.err

    def test_a_replanned_task_closes_as_superseded_and_ready_passes(
        self, task_repo: TaskRepo
    ) -> None:
        task_repo.approve('T1.AC-1', 'T2.AC-1')
        start(task_repo)
        task_repo.run('mark', 'T1', to='failed', reason='AC-1 cannot pass as planned')
        stuck = task_repo.run('ready')
        task_repo.run('start', 'T2', by='engineer', owned=['src/queue.py'], acceptance=['AC-1'])
        head = task_repo.commit('src/queue.py')
        task_repo.receipt('T2.AC-1', 'pass', head)
        task_repo.run('verify', 'T2', commit=head)

        closed = task_repo.run('mark', 'T1', to='superseded', reason='replanned as T2')

        assert (stuck.code, 'T1 is failed, not verified' in stuck.out) == (BLOCKED, True)
        assert (closed.code, task_repo.task('T1').status) == (ADVANCED, 'superseded')
        assert (task_repo.run('ready').code, task_repo.run('ready').out) == (
            ADVANCED,
            f'ready at {head[:12]}\n',
        )

    def test_a_superseded_task_cannot_restart(self, task_repo: TaskRepo) -> None:
        start(task_repo)
        task_repo.run('mark', 'T1', to='superseded', reason='replanned as T2')

        outcome = start(task_repo)

        assert outcome.code == REJECTED
        assert 'cannot move from superseded to in-progress' in outcome.err

    def test_diagnose_replan_is_allowed_after_the_architects_one_implementation_attempt(
        self, task_repo: TaskRepo
    ) -> None:
        start(task_repo)
        task_repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
        start(task_repo, 'architect')
        task_repo.run('mark', 'T1', to='failed', reason='the contract cannot pass')
        spent = start(task_repo, 'architect')

        first = task_repo.run(
            'start',
            'T1',
            by='architect',
            owned=['src/queue.py'],
            acceptance=['AC-1'],
            mode='diagnose-replan',
        )
        task_repo.run('mark', 'T1', to='blocked', reason='revised contract proposed')
        second = task_repo.run(
            'start',
            'T1',
            by='architect',
            owned=['src/queue.py'],
            acceptance=['AC-1'],
            mode='diagnose-replan',
        )

        assert (spent.code, first.code, second.code) == (REJECTED, ADVANCED, ADVANCED)
        assert task_repo.task('T1').attempts == {'engineer': 1, 'architect': 3}

    def test_diagnose_replan_does_not_spend_the_architects_implementation_attempt(
        self, task_repo: TaskRepo
    ) -> None:
        start(task_repo)
        task_repo.run('mark', 'T1', to='failed', reason='AC-1 still red')
        task_repo.run(
            'start',
            'T1',
            by='architect',
            owned=['src/queue.py'],
            acceptance=['AC-1'],
            mode='diagnose-replan',
        )
        task_repo.run('mark', 'T1', to='blocked', reason='revised contract approved')

        assert start(task_repo, 'architect').code == ADVANCED


class TestATaskThatNeverStarted:
    def test_a_task_that_never_started_can_be_superseded(self, task_repo: TaskRepo) -> None:
        outcome = task_repo.run('mark', 'T1', to='superseded', reason='split into T2 and T3')

        task = task_repo.task('T1')
        assert outcome.code == ADVANCED
        assert (task.status, task.reasons) == ('superseded', ('split into T2 and T3',))
        assert task_repo.transitions() == [('pending', 'superseded')]

    @pytest.mark.parametrize(
        'status', [pytest.param('failed', id='failed'), pytest.param('blocked', id='blocked')]
    )
    def test_a_task_that_never_started_cannot_be_marked_anything_but_superseded(
        self, task_repo: TaskRepo, status: str
    ) -> None:
        outcome = task_repo.run('mark', 'T1', to=status, reason='AC-1 cannot pass as planned')

        assert outcome.code == REJECTED
        assert f'cannot move from pending to {status}' in outcome.err
        assert task_repo.transitions() == []

    def test_a_task_superseded_before_it_started_cannot_start(self, task_repo: TaskRepo) -> None:
        task_repo.run('mark', 'T1', to='superseded', reason='split into T2 and T3')

        outcome = start(task_repo)

        assert outcome.code == REJECTED
        assert 'cannot move from superseded to in-progress' in outcome.err

    def test_a_task_superseded_before_it_started_no_longer_blocks_ready(
        self, task_repo: TaskRepo
    ) -> None:
        task_repo.approve('T1.AC-1', 'T2.AC-1')
        task_repo.run('start', 'T2', by='engineer', owned=['src/queue.py'], acceptance=['AC-1'])
        head = task_repo.commit('src/queue.py')
        task_repo.receipt('T2.AC-1', 'pass', head)
        task_repo.run('verify', 'T2', commit=head)
        stuck = task_repo.run('ready')

        task_repo.run('mark', 'T1', to='superseded', reason='split into T2 and T3')

        never_started = 'T1 has contract commands but was never started'
        assert (stuck.code, never_started in stuck.out) == (BLOCKED, True)
        assert (task_repo.run('ready').code, task_repo.run('ready').out) == (
            ADVANCED,
            f'ready at {head[:12]}\n',
        )


class TestTheInternsOneAttempt:
    @pytest.fixture
    def blocked_after_the_intern(self, task_repo: TaskRepo) -> TaskRepo:
        start(task_repo, 'intern')
        task_repo.run('mark', 'T1', to='blocked', reason='AC-1 still red')
        return task_repo

    def test_a_second_intern_attempt_is_refused_naming_the_engineer(
        self, blocked_after_the_intern: TaskRepo
    ) -> None:
        outcome = start(blocked_after_the_intern, 'intern')

        task = blocked_after_the_intern.task('T1')
        assert outcome.code == REJECTED
        assert outcome.err == 'T1 already had its intern attempt; start it by engineer'
        assert (task.status, task.attempts) == ('blocked', {'intern': 1})

    def test_the_engineer_takes_over_the_task_the_intern_blocked_on(
        self, blocked_after_the_intern: TaskRepo
    ) -> None:
        outcome = start(blocked_after_the_intern)

        task = blocked_after_the_intern.task('T1')
        assert outcome.code == ADVANCED
        assert (task.status, task.attempts) == ('in-progress', {'intern': 1, 'engineer': 1})
        assert blocked_after_the_intern.transitions() == [
            ('pending', 'in-progress'),
            ('in-progress', 'blocked'),
            ('blocked', 'in-progress'),
        ]

    def test_an_intern_attempt_on_one_task_leaves_its_attempt_on_another(
        self, blocked_after_the_intern: TaskRepo
    ) -> None:
        outcome = blocked_after_the_intern.run(
            'start', 'T2', by='intern', owned=['src/queue.py'], acceptance=['AC-1']
        )

        assert outcome.code == ADVANCED
        assert blocked_after_the_intern.task('T2').attempts == {'intern': 1}


@dataclass(frozen=True, slots=True, kw_only=True)
class Restarted:
    first_base: str
    head: str
    blocked: TaskOutcome
    restart: TaskOutcome


class TestARestart:
    OUTSIDE = 'deploy/values.yaml'
    BLOCKED_ON_THE_CHANGE = f'T1 blocked\n  - changed outside the owned set: {OUTSIDE}\n'
    TRANSITIONS = (
        ('pending', 'in-progress'),
        ('in-progress', 'blocked'),
        ('blocked', 'in-progress'),
    )

    @pytest.fixture
    def restarted(self, task_repo: TaskRepo) -> Restarted:
        task_repo.approve('T1.AC-1')
        first_base = task_repo.head()
        start(task_repo)
        head = task_repo.commit(self.OUTSIDE)
        task_repo.receipt('T1.AC-1', 'pass', head)
        blocked = task_repo.run('verify', 'T1', commit=head)
        return Restarted(
            first_base=first_base, head=head, blocked=blocked, restart=start(task_repo)
        )

    def test_a_restart_keeps_the_base_of_the_first_start(
        self, task_repo: TaskRepo, restarted: Restarted
    ) -> None:
        task = task_repo.task('T1')

        assert restarted.restart.code == ADVANCED
        assert (task.status, task.base, task.owned, task.attempts) == (
            'in-progress',
            restarted.first_base,
            ('src/queue.py',),
            {'engineer': 2},
        )
        assert task_repo.transitions() == list(self.TRANSITIONS)

    def test_a_restarted_task_stays_blocked_on_the_same_change_outside_the_owned_set(
        self, task_repo: TaskRepo, restarted: Restarted
    ) -> None:
        outcome = task_repo.run('verify', 'T1', commit=restarted.head)

        assert restarted.blocked.out == self.BLOCKED_ON_THE_CHANGE
        assert (outcome.code, outcome.out) == (BLOCKED, self.BLOCKED_ON_THE_CHANGE)
