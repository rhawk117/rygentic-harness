"""Every method of the task repository, on the store kept in memory and on SQLite.

One fixture hands out either store, so each case runs on both and the store kept in memory cannot
drift from the repository it stands in for. A task belongs to a ticket, so every case starts from
two staged tickets, staged through the ticket repository of the task transaction.
"""

from contextlib import suppress
from dataclasses import replace

import pytest
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.routing import Scope
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.contract.schema import ContractCommand
from mightymodels_plugin.tools.contract.store import Approval
from mightymodels_plugin.tools.task.repository import task_store
from mightymodels_plugin.tools.task.schema import ArchitectMode, Implementer, Status, TaskRecord
from mightymodels_plugin.tools.task.store import (
    Attempt,
    TaskRecords,
    TaskRepository,
    TaskStore,
    Transition,
)
from mightymodels_plugin.tools.ticket.repository import NotStagedError
from mightymodels_plugin.tools.ticket.schema import TicketSection, TicketStatus, Tracker

TICKET = Slug('retry-queue')
OTHER = Slug('drain-loop')
NEVER_STAGED = Slug('never-staged')
BASE, HEAD = 'a' * 40, 'b' * 40
AT = '2026-09-28T00:00:00+00:00'
EVERY_STATUS = frozenset(Status)
MANY = 10
OWNED = ('src/queue.py',)
EXPANDED = ('src/client.py', 'src/queue.py')
SECTION = TicketSection(
    ticket='Retry queue drains slowly',
    summary='The drain loop sleeps between batches',
    branch='fix/retry-queue',
    scope=Scope.MED,
    plan_first=False,
    models={},
    tracker=Tracker(issue=None, jira=None),
    context=(),
    validated_at=AT,
)
OTHER_SECTION = SECTION.model_copy(update={'ticket': 'Drain loop never wakes'})
COMMAND = ContractCommand(id='T1.AC-1', argv=('true',), approved_by='user')
APPROVAL = Approval(at=AT, head=BASE)


def moved(
    task_id: str, before: Status, after: Status, *reasons: str, head: str | None = BASE
) -> Transition:
    return Transition(
        task_id=task_id, before=before, after=after, reasons=reasons, head=head, at=AT
    )


STARTED = moved('T1', Status.PENDING, Status.IN_PROGRESS)
BLOCKED = moved(
    'T1', Status.IN_PROGRESS, Status.BLOCKED, 'changed outside the owned set', head=HEAD
)
RESTARTED = moved('T1', Status.BLOCKED, Status.IN_PROGRESS, head=HEAD)
VERIFIED = moved('T1', Status.IN_PROGRESS, Status.VERIFIED, head=HEAD)
FAILED = Transition(
    task_id='T1',
    before=Status.IN_PROGRESS,
    after=Status.FAILED,
    reasons=['AC-1 still red', 'AC-2 still red'],
    head=HEAD,
    at=AT,
)
STARTED_WITH_NO_HEAD = moved('T1', Status.PENDING, Status.IN_PROGRESS, head=None)
SECOND_STARTED = moved('T2', Status.PENDING, Status.IN_PROGRESS)
BY_THE_ENGINEER = Attempt(worker=Implementer.ENGINEER, mode=None, owned=OWNED)
BY_THE_ARCHITECT = Attempt(
    worker=Implementer.ARCHITECT, mode=ArchitectMode.SYSTEMIC_REFACTOR, owned=EXPANDED
)


@pytest.fixture
def sqlite_store(repository_database: Database) -> TaskStore:
    return task_store(repository_database)


@pytest.fixture(
    params=[
        pytest.param('in_memory_task_store', id='fake'),
        pytest.param('sqlite_store', id='sqlite'),
    ]
)
def store(request: pytest.FixtureRequest) -> TaskStore:
    return request.getfixturevalue(request.param)


@pytest.fixture
def staged(store: TaskStore) -> TaskStore:
    with store.transaction() as repository:
        repository.tickets.stage(TICKET, SECTION, [])
        repository.tickets.stage(OTHER, OTHER_SECTION, [])
    return store


@pytest.fixture
def started(staged: TaskStore) -> TaskStore:
    with staged.transaction() as repository:
        repository.record_start(TICKET, STARTED, BY_THE_ENGINEER)
    return staged


@pytest.fixture
def restarted(started: TaskStore) -> TaskStore:
    with started.transaction() as repository:
        repository.record_mark(TICKET, BLOCKED)
        repository.record_start(TICKET, RESTARTED, BY_THE_ARCHITECT)
    return started


