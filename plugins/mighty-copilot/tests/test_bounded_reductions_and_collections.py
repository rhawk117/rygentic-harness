from collections.abc import Callable, Sized
from dataclasses import dataclass
from types import MappingProxyType

import pytest
import sqlalchemy as sql
from mightymodels.core.database import Database, ReadLimit, ReadLimitError
from mightymodels.core.routing import Depth, Scope
from mightymodels.core.run_id import RunId
from mightymodels.tools.contract.repository import COMMANDS
from mightymodels.tools.contract.schema import Outcome, Phase
from mightymodels.tools.contract.tables import CommandRow, ReceiptRow
from mightymodels.tools.investigation.repository import ENTRIES, investigation_store
from mightymodels.tools.investigation.tables import LedgerEntryRow
from mightymodels.tools.review.repository import FINDINGS, review_store
from mightymodels.tools.review.schema import Emphasis, ReviewScope
from mightymodels.tools.review.tables import (
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels.tools.task.gates import STUCK
from mightymodels.tools.task.repository import (
    ATTEMPT_COUNTS,
    FAILED_FIXES,
    TASKS,
    task_store,
)
from mightymodels.tools.task.schema import ArchitectMode, Implementer, Status
from mightymodels.tools.task.tables import AttemptRow, FailedFixRow, TaskRow, TransitionRow
from mightymodels.tools.tests.bounded_reads import (
    A_FINDING,
    AN_ENTRY,
    LEDGER,
    NEVER_STARTED,
    OTHER_LEDGER,
    RUN,
    SLUG,
    SNAPSHOT_LIMIT,
    TARGET,
    TASK,
    TICKET,
    Read,
    SizedRead,
    attempt_counts,
    attempts_in_modes,
    commands,
    commands_of_the_ticket,
    decisions_on,
    dispositions,
    entries_of_the_ledger,
    finding_ids,
    findings_of_the_run,
    latest_receipts,
    ledger_entries,
    outcomes,
    outcomes_of,
    selects_of,
    store,
    stuck_transitions,
    tasks,
    tasks_of_the_ticket,
    unrecorded_investigations,
)
from mightymodels.tools.ticket.tables import TicketRow

type Write = Callable[[Database], None]

OTHER_TASK = 'T2'
A_PASSING_RUN = MappingProxyType({'outcome': Outcome.PASSED, 'phase': Phase.TASK})
A_RUN = MappingProxyType(
    {
        'scope': ReviewScope.CODEBASE,
        'depth': Depth.DEEP,
        'emphasis': Emphasis.BALANCED,
        'weights': {},
        'models': {},
    }
)


def failed_fixes(database: Database) -> Sized:
    with task_store(database).transaction() as repository:
        return repository.failed_fixes(TICKET, TASK)


def a_ticket_with_two_tasks(database: Database) -> None:
    store(database, TicketRow, [{'slug': SLUG, 'scope': Scope.MED, 'models': {}}])
    store(database, TaskRow, [{'slug': SLUG, 'task_id': task} for task in (TASK, OTHER_TASK)])


def two_approved_commands(database: Database) -> None:
    store(database, CommandRow, [{'slug': SLUG, 'command_id': name} for name in ('a', 'b')])


def a_run_of_every_command(database: Database) -> None:
    with database.transaction() as session:
        taken = session.scalars(sql.select(sql.func.count()).select_from(ReceiptRow)).one()
    run = [
        {'slug': SLUG, 'command_id': name, 'duration_ms': taken + number, **A_PASSING_RUN}
        for number, name in enumerate(('a', 'b') * 5, start=1)
    ]
    store(database, ReceiptRow, run)


def an_attempt_by_each_worker(database: Database) -> None:
    tried = [
        {'slug': SLUG, 'task_id': task, 'worker': worker, 'mode': mode}
        for task in (TASK, OTHER_TASK)
        for worker, mode in (
            (Implementer.ENGINEER, None),
            (Implementer.ARCHITECT, ArchitectMode.RECOVERY_IMPLEMENTATION),
        )
    ]
    store(database, AttemptRow, tried * 5)


def twelve_findings_of(run: RunId, database: Database) -> None:
    store(database, ReviewRunRow, [{**A_RUN, 'run_id': run.root}])
    found = [
        {**A_FINDING, 'run_id': run.root, 'finding_id': f'F{number}'} for number in range(12, 0, -1)
    ]
    store(database, ReviewFindingRow, found)


def twelve_findings(database: Database) -> None:
    twelve_findings_of(RUN, database)


def findings_of_two_other_runs(database: Database) -> None:
    with review_store(database).transaction() as repository:
        recorded = len(repository.latest_runs().rows)
    for number in (recorded, recorded + 1):
        twelve_findings_of(RunId(f'20260929-{number:06d}'), database)


def two_started_investigations(database: Database) -> None:
    with investigation_store(database).transaction() as repository:
        repository.append(LEDGER, [TARGET])
        repository.append(OTHER_LEDGER, [TARGET])


def twenty_more_entries_in_each_ledger(database: Database) -> None:
    with investigation_store(database).transaction() as repository:
        recorded = len(repository.entries(LEDGER))
    entries = [
        {**AN_ENTRY, 'investigation_id': ledger.root, 'seq': recorded + number}
        for ledger in (LEDGER, OTHER_LEDGER)
        for number in range(1, 21)
    ]
    store(database, LedgerEntryRow, entries)


def ten_failed_transitions(database: Database) -> None:
    with task_store(database).transaction() as repository:
        recorded = len(repository.latest_transitions_into(TICKET, STUCK, limit=1000))
    failed = [
        {
            'slug': SLUG,
            'task_id': TASK,
            'before': Status.IN_PROGRESS,
            'after': Status.FAILED,
            'head': str(recorded + number),
        }
        for number in range(10)
    ]
    store(database, TransitionRow, failed)


@dataclass(slots=True, kw_only=True, frozen=True)
class Reduction:
    arrange: Write
    add_history: Write
    read: Read
    fetched: int
    answer: object


@dataclass(slots=True, kw_only=True, frozen=True)
class FetchedTwice:
    early: list[int]
    late: list[int]
    answer: object


class TestAReductionTheDatabaseDoes:
    REDUCTIONS = (
        pytest.param(
            Reduction(
                arrange=two_approved_commands,
                add_history=a_run_of_every_command,
                read=latest_receipts,
                fetched=2,
                answer={'a': 49, 'b': 50},
            ),
            id='latest-receipt-per-command',
        ),
        pytest.param(
            Reduction(
                arrange=a_ticket_with_two_tasks,
                add_history=an_attempt_by_each_worker,
                read=attempt_counts,
                fetched=4,
                answer=[
                    (TASK, Implementer.ENGINEER, 25),
                    (TASK, Implementer.ARCHITECT, 25),
                    (OTHER_TASK, Implementer.ENGINEER, 25),
                    (OTHER_TASK, Implementer.ARCHITECT, 25),
                ],
            ),
            id='attempt-counts',
        ),
        pytest.param(
            Reduction(
                arrange=a_ticket_with_two_tasks,
                add_history=an_attempt_by_each_worker,
                read=attempts_in_modes,
                fetched=1,
                answer=25,
            ),
            id='attempts-in-modes',
        ),
        pytest.param(
            Reduction(
                arrange=twelve_findings,
                add_history=findings_of_two_other_runs,
                read=finding_ids,
                fetched=12,
                answer=[f'F{number}' for number in range(1, 13)],
            ),
            id='findings-order',
        ),
        pytest.param(
            Reduction(
                arrange=two_started_investigations,
                add_history=twenty_more_entries_in_each_ledger,
                read=unrecorded_investigations,
                fetched=2,
                answer=[NEVER_STARTED],
            ),
            id='unrecorded-investigations',
        ),
        pytest.param(
            Reduction(
                arrange=a_ticket_with_two_tasks,
                add_history=ten_failed_transitions,
                read=stuck_transitions,
                fetched=SNAPSHOT_LIMIT,
                answer=['47', '48', '49'],
            ),
            id='stuck-transitions',
        ),
    )
    MORE_HISTORY = 4

    @pytest.fixture
    def fetched_twice(self, reduction: Reduction, repository_database: Database) -> FetchedTwice:
        reduction.arrange(repository_database)
        reduction.add_history(repository_database)
        early = selects_of(reduction.read, repository_database).rows_fetched()
        for _ in range(self.MORE_HISTORY):
            reduction.add_history(repository_database)
        late = selects_of(reduction.read, repository_database).rows_fetched()
        return FetchedTwice(early=early, late=late, answer=reduction.read(repository_database))

    @pytest.mark.parametrize('reduction', REDUCTIONS)
    def test_fetches_the_same_number_of_rows_after_five_times_the_history(
        self, reduction: Reduction, fetched_twice: FetchedTwice
    ) -> None:
        assert fetched_twice.early == [reduction.fetched]
        assert fetched_twice.late == [reduction.fetched]

    @pytest.mark.parametrize('reduction', REDUCTIONS)
    def test_answers_as_the_whole_history_would(
        self, reduction: Reduction, fetched_twice: FetchedTwice
    ) -> None:
        assert fetched_twice.answer == reduction.answer


def a_receipt_of_every_command(database: Database, count: int) -> None:
    commands_of_the_ticket(database, count)
    run = [{'slug': SLUG, 'command_id': f'c{number}', **A_PASSING_RUN} for number in range(count)]
    store(database, ReceiptRow, run)


def an_attempt_at_every_task(database: Database, count: int) -> None:
    tasks_of_the_ticket(database, count)
    tried = [{'slug': SLUG, 'task_id': f'T{number}'} for number in range(count)]
    store(database, AttemptRow, tried)


def a_failed_fix_for_the_task(database: Database, count: int) -> None:
    a_ticket_with_two_tasks(database)
    store(database, FailedFixRow, [{'slug': SLUG, 'task_id': TASK}] * count)


def a_decision_on_every_finding(database: Database, count: int) -> None:
    findings_of_the_run(database, count)
    store(database, ReviewDispositionRow, decisions_on(range(count)))


def an_outcome_of_every_finding(database: Database, count: int) -> None:
    a_decision_on_every_finding(database, count)
    store(database, ReviewOutcomeRow, outcomes_of(range(count)))


@dataclass(slots=True, kw_only=True, frozen=True)
class Collection:
    limit: ReadLimit
    fill: Callable[[Database, int], None]
    read: SizedRead
    owner: str


class TestACollectionReadWhole:
    OF_THE_TICKET = f'ticket {SLUG}'
    OF_THE_RUN = f'run {RUN}'
    COLLECTIONS = (
        pytest.param(
            Collection(
                limit=COMMANDS, fill=commands_of_the_ticket, read=commands, owner=OF_THE_TICKET
            ),
            id='contract-commands',
        ),
        pytest.param(
            Collection(
                limit=COMMANDS,
                fill=a_receipt_of_every_command,
                read=latest_receipts,
                owner=OF_THE_TICKET,
            ),
            id='latest-receipts',
        ),
        pytest.param(
            Collection(limit=TASKS, fill=tasks_of_the_ticket, read=tasks, owner=OF_THE_TICKET),
            id='tasks',
        ),
        pytest.param(
            Collection(
                limit=ATTEMPT_COUNTS,
                fill=an_attempt_at_every_task,
                read=attempt_counts,
                owner=OF_THE_TICKET,
            ),
            id='attempt-counts',
        ),
        pytest.param(
            Collection(
                limit=FAILED_FIXES,
                fill=a_failed_fix_for_the_task,
                read=failed_fixes,
                owner=f'task {TASK} of ticket {SLUG}',
            ),
            id='failed-fixes',
        ),
        pytest.param(
            Collection(
                limit=FINDINGS, fill=findings_of_the_run, read=finding_ids, owner=OF_THE_RUN
            ),
            id='review-findings',
        ),
        pytest.param(
            Collection(
                limit=FINDINGS,
                fill=a_decision_on_every_finding,
                read=dispositions,
                owner=OF_THE_RUN,
            ),
            id='review-dispositions',
        ),
        pytest.param(
            Collection(
                limit=FINDINGS, fill=an_outcome_of_every_finding, read=outcomes, owner=OF_THE_RUN
            ),
            id='review-outcomes',
        ),
        pytest.param(
            Collection(
                limit=ENTRIES,
                fill=entries_of_the_ledger,
                read=ledger_entries,
                owner=f'investigation {LEDGER}',
            ),
            id='ledger-entries',
        ),
    )

    @pytest.fixture
    def filled_to_the_limit(
        self, collection: Collection, repository_database: Database
    ) -> Database:
        collection.fill(repository_database, collection.limit.rows)
        return repository_database

    @pytest.fixture
    def filled_past_the_limit(
        self, collection: Collection, repository_database: Database
    ) -> Database:
        collection.fill(repository_database, collection.limit.rows + 2)
        return repository_database

    @pytest.mark.parametrize('collection', COLLECTIONS)
    def test_at_its_limit_is_returned_whole(
        self, collection: Collection, filled_to_the_limit: Database
    ) -> None:
        assert len(collection.read(filled_to_the_limit)) == collection.limit.rows

    @pytest.mark.parametrize('collection', COLLECTIONS)
    def test_past_its_limit_is_refused_by_name_and_not_cut(
        self, collection: Collection, filled_past_the_limit: Database
    ) -> None:
        with pytest.raises(ReadLimitError) as refused:
            collection.read(filled_past_the_limit)

        assert (refused.value.owner, refused.value.rows, refused.value.kept) == (
            collection.owner,
            collection.limit.rows,
            collection.limit.kept,
        )
        assert f'{collection.owner} holds more than {collection.limit.rows}' in str(refused.value)

    @pytest.mark.parametrize('collection', COLLECTIONS)
    def test_past_its_limit_fetches_one_row_more_than_the_limit(
        self, collection: Collection, filled_past_the_limit: Database
    ) -> None:
        selects = selects_of(collection.read, filled_past_the_limit)

        assert selects.rows_fetched() == [collection.limit.fetched]
