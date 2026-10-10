"""Every read of the state database is bounded: what its statements say and what they fetch.

A write that adds to what a whole read returns is held to that read's limit, so no write the
plugin accepts makes a ticket, a run or an investigation unreadable.
"""

from collections.abc import Callable, Iterable, Sized
from contextlib import suppress
from dataclasses import dataclass
from types import MappingProxyType

import pytest
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import (
    Database,
    Latest,
    ReadLimit,
    ReadLimitError,
    WriteLimitError,
)
from mightymodels_plugin.core.declarative import Base
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.contract.repository import COMMANDS, contract_transaction
from mightymodels_plugin.tools.contract.schema import ContractCommand
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.contract.tables import CommandRow, ReceiptRow
from mightymodels_plugin.tools.crashout import service as crashouts
from mightymodels_plugin.tools.crashout.repository import JOURNAL_WINDOW, crashout_transaction
from mightymodels_plugin.tools.crashout.schema import JournaledCrashout, Severity, Verdict
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.investigation import service as investigations
from mightymodels_plugin.tools.investigation.repository import (
    ENTRIES,
    INVESTIGATIONS_LISTED,
    TARGET_SEQ,
    LedgerRecord,
    investigation_transaction,
)
from mightymodels_plugin.tools.investigation.schema import (
    EntryKind,
    LedgerEntry,
    Source,
    TargetKind,
)
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.review import service as reviews
from mightymodels_plugin.tools.review.repository import (
    FINDINGS,
    RUNS_LISTED,
    DecidedFinding,
    ResolvedFinding,
    review_transaction,
)
from mightymodels_plugin.tools.review.schema import (
    Decision,
    Emphasis,
    FindingInput,
    Persona,
    ReportedSeverity,
    Result,
    ReviewRun,
    ReviewScope,
    Shape,
)
from mightymodels_plugin.tools.review.schema import Severity as FindingSeverity
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.review.tables import (
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels_plugin.tools.task.gates import STUCK
from mightymodels_plugin.tools.task.repository import (
    ATTEMPT_COUNTS,
    FAILED_FIXES,
    TASKS,
    task_transaction,
)
from mightymodels_plugin.tools.task.schema import ArchitectMode, Implementer, Status, TaskStart
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.task.tables import AttemptRow, FailedFixRow, TaskRow, TransitionRow
from mightymodels_plugin.tools.tests.support import (
    RowValues,
    SelectsSent,
    filled_row,
    selects_sent_to,
    table_of,
)
from mightymodels_plugin.tools.ticket.repository import ticket_transaction
from mightymodels_plugin.tools.ticket.tables import TicketRow
from sqlalchemy import insert

type Read = Callable[[Database], object]
type SizedRead = Callable[[Database], Sized]
type Write = Callable[[Database], None]

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
TASK = 'T1'
OTHER_TASK = 'T2'
RUN = RunId('20260928-120000')
LEDGER = Slug('20260928-queue')
OTHER_LEDGER = Slug('20260928-drain')
NEVER_STARTED = Slug('20260928-never-started')
MODES = frozenset(ArchitectMode)
SNAPSHOT_LIMIT = 3
JOURNALED = JournaledCrashout(
    at='2026-09-28T12:00:00+00:00',
    ticket=None,
    branch=None,
    severity=Severity.HEATED,
    verdict=Verdict.DESERVED,
    rant='why did you skip the tests',
    failures=('skipped the tests',),
    root_cause='optimised for speed',
    corrective_action='run the gate before reporting',
    barked_back=False,
)
TARGET = LedgerRecord(
    seq=TARGET_SEQ,
    round=0,
    kind=EntryKind.TARGET,
    text='queue',
    source=Source.USER,
    cite=TargetKind.BEHAVIOR,
    supersedes=(),
    at='2026-09-28T12:00:00+00:00',
    head=None,
)
A_FINDING = MappingProxyType(
    {'run_id': RUN.root, 'sources': ['MV-1'], 'severity': FindingSeverity.HIGH}
)
AN_ENTRY = MappingProxyType(
    {'investigation_id': LEDGER.root, 'kind': EntryKind.OPEN, 'source': Source.USER}
)


def store(database: Database, row_type: type[Base], rows: Iterable[RowValues]) -> None:
    key = database.repository_key.root
    filled = [filled_row(row_type, **row, repository_key=key) for row in rows]
    with database.transaction() as session:
        session.execute(insert(table_of(row_type)), filled)


def ticket_row(database: Database) -> None:
    with ticket_transaction(database) as repository:
        repository.row(TICKET)


def commands(database: Database) -> Sized:
    with contract_transaction(database) as repository:
        return repository.commands(TICKET)


def latest_receipts(database: Database) -> dict[str, int]:
    with contract_transaction(database) as repository:
        latest = repository.latest_receipts(TICKET)
        return {command: receipt.id for command, receipt in latest.items()}


def task_row(database: Database) -> None:
    with task_transaction(database) as repository:
        repository.row(TICKET, TASK)


def tasks(database: Database) -> Sized:
    with task_transaction(database) as repository:
        return repository.rows(TICKET)


def attempt_counts(database: Database) -> list[tuple[str, str, int]]:
    with task_transaction(database) as repository:
        counts = repository.attempts_by_worker(TICKET)
    return [
        (task, worker, count)
        for task, by_worker in counts.items()
        for worker, count in by_worker.items()
    ]


def failed_fixes(database: Database) -> Sized:
    with task_transaction(database) as repository:
        return repository.failed_fixes(TICKET, TASK)


def attempts_in_modes(database: Database) -> int:
    with task_transaction(database) as repository:
        return repository.attempts_in_modes(TICKET, TASK, MODES)


def stuck_transitions(database: Database) -> list[str]:
    with task_transaction(database) as repository:
        latest = repository.latest_transitions_into(TICKET, STUCK, SNAPSHOT_LIMIT)
        return [str(transition.head) for transition in latest]


def run_row(database: Database) -> None:
    with review_transaction(database) as repository:
        repository.run_row(RUN)


def latest_runs(database: Database) -> Latest[str]:
    with review_transaction(database) as repository:
        latest = repository.latest_run_rows()
        return Latest(
            rows=tuple(row.run_id for row in latest.rows), older_left_out=latest.older_left_out
        )


def latest_run_of_the_ticket(database: Database) -> None:
    with review_transaction(database) as repository:
        repository.latest_run_row(TICKET)


def finding_ids(database: Database) -> list[str]:
    with review_transaction(database) as repository:
        return [row.finding_id for row in repository.finding_rows(RUN)]


def dispositions(database: Database) -> Sized:
    with review_transaction(database) as repository:
        return repository.decisions.disposition_rows(RUN)


def outcomes(database: Database) -> Sized:
    with review_transaction(database) as repository:
        return repository.decisions.outcome_rows(RUN)


def ledger_target(database: Database) -> None:
    with investigation_transaction(database) as repository:
        repository.has_entries(LEDGER)


def ledger_entries(database: Database) -> Sized:
    with investigation_transaction(database) as repository:
        return repository.entry_rows(LEDGER)


def unrecorded_investigations(database: Database) -> list[Slug]:
    with ticket_transaction(database) as repository:
        return repository.unrecorded_investigations([LEDGER, OTHER_LEDGER, NEVER_STARTED])


def latest_investigations(database: Database) -> Latest[str]:
    with investigation_transaction(database) as repository:
        latest = repository.latest_rounds()
    return Latest(
        rows=tuple(investigation for investigation, _ in latest.rows),
        older_left_out=latest.older_left_out,
    )


def latest_crashouts(database: Database) -> Latest[str]:
    with crashout_transaction(database) as repository:
        latest = repository.latest_rows()
        return Latest(
            rows=tuple(row.at for row in latest.rows), older_left_out=latest.older_left_out
        )


def latest_crashout(database: Database) -> None:
    with crashout_transaction(database) as repository:
        repository.latest_row()


def selects_of(read: Read, database: Database) -> SelectsSent:
    with selects_sent_to(database) as selects, suppress(ReadLimitError):
        read(database)
    return selects


READS_OF_ROWS = (
    pytest.param(commands, id='contract-commands'),
    pytest.param(latest_receipts, id='latest-receipts'),
    pytest.param(tasks, id='tasks'),
    pytest.param(attempt_counts, id='attempt-counts'),
    pytest.param(stuck_transitions, id='stuck-transitions'),
    pytest.param(latest_runs, id='latest-review-runs'),
    pytest.param(latest_run_of_the_ticket, id='latest-review-run-of-a-ticket'),
    pytest.param(finding_ids, id='review-findings'),
    pytest.param(dispositions, id='review-dispositions'),
    pytest.param(outcomes, id='review-outcomes'),
    pytest.param(ledger_entries, id='ledger-entries'),
    pytest.param(unrecorded_investigations, id='unrecorded-investigations'),
    pytest.param(latest_investigations, id='latest-investigations'),
    pytest.param(latest_crashouts, id='latest-crashouts'),
    pytest.param(latest_crashout, id='latest-crashout'),
)
READS_OF_ONE_ROW = (
    pytest.param(ticket_row, id='ticket'),
    pytest.param(task_row, id='task'),
    pytest.param(attempts_in_modes, id='attempts-in-modes'),
    pytest.param(run_row, id='review-run'),
    pytest.param(ledger_target, id='ledger-target'),
)


class TestEveryRead:
    @pytest.mark.parametrize('read', READS_OF_ROWS)
    def test_that_returns_rows_carries_a_limit_in_sql(
        self, read: Read, repository_database: Database
    ) -> None:
        sent = selects_of(read, repository_database).sent

        assert len(sent) > 0
        assert [select.sql for select in sent if ' LIMIT ' not in select.sql] == []

    @pytest.mark.parametrize('read', [*READS_OF_ROWS, *READS_OF_ONE_ROW])
    def test_searches_an_index_and_scans_no_table(
        self, read: Read, repository_database: Database
    ) -> None:
        steps = selects_of(read, repository_database).plan_steps()

        assert [step for step in steps if step.startswith('SEARCH')] != []
        assert [step for step in steps if step.startswith('SCAN')] == []


def journal_crashouts(database: Database, count: int) -> list[str]:
    times = [f'2026-09-28T12:{number // 60:02d}:{number % 60:02d}+00:00' for number in range(count)]
    with crashout_transaction(database) as repository:
        for at in times:
            repository.journal(JOURNALED.model_copy(update={'at': at}))
    return times


def started(run: RunId) -> ReviewRun:
    return ReviewRun(
        run_id=run,
        slug=None,
        scope=ReviewScope.CODEBASE,
        base=None,
        head=None,
        depth=Depth.DEEP,
        emphasis=Emphasis.BALANCED,
        weights=dict.fromkeys(Persona, 0.5),
        personas=tuple(Persona),
        models={},
        created_at=now(),
    )


def start_runs(database: Database, count: int) -> list[str]:
    runs = [RunId(f'20260928-{number:06d}') for number in range(count)]
    with review_transaction(database) as repository:
        for run in runs:
            repository.record_run(started(run))
    return [run.root for run in runs]


def start_investigations(database: Database, count: int) -> list[str]:
    started = [Slug(f'20260928-queue-{number:04d}') for number in range(count)]
    with investigation_transaction(database) as repository:
        for investigation in started:
            repository.append(investigation, [TARGET])
    return [investigation.root for investigation in started]


def crashout_stats(_workspace: Workspace, database: Database) -> str:
    return CrashoutService(database=database).stats().text


def review_listing(workspace: Workspace, database: Database) -> str:
    return ReviewService(workspace=workspace, database=database).listing().text


def investigation_listing(workspace: Workspace, database: Database) -> str:
    return InvestigationService(workspace=workspace, database=database).listing().text


@dataclass(slots=True, kw_only=True, frozen=True)
class History:
    window: ReadLimit
    write: Callable[[Database, int], list[str]]
    latest: Callable[[Database], Latest[str]]
    told: Callable[[Workspace, Database], str]
    left_out_note: str


@dataclass(slots=True, kw_only=True, frozen=True)
class WrittenHistory:
    database: Database
    names: list[str]


class TestAReadOfARepositorysHistory:
    PAST_THE_WINDOW = 5
    HISTORIES = (
        pytest.param(
            History(
                window=JOURNAL_WINDOW,
                write=journal_crashouts,
                latest=latest_crashouts,
                told=crashout_stats,
                left_out_note=crashouts.OLDER_LEFT_OUT,
            ),
            id='crashouts',
        ),
        pytest.param(
            History(
                window=RUNS_LISTED,
                write=start_runs,
                latest=latest_runs,
                told=review_listing,
                left_out_note=reviews.OLDER_LEFT_OUT,
            ),
            id='review-runs',
        ),
        pytest.param(
            History(
                window=INVESTIGATIONS_LISTED,
                write=start_investigations,
                latest=latest_investigations,
                told=investigation_listing,
                left_out_note=investigations.OLDER_LEFT_OUT,
            ),
            id='investigations',
        ),
    )

    @pytest.fixture
    def filling_the_window(self, history: History, repository_database: Database) -> WrittenHistory:
        names = history.write(repository_database, history.window.rows)
        return WrittenHistory(database=repository_database, names=names)

    @pytest.fixture
    def past_the_window(self, history: History, repository_database: Database) -> WrittenHistory:
        names = history.write(repository_database, history.window.rows + self.PAST_THE_WINDOW)
        return WrittenHistory(database=repository_database, names=names)

    @pytest.mark.parametrize('history', HISTORIES)
    def test_that_fills_the_window_returns_all_of_it_oldest_first(
        self, history: History, filling_the_window: WrittenHistory
    ) -> None:
        assert history.latest(filling_the_window.database) == Latest(
            rows=tuple(filling_the_window.names), older_left_out=False
        )

    @pytest.mark.parametrize('history', HISTORIES)
    def test_that_fills_the_window_is_told_with_no_word_of_a_cut(
        self, history: History, filling_the_window: WrittenHistory, repository_workspace: Workspace
    ) -> None:
        told = history.told(repository_workspace, filling_the_window.database)

        assert 'left out' not in told

    @pytest.mark.parametrize('history', HISTORIES)
    def test_past_the_window_fetches_the_window_and_one_row_more(
        self, history: History, past_the_window: WrittenHistory
    ) -> None:
        selects = selects_of(history.latest, past_the_window.database)

        assert selects.rows_fetched() == [history.window.fetched]

    @pytest.mark.parametrize('history', HISTORIES)
    def test_past_the_window_returns_the_newest_and_says_older_ones_are_left_out(
        self, history: History, past_the_window: WrittenHistory
    ) -> None:
        newest = past_the_window.names[self.PAST_THE_WINDOW :]

        assert history.latest(past_the_window.database) == Latest(
            rows=tuple(newest), older_left_out=True
        )

    @pytest.mark.parametrize('history', HISTORIES)
    def test_past_the_window_is_told_as_cut_to_the_latest(
        self, history: History, past_the_window: WrittenHistory, repository_workspace: Workspace
    ) -> None:
        told = history.told(repository_workspace, past_the_window.database)

        assert told.endswith(history.left_out_note)
        assert str(history.window.rows) in history.left_out_note


def a_ticket_with_two_tasks(database: Database) -> None:
    store(database, TicketRow, [{'slug': SLUG}])
    store(database, TaskRow, [{'slug': SLUG, 'task_id': task} for task in (TASK, OTHER_TASK)])


def two_approved_commands(database: Database) -> None:
    store(database, CommandRow, [{'slug': SLUG, 'command_id': name} for name in ('a', 'b')])


def a_run_of_every_command(database: Database) -> None:
    store(database, ReceiptRow, [{'slug': SLUG, 'command_id': name} for name in ('a', 'b')] * 5)


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
    store(database, ReviewRunRow, [{'run_id': run.root}])
    found = [{'run_id': run.root, 'finding_id': f'F{number}'} for number in range(12, 0, -1)]
    store(database, ReviewFindingRow, found)


def twelve_findings(database: Database) -> None:
    twelve_findings_of(RUN, database)


def findings_of_two_other_runs(database: Database) -> None:
    with review_transaction(database) as repository:
        recorded = len(repository.latest_run_rows().rows)
    for number in (recorded, recorded + 1):
        twelve_findings_of(RunId(f'20260929-{number:06d}'), database)


def two_started_investigations(database: Database) -> None:
    with investigation_transaction(database) as repository:
        repository.append(LEDGER, [TARGET])
        repository.append(OTHER_LEDGER, [TARGET])


def twenty_more_entries_in_each_ledger(database: Database) -> None:
    with investigation_transaction(database) as repository:
        recorded = len(repository.entry_rows(LEDGER))
    entries = [
        {'investigation_id': ledger.root, 'seq': recorded + number}
        for ledger in (LEDGER, OTHER_LEDGER)
        for number in range(1, 21)
    ]
    store(database, LedgerEntryRow, entries)


def ten_failed_transitions(database: Database) -> None:
    with task_transaction(database) as repository:
        recorded = len(repository.latest_transitions_into(TICKET, STUCK, limit=1000))
    failed = [
        {'slug': SLUG, 'task_id': TASK, 'after': Status.FAILED, 'head': str(recorded + number)}
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


def decisions_on(numbers: range) -> list[RowValues]:
    return [
        {'run_id': RUN.root, 'finding_id': f'F{number}', 'decision': Decision.FIX}
        for number in numbers
    ]


def outcomes_of(numbers: range) -> list[RowValues]:
    return [
        {'run_id': RUN.root, 'finding_id': f'F{number}', 'result': Result.FIXED}
        for number in numbers
    ]


def commands_of_the_ticket(database: Database, count: int) -> None:
    named = [{'slug': SLUG, 'command_id': f'c{number}'} for number in range(count)]
    store(database, CommandRow, named)


def a_receipt_of_every_command(database: Database, count: int) -> None:
    commands_of_the_ticket(database, count)
    run = [{'slug': SLUG, 'command_id': f'c{number}'} for number in range(count)]
    store(database, ReceiptRow, run)


def tasks_of_the_ticket(database: Database, count: int) -> None:
    store(database, TicketRow, [{'slug': SLUG}])
    started = [
        {'slug': SLUG, 'task_id': f'T{number}', 'status': Status.VERIFIED}
        for number in range(count)
    ]
    store(database, TaskRow, started)


def an_attempt_at_every_task(database: Database, count: int) -> None:
    tasks_of_the_ticket(database, count)
    tried = [{'slug': SLUG, 'task_id': f'T{number}'} for number in range(count)]
    store(database, AttemptRow, tried)


def a_failed_fix_for_the_task(database: Database, count: int) -> None:
    a_ticket_with_two_tasks(database)
    store(database, FailedFixRow, [{'slug': SLUG, 'task_id': TASK}] * count)


def findings_of_the_run(database: Database, count: int) -> None:
    with review_transaction(database) as repository:
        repository.record_run(started(RUN))
    found = [{**A_FINDING, 'finding_id': f'F{number}'} for number in range(count)]
    store(database, ReviewFindingRow, found)


def a_decision_on_every_finding(database: Database, count: int) -> None:
    findings_of_the_run(database, count)
    store(database, ReviewDispositionRow, decisions_on(range(count)))


def an_outcome_of_every_finding(database: Database, count: int) -> None:
    a_decision_on_every_finding(database, count)
    store(database, ReviewOutcomeRow, outcomes_of(range(count)))


def entries_of_the_ledger(database: Database, count: int) -> None:
    entries = [{**AN_ENTRY, 'seq': number} for number in range(1, count + 1)]
    store(database, LedgerEntryRow, entries)


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


def decisions_in_a_full_run(database: Database, count: int) -> None:
    findings_of_the_run(database, FINDINGS.rows)
    store(database, ReviewDispositionRow, decisions_on(range(count)))


def outcomes_in_a_full_run(database: Database, count: int) -> None:
    decisions_in_a_full_run(database, FINDINGS.rows)
    store(database, ReviewOutcomeRow, outcomes_of(range(count)))


def approve_commands(workspace: Workspace, database: Database, numbers: range) -> None:
    approved = [
        ContractCommand(id=f'c{number}', argv=('true',), approved_by='user') for number in numbers
    ]
    ContractService(workspace=workspace, database=database).approve(TICKET, approved)


def start_tasks(workspace: Workspace, database: Database, numbers: range) -> None:
    service = TaskService(workspace=workspace, database=database)
    change = TaskStart(by=Implementer.ENGINEER, owned=('src/queue.py',))
    for number in numbers:
        service.start(TICKET, f'T{number}', change)


def add_findings(workspace: Workspace, database: Database, numbers: range) -> None:
    found = [
        FindingInput(
            sources=('MV-1',),
            severity=ReportedSeverity.HIGH,
            title='the drain loop sleeps between batches',
            location=f'src/queue.py:{number}',
            fix='drain in one pass',
            verify='run the drain test',
        )
        for number in numbers
    ]
    ReviewService(workspace=workspace, database=database).add_findings(RUN, found)


def decide_findings(_workspace: Workspace, database: Database, numbers: range) -> None:
    decided = [
        DecidedFinding(
            finding_id=f'F{number}', decision=Decision.FIX, reason='', by='user', at=now()
        )
        for number in numbers
    ]
    with review_transaction(database) as repository:
        repository.decisions.record_dispositions(RUN, decided)


def resolve_findings(_workspace: Workspace, database: Database, numbers: range) -> None:
    with review_transaction(database) as repository:
        for number in numbers:
            repository.decisions.record_outcome(
                RUN,
                ResolvedFinding(
                    finding_id=f'F{number}',
                    result=Result.FIXED,
                    commit='abc1234',
                    reason='',
                    at=now(),
                ),
            )


def add_entries(workspace: Workspace, database: Database, numbers: range) -> None:
    entries = [
        LedgerEntry(kind=EntryKind.OPEN, text=f'question {number}', source=Source.USER)
        for number in numbers
    ]
    InvestigationService(workspace=workspace, database=database).add(LEDGER, 1, entries)


def contract_status(workspace: Workspace, database: Database) -> str:
    return ContractService(workspace=workspace, database=database).status(TICKET).text


def task_listing(workspace: Workspace, database: Database) -> str:
    return TaskService(workspace=workspace, database=database).show(TICKET).text


def review_report(workspace: Workspace, database: Database) -> str:
    return ReviewService(workspace=workspace, database=database).report(RUN, Shape.FULL).text


def rendered_ledger(workspace: Workspace, database: Database) -> str:
    return InvestigationService(workspace=workspace, database=database).render(LEDGER).text


@dataclass(slots=True, kw_only=True, frozen=True)
class CappedWrite:
    limit: ReadLimit
    fill: Callable[[Database, int], None]
    write: Callable[[Workspace, Database, range], None]
    rows_written: int
    read: SizedRead
    told: Callable[[Workspace, Database], str]
    owner: str


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedWrite:
    database: Database
    held: int
    told_before: str
    refusal: WriteLimitError
    told_after: str


class TestAWriteToACollectionReadWhole:
    OF_THE_TICKET = f'ticket {SLUG}'
    OF_THE_RUN = f'run {RUN}'
    WRITES = (
        pytest.param(
            CappedWrite(
                limit=COMMANDS,
                fill=commands_of_the_ticket,
                write=approve_commands,
                rows_written=2,
                read=commands,
                told=contract_status,
                owner=OF_THE_TICKET,
            ),
            id='contract-commands',
        ),
        pytest.param(
            CappedWrite(
                limit=TASKS,
                fill=tasks_of_the_ticket,
                write=start_tasks,
                rows_written=1,
                read=tasks,
                told=task_listing,
                owner=OF_THE_TICKET,
            ),
            id='tasks',
        ),
        pytest.param(
            CappedWrite(
                limit=FINDINGS,
                fill=findings_of_the_run,
                write=add_findings,
                rows_written=2,
                read=finding_ids,
                told=review_report,
                owner=OF_THE_RUN,
            ),
            id='review-findings',
        ),
        pytest.param(
            CappedWrite(
                limit=FINDINGS,
                fill=decisions_in_a_full_run,
                write=decide_findings,
                rows_written=2,
                read=dispositions,
                told=review_report,
                owner=OF_THE_RUN,
            ),
            id='review-dispositions',
        ),
        pytest.param(
            CappedWrite(
                limit=FINDINGS,
                fill=outcomes_in_a_full_run,
                write=resolve_findings,
                rows_written=1,
                read=outcomes,
                told=review_report,
                owner=OF_THE_RUN,
            ),
            id='review-outcomes',
        ),
        pytest.param(
            CappedWrite(
                limit=ENTRIES,
                fill=entries_of_the_ledger,
                write=add_entries,
                rows_written=2,
                read=ledger_entries,
                told=rendered_ledger,
                owner=f'investigation {LEDGER}',
            ),
            id='ledger-entries',
        ),
    )

    @pytest.fixture
    def written_up_to_the_limit(
        self, capped: CappedWrite, repository_workspace: Workspace, repository_database: Database
    ) -> Database:
        held = capped.limit.rows - capped.rows_written
        capped.fill(repository_database, held)
        capped.write(repository_workspace, repository_database, range(held, capped.limit.rows))
        return repository_database

    @pytest.fixture
    def refused_one_row_past_the_limit(
        self, capped: CappedWrite, repository_workspace: Workspace, repository_database: Database
    ) -> RefusedWrite:
        held = capped.limit.rows - capped.rows_written + 1
        capped.fill(repository_database, held)
        told_before = capped.told(repository_workspace, repository_database)
        with pytest.raises(WriteLimitError) as refused:
            capped.write(
                repository_workspace, repository_database, range(held, held + capped.rows_written)
            )
        return RefusedWrite(
            database=repository_database,
            held=held,
            told_before=told_before,
            refusal=refused.value,
            told_after=capped.told(repository_workspace, repository_database),
        )

    @pytest.mark.parametrize('capped', WRITES)
    def test_up_to_its_limit_is_stored_and_read_back_through_the_tool(
        self,
        capped: CappedWrite,
        written_up_to_the_limit: Database,
        repository_workspace: Workspace,
    ) -> None:
        assert len(capped.read(written_up_to_the_limit)) == capped.limit.rows
        assert capped.told(repository_workspace, written_up_to_the_limit) != ''

    @pytest.mark.parametrize('capped', WRITES)
    def test_past_its_limit_is_refused_by_the_owner_and_the_limit(
        self, capped: CappedWrite, refused_one_row_past_the_limit: RefusedWrite
    ) -> None:
        refusal = refused_one_row_past_the_limit.refusal

        assert (refusal.owner, refusal.rows, refusal.kept) == (
            capped.owner,
            capped.limit.rows,
            capped.limit.kept,
        )
        assert f'{capped.owner} would hold more than {capped.limit.rows}' in str(refusal)

    @pytest.mark.parametrize('capped', WRITES)
    def test_past_its_limit_stores_none_of_its_rows(
        self, capped: CappedWrite, refused_one_row_past_the_limit: RefusedWrite
    ) -> None:
        refused = refused_one_row_past_the_limit

        assert len(capped.read(refused.database)) == refused.held

    @pytest.mark.parametrize('capped', WRITES)
    def test_past_its_limit_leaves_what_was_stored_readable_through_the_tool(
        self, refused_one_row_past_the_limit: RefusedWrite
    ) -> None:
        refused = refused_one_row_past_the_limit

        assert refused.told_before != ''
        assert refused.told_after == refused.told_before