class TestTaskRepository:
    def test_the_store_and_its_repository_are_the_seam_the_service_holds(
        self, store: TaskStore
    ) -> None:
        with store.transaction() as repository:
            assert isinstance(store, TaskStore)
            assert isinstance(repository, TaskRecords)
            assert isinstance(repository, TaskRepository)

    def test_a_ticket_with_no_task_started_has_nothing_to_read(self, staged: TaskStore) -> None:
        with staged.transaction() as repository:
            assert (repository.task(TICKET, 'T1'), repository.tasks(TICKET)) == (None, [])
            assert repository.attempts_by_worker(TICKET) == {}
            assert repository.attempts_in_modes(TICKET, 'T1', frozenset(ArchitectMode)) == 0
            assert repository.failed_fixes(TICKET, 'T1') == []
            assert repository.latest_transitions_into(TICKET, EVERY_STATUS, MANY) == []

    def test_a_start_stores_the_task_its_attempt_and_its_transition(
        self, started: TaskStore
    ) -> None:
        task = TaskRecord(id='T1', status=Status.IN_PROGRESS, owned=OWNED, base=BASE)

        with started.transaction() as repository:
            assert (repository.task(TICKET, 'T1'), repository.tasks(TICKET)) == (task, [task])
            assert repository.attempts_by_worker(TICKET) == {'T1': {'engineer': 1}}
            assert repository.latest_transitions_into(TICKET, EVERY_STATUS, MANY) == [STARTED]

    def test_a_restart_keeps_the_first_base_and_counts_each_worker(
        self, restarted: TaskStore
    ) -> None:
        task = TaskRecord(id='T1', status=Status.IN_PROGRESS, owned=EXPANDED, base=BASE)

        with restarted.transaction() as repository:
            assert repository.task(TICKET, 'T1') == task
            assert repository.attempts_by_worker(TICKET) == {'T1': {'engineer': 1, 'architect': 1}}

    def test_attempts_are_counted_in_the_modes_named_and_no_other(
        self, restarted: TaskStore
    ) -> None:
        refactor = {ArchitectMode.SYSTEMIC_REFACTOR}
        others = {ArchitectMode.DIAGNOSE_REPLAN, ArchitectMode.RECOVERY_IMPLEMENTATION}

        with restarted.transaction() as repository:
            assert repository.attempts_in_modes(TICKET, 'T1', refactor) == 1
            assert repository.attempts_in_modes(TICKET, 'T1', others) == 0
            assert repository.attempts_in_modes(TICKET, 'T2', refactor) == 0

    def test_the_latest_transitions_into_the_statuses_named_are_read_oldest_first(
        self, restarted: TaskStore
    ) -> None:
        in_progress = {Status.IN_PROGRESS}

        with restarted.transaction() as repository:
            every = repository.latest_transitions_into(TICKET, EVERY_STATUS, MANY)
            assert every == [STARTED, BLOCKED, RESTARTED]
            assert repository.latest_transitions_into(TICKET, in_progress, MANY) == [
                STARTED,
                RESTARTED,
            ]
            assert repository.latest_transitions_into(TICKET, in_progress, 1) == [RESTARTED]
            assert repository.latest_transitions_into(TICKET, EVERY_STATUS, 2) == [
                BLOCKED,
                RESTARTED,
            ]
            assert repository.latest_transitions_into(TICKET, EVERY_STATUS, 0) == []


class TestTheBase:
    @pytest.fixture
    def started_before_the_first_commit(self, staged: TaskStore) -> TaskStore:
        with staged.transaction() as repository:
            repository.record_start(TICKET, STARTED_WITH_NO_HEAD, BY_THE_ENGINEER)
        return staged

    @pytest.fixture
    def restarted_after_two_commits(self, started_before_the_first_commit: TaskStore) -> TaskStore:
        with started_before_the_first_commit.transaction() as repository:
            repository.record_start(TICKET, RESTARTED, BY_THE_ENGINEER)
            repository.record_start(TICKET, STARTED, BY_THE_ENGINEER)
        return started_before_the_first_commit

    def test_a_task_started_before_the_first_commit_has_no_base(
        self, started_before_the_first_commit: TaskStore
    ) -> None:
        with started_before_the_first_commit.transaction() as repository:
            assert repository.tasks(TICKET) == [
                TaskRecord(id='T1', status=Status.IN_PROGRESS, owned=OWNED)
            ]

    def test_the_base_is_the_head_of_the_first_start_that_had_one(
        self, restarted_after_two_commits: TaskStore
    ) -> None:
        with restarted_after_two_commits.transaction() as repository:
            assert repository.tasks(TICKET) == [
                TaskRecord(id='T1', status=Status.IN_PROGRESS, owned=OWNED, base=HEAD)
            ]
            assert repository.attempts_by_worker(TICKET) == {'T1': {'engineer': 3}}


class TestAMovedTask:
    @pytest.fixture
    def blocked(self, started: TaskStore) -> TaskStore:
        with started.transaction() as repository:
            repository.record_mark(TICKET, BLOCKED)
        return started

    @pytest.fixture
    def failed(self, started: TaskStore) -> TaskStore:
        with started.transaction() as repository:
            repository.record_mark(TICKET, FAILED)
        return started

    @pytest.fixture
    def verified(self, started: TaskStore) -> TaskStore:
        with started.transaction() as repository:
            repository.record_verification(TICKET, VERIFIED, HEAD)
        return started

    def test_a_mark_stores_the_status_and_its_reasons_with_the_transition(
        self, blocked: TaskStore
    ) -> None:
        task = TaskRecord(
            id='T1', status=Status.BLOCKED, owned=OWNED, base=BASE, reasons=tuple(BLOCKED.reasons)
        )

        with blocked.transaction() as repository:
            assert repository.task(TICKET, 'T1') == task
            assert repository.latest_transitions_into(TICKET, {Status.BLOCKED}, MANY) == [BLOCKED]

    def test_reasons_written_as_a_list_are_read_back_as_a_tuple(self, failed: TaskStore) -> None:
        reasons = ('AC-1 still red', 'AC-2 still red')

        with failed.transaction() as repository:
            assert repository.tasks(TICKET)[0].reasons == reasons
            assert repository.latest_transitions_into(TICKET, {Status.FAILED}, MANY) == [
                replace(FAILED, reasons=reasons)
            ]

    def test_a_verification_stores_the_commit_with_the_transition(
        self, verified: TaskStore
    ) -> None:
        task = TaskRecord(id='T1', status=Status.VERIFIED, owned=OWNED, base=BASE, commit=HEAD)

        with verified.transaction() as repository:
            assert repository.task(TICKET, 'T1') == task
            assert repository.latest_transitions_into(TICKET, {Status.VERIFIED}, MANY) == [VERIFIED]


class TestFailedFixes:
    HYPOTHESES = ('the lock is held too long', 'the batch is too large')

    @pytest.fixture
    def with_failed_fixes(self, started: TaskStore) -> TaskStore:
        with started.transaction() as repository:
            for hypothesis in self.HYPOTHESES:
                repository.record_failed_fix(TICKET, 'T1', hypothesis, at=AT)
        return started

    def test_the_failed_fixes_of_a_task_are_read_in_the_order_written(
        self, with_failed_fixes: TaskStore
    ) -> None:
        with with_failed_fixes.transaction() as repository:
            assert repository.failed_fixes(TICKET, 'T1') == list(self.HYPOTHESES)
            assert repository.failed_fixes(TICKET, 'T2') == []
            assert repository.failed_fixes(OTHER, 'T1') == []


class TestTwoTickets:
    @pytest.fixture
    def both_started(self, started: TaskStore) -> TaskStore:
        with started.transaction() as repository:
            repository.record_start(OTHER, STARTED, BY_THE_ARCHITECT)
            repository.record_start(OTHER, SECOND_STARTED, BY_THE_ENGINEER)
        return started

    def test_each_ticket_reads_its_own_tasks_attempts_and_transitions(
        self, both_started: TaskStore
    ) -> None:
        with both_started.transaction() as repository:
            assert [task.id for task in repository.tasks(TICKET)] == ['T1']
            assert sorted(task.id for task in repository.tasks(OTHER)) == ['T1', 'T2']
            assert repository.attempts_by_worker(TICKET) == {'T1': {'engineer': 1}}
            assert repository.attempts_by_worker(OTHER) == {
                'T1': {'architect': 1},
                'T2': {'engineer': 1},
            }
            assert repository.latest_transitions_into(OTHER, EVERY_STATUS, MANY) == [
                STARTED,
                SECOND_STARTED,
            ]


class TestOneTransactionForTheThree:
    @pytest.fixture
    def written_together(self, staged: TaskStore) -> TaskStore:
        with staged.transaction() as repository:
            repository.tickets.mark_in_progress(TICKET)
            repository.contracts.approve(TICKET, [COMMAND], APPROVAL)
            repository.record_start(TICKET, STARTED, BY_THE_ENGINEER)
        return staged

    @pytest.fixture
    def abandoned_together(self, staged: TaskStore) -> TaskStore:
        with suppress(NotStagedError), staged.transaction() as repository:
            repository.tickets.mark_in_progress(TICKET)
            repository.contracts.approve(TICKET, [COMMAND], APPROVAL)
            repository.record_start(TICKET, STARTED, BY_THE_ENGINEER)
            repository.record_failed_fix(TICKET, 'T1', 'the lock is held too long', at=AT)
            repository.tickets.staged_ticket(NEVER_STAGED)
        return staged

    def test_the_ticket_the_contract_and_the_task_are_kept_together(
        self, written_together: TaskStore
    ) -> None:
        with written_together.transaction() as repository:
            assert repository.tickets.staged_ticket(TICKET).status is TicketStatus.IN_PROGRESS
            assert [command.id for command in repository.contracts.commands(TICKET)] == ['T1.AC-1']
            assert [task.id for task in repository.tasks(TICKET)] == ['T1']

    def test_a_transaction_that_fails_keeps_nothing_of_the_three(
        self, abandoned_together: TaskStore
    ) -> None:
        with abandoned_together.transaction() as repository:
            assert repository.tickets.staged_ticket(TICKET).status is TicketStatus.STAGED
            assert repository.contracts.commands(TICKET) == []
            assert repository.tasks(TICKET) == []
            assert repository.attempts_by_worker(TICKET) == {}
            assert repository.failed_fixes(TICKET, 'T1') == []
            assert repository.latest_transitions_into(TICKET, EVERY_STATUS, MANY) == []
