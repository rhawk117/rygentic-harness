"""One database file and two repositories: every read is keyed, and the same ids coexist."""

from collections import Counter
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.declarative import Base
from mightymodels_plugin.core.edge import OpenState, open_state
from mightymodels_plugin.core.process import process_runner
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.close.schema import Closing
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.tools.close.tables import ClosingRow
from mightymodels_plugin.tools.contract.repository import contract_store
from mightymodels_plugin.tools.contract.schema import ContractCommand, Outcome, Phase, Receipt
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.contract.tables import CommandRow, ReceiptRow
from mightymodels_plugin.tools.crashout.repository import crashout_store
from mightymodels_plugin.tools.crashout.schema import CrashoutEntry, Severity, Verdict
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.crashout.tables import CrashoutRow
from mightymodels_plugin.tools.investigation.repository import investigation_store
from mightymodels_plugin.tools.investigation.schema import (
    EntryKind,
    InvestigationStart,
    LedgerEntry,
    Source,
    TargetKind,
)
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.review.repository import review_store
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
from mightymodels_plugin.tools.review.tables import (
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.similarity.repository import similarity_store
from mightymodels_plugin.tools.similarity.schema import Scout, SimilarityKind, SpooledReport
from mightymodels_plugin.tools.similarity.service import SimilarityService
from mightymodels_plugin.tools.similarity.spool import SPOOL_DIRECTORY
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow, SimilarityRow
from mightymodels_plugin.tools.task.repository import task_store
from mightymodels_plugin.tools.task.schema import Implementer, Status
from mightymodels_plugin.tools.task.store import Attempt, Transition
from mightymodels_plugin.tools.task.tables import AttemptRow, FailedFixRow, TaskRow, TransitionRow
from mightymodels_plugin.tools.tests.support import (
    FILES_OF_AN_OPEN_DATABASE,
    StateServer,
    ToolCall,
    text_of,
    tree,
)
from mightymodels_plugin.tools.ticket.repository import ticket_store
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.tools.ticket.tables import TicketRow

type GitRunner = Callable[..., str]
type RowsRead = Callable[[Database], int]

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
TASK = 'T1'
HEAD = 'a' * 40
STARTED = datetime(2026, 9, 28, 12, tzinfo=UTC)
RUN = RunId('20260928-120000')
LEDGER = Slug('20260928-queue')
FIRST_ORIGIN = 'https://github.com/acme/widgets.git'
SECOND_ORIGIN = 'git@github.com:acme/gadgets.git'
FIRST_KEY = 'acme/widgets'
SECOND_KEY = 'acme/gadgets'
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': 'fix/retry-queue',
        'context': ['drain loop sleeps between batches'],
    }
)
COMMAND = ContractCommand(id='T1.AC-1', argv=('uv', 'run', 'pytest'), approved_by='user')
REVIEW = StartPayload(
    scope=ReviewScope.CODEBASE, depth=Depth.DEEP, emphasis=Emphasis.BALANCED, slug=TICKET
)
FINDING = FindingInput(
    sources=('MV-1',),
    severity=ReportedSeverity.HIGH,
    title='the drain loop sleeps',
    location='src/queue.py:1',
    fix='fix it',
    verify='run the tests',
)
FIX_IT = DisposePayload(by='user', decisions={'F1': Disposition(decision=Decision.FIX)})
FIXED = ResolvePayload(finding='F1', result=Result.FIXED, commit=HEAD)
LEDGER_TARGET = InvestigationStart(target='queue', kind=TargetKind.BEHAVIOR)
LEDGER_DECISION = LedgerEntry(
    kind=EntryKind.DECISION, text='keep the 10s floor', source=Source.USER
)
CRASHOUT = CrashoutEntry(
    severity=Severity.HEATED,
    verdict=Verdict.DESERVED,
    rant='why did you skip the tests',
    failures=('skipped the tests',),
    root_cause='optimised for speed',
    corrective_action='run the gate before reporting',
    barked_back=False,
)
CLOSING = Closing(shipped='Retry queue drains in under a second')
SCOUT_REPORT_TEXT = 'the retry loop sleeps between drain batches'
SIMILAR_TO_EVERY_TEXT = 'queue floor drain sleeps optimised speed retry'
ONE_READ_OF_EACH_TOOL: tuple[ToolCall, ...] = (
    ('ticket', {'action': 'show', 'slug': SLUG}),
    ('task', {'action': 'show', 'slug': SLUG}),
    ('contract', {'action': 'status', 'slug': SLUG}),
    ('review', {'action': 'list'}),
    ('snapshot', {'slug': SLUG}),
    ('close', {'action': 'check', 'slug': SLUG}),
    ('investigation', {'action': 'list'}),
    ('crashout', {'action': 'stats'}),
    ('similarity', {'action': 'search', 'query': SIMILAR_TO_EVERY_TEXT}),
)


def passing_receipt() -> Receipt:
    return Receipt(
        id=COMMAND.id,
        argv=COMMAND.argv,
        outcome=Outcome.PASSED,
        exit=0,
        duration_ms=0,
        stdout_tail='',
        stderr_tail='',
        digest='d' * 64,
        head=HEAD,
        phase=Phase.TASK,
        at=now(),
    )


def transition_to(after: Status) -> Transition:
    before = Status.PENDING if after is Status.IN_PROGRESS else Status.IN_PROGRESS
    return Transition(task_id=TASK, before=before, after=after, reasons=[], head=HEAD, at=now())


def tickets_read(database: Database) -> int:
    with ticket_store(database).transaction() as repository:
        return int(repository.ticket(TICKET) is not None)


def tasks_read(database: Database) -> int:
    with task_store(database).transaction() as repository:
        return len(repository.tasks(TICKET))


def attempts_read(database: Database) -> int:
    with task_store(database).transaction() as repository:
        return len(repository.attempts_by_worker(TICKET))


def failed_fixes_read(database: Database) -> int:
    with task_store(database).transaction() as repository:
        return len(repository.failed_fixes(TICKET, TASK))


def transitions_read(database: Database) -> int:
    with task_store(database).transaction() as repository:
        return len(repository.latest_transitions_into(TICKET, tuple(Status), limit=2))


def commands_read(database: Database) -> int:
    with contract_store(database).transaction() as repository:
        return len(repository.commands(TICKET))


def receipts_read(database: Database) -> int:
    with contract_store(database).transaction() as repository:
        return len(repository.latest_receipts(TICKET))


def runs_read(database: Database) -> int:
    with review_store(database).transaction() as repository:
        return len(repository.latest_runs().rows)


def findings_read(database: Database) -> int:
    with review_store(database).transaction() as repository:
        return len(repository.findings(RUN))


def dispositions_read(database: Database) -> int:
    with review_store(database).transaction() as repository:
        return len(repository.decisions.dispositions(RUN))


def outcomes_read(database: Database) -> int:
    with review_store(database).transaction() as repository:
        return len(repository.decisions.outcomes(RUN))


def closings_read(database: Database) -> int:
    with database.transaction() as session:
        return int(session.get(ClosingRow, (database.repository_key.root, SLUG)) is not None)


def ledger_entries_read(database: Database) -> int:
    with investigation_store(database).transaction() as repository:
        return len(repository.entries(LEDGER))


def crashouts_read(database: Database) -> int:
    with crashout_store(database).transaction() as repository:
        return len(repository.latest_crashouts().rows)


def similar_rows_read(database: Database) -> int:
    with similarity_store(database).transaction() as repository:
        return len(repository.search(SIMILAR_TO_EVERY_TEXT, kind=None))


def scout_reports_read(database: Database) -> int:
    with similarity_store(database).transaction() as repository:
        return len(repository.search(SIMILAR_TO_EVERY_TEXT, kind=SimilarityKind.SCOUT_REPORT))


def answers_of(server: StateServer) -> list[str]:
    return [text_of(result) for result in server.call(*ONE_READ_OF_EACH_TOOL)]


def keys_stored(database: Database, row_type: type[Base]) -> Counter[str]:
    table = Base.metadata.tables[row_type.__tablename__]
    with database.transaction() as session:
        return Counter(session.scalars(sql.select(table.c.repository_key)))


READS = (
    pytest.param(TicketRow, tickets_read, id='tickets'),
    pytest.param(TaskRow, tasks_read, id='tasks'),
    pytest.param(AttemptRow, attempts_read, id='task-attempts'),
    pytest.param(FailedFixRow, failed_fixes_read, id='task-failed-fixes'),
    pytest.param(TransitionRow, transitions_read, id='task-transitions'),
    pytest.param(CommandRow, commands_read, id='contract-commands'),
    pytest.param(ReceiptRow, receipts_read, id='contract-receipts'),
    pytest.param(ReviewRunRow, runs_read, id='review-runs'),
    pytest.param(ReviewFindingRow, findings_read, id='review-findings'),
    pytest.param(ReviewDispositionRow, dispositions_read, id='review-dispositions'),
    pytest.param(ReviewOutcomeRow, outcomes_read, id='review-outcomes'),
    pytest.param(ClosingRow, closings_read, id='closings'),
    pytest.param(LedgerEntryRow, ledger_entries_read, id='ledger-entries'),
    pytest.param(CrashoutRow, crashouts_read, id='crashouts'),
    pytest.param(SimilarityRow, similar_rows_read, id='similarity'),
    pytest.param(ScoutReportRow, scout_reports_read, id='scout-reports'),
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Clone:
    tickets: TicketService
    contracts: ContractService
    reviews: ReviewService
    closings: CloseService
    investigations: InvestigationService
    crashouts: CrashoutService
    similarity: SimilarityService

    @property
    def database(self) -> Database:
        return self.closings.database

    def stage_the_ticket(self) -> None:
        self.tickets.write(TICKET, ANSWERS)
        self.tickets.validate(TICKET)

    def verify_the_task(self) -> None:
        with task_store(self.database).transaction() as repository:
            repository.tickets.mark_in_progress(TICKET)
            attempt = Attempt(worker=Implementer.ENGINEER, mode=None, owned=['queue.py'])
            repository.record_start(TICKET, transition_to(Status.IN_PROGRESS), attempt)
            repository.record_failed_fix(TICKET, TASK, 'the drain loop sleeps', at=now())
        with task_store(self.database).transaction() as repository:
            repository.record_mark(TICKET, transition_to(Status.VERIFIED))

    def settle_a_review(self) -> None:
        self.reviews.start(REVIEW, started=STARTED)
        self.reviews.add_findings(RUN, [FINDING])
        self.reviews.dispose(RUN, FIX_IT)
        self.reviews.resolve(RUN, FIXED)

    def store_a_scout_report(self) -> None:
        report = SpooledReport(
            repository_key=self.database.repository_key,
            scout=Scout.CODE_SCOUT,
            target='the drain loop',
            report=SCOUT_REPORT_TEXT,
        )
        with similarity_store(self.database).transaction() as repository:
            repository.add_scout_report(report)

    def write_every_table(self) -> None:
        self.stage_the_ticket()
        self.contracts.approve(TICKET, [COMMAND])
        with contract_store(self.database).transaction() as repository:
            repository.record(TICKET, [passing_receipt()])
        self.verify_the_task()
        self.settle_a_review()
        self.investigations.start(LEDGER_TARGET, started=STARTED)
        self.investigations.add(LEDGER, 1, [LEDGER_DECISION])
        self.crashouts.add(CRASHOUT)
        self.store_a_scout_report()
        self.closings.close(TICKET, CLOSING)

    def ticket_status(self) -> str:
        with ticket_store(self.database).transaction() as repository:
            return repository.staged_ticket(TICKET).status


@dataclass(slots=True, kw_only=True, frozen=True)
class Clones:
    first: Clone
    second: Clone


@dataclass(slots=True, kw_only=True, frozen=True)
class Answers:
    to_an_empty_database: list[str]
    to_the_other_repository: list[str]
    to_the_one_that_wrote: list[str]


def clone_of(state: OpenState) -> Clone:
    workspace, database = state.workspace, state.database
    return Clone(
        tickets=TicketService(workspace=workspace, store=ticket_store(database), git=workspace.git),
        contracts=ContractService(
            workspace=workspace,
            store=contract_store(database),
            git=workspace.git,
            processes=process_runner(),
        ),
        reviews=ReviewService(workspace=workspace, store=review_store(database), git=workspace.git),
        closings=CloseService(workspace=workspace, database=database),
        investigations=InvestigationService(store=investigation_store(database), git=workspace.git),
        crashouts=CrashoutService(store=crashout_store(database)),
        similarity=SimilarityService(
            store=similarity_store(database),
            spool=state.data_directory.joinpath(SPOOL_DIRECTORY),
            repository_key=database.repository_key,
        ),
    )


def checkout_of(origin: str, directory: Path, git: GitRunner) -> Path:
    directory.mkdir()
    git(directory, 'init', '--quiet')
    git(directory, 'remote', 'add', 'origin', origin)
    return directory


@pytest.fixture
def first_checkout(tmp_path: Path, git: GitRunner) -> Path:
    return checkout_of(FIRST_ORIGIN, tmp_path.joinpath('widgets'), git)


@pytest.fixture
def second_checkout(tmp_path: Path, git: GitRunner) -> Path:
    return checkout_of(SECOND_ORIGIN, tmp_path.joinpath('gadgets'), git)


@pytest.fixture
def first(first_checkout: Path, data_directory: Path) -> Generator[Clone]:
    with open_state(first_checkout, data_directory, ROW_TYPES) as state:
        yield clone_of(state)


@pytest.fixture
def second(second_checkout: Path, data_directory: Path) -> Generator[Clone]:
    with open_state(second_checkout, data_directory, ROW_TYPES) as state:
        yield clone_of(state)


@pytest.fixture
def only_the_first_written(first: Clone, second: Clone) -> Clones:
    first.write_every_table()
    return Clones(first=first, second=second)


@pytest.fixture
def both_written(only_the_first_written: Clones) -> Clones:
    only_the_first_written.second.write_every_table()
    return only_the_first_written


class TestTwoRepositoriesInOneDatabase:
    def test_every_table_has_a_read_through_its_repository(self) -> None:
        assert [read.values[0] for read in READS] == list(ROW_TYPES)

    @pytest.mark.usefixtures('both_written')
    def test_both_repositories_keep_their_rows_in_the_one_file(self, data_directory: Path) -> None:
        assert set(tree(data_directory)) == FILES_OF_AN_OPEN_DATABASE

    @pytest.mark.parametrize(('row_type', 'rows_read'), READS)
    def test_a_read_under_one_key_finds_no_row_written_under_another(
        self, row_type: type[Base], rows_read: RowsRead, only_the_first_written: Clones
    ) -> None:
        written, other = only_the_first_written.first, only_the_first_written.second

        assert set(keys_stored(other.database, row_type)) == {FIRST_KEY}
        assert rows_read(written.database) > 0
        assert rows_read(other.database) == 0

    @pytest.mark.parametrize(('row_type', 'rows_read'), READS)
    def test_the_same_ids_written_under_two_keys_coexist(
        self, row_type: type[Base], rows_read: RowsRead, both_written: Clones
    ) -> None:
        stored = keys_stored(both_written.first.database, row_type)

        assert set(stored) == {FIRST_KEY, SECOND_KEY}
        assert stored[FIRST_KEY] == stored[SECOND_KEY]
        assert rows_read(both_written.first.database) == rows_read(both_written.second.database)
        assert rows_read(both_written.second.database) > 0


class TestTheToolsOfAnotherRepository:
    @pytest.fixture
    def answers(
        self, first: Clone, first_checkout: Path, second_checkout: Path, data_directory: Path
    ) -> Answers:
        other = StateServer(root=second_checkout, data_directory=data_directory)
        to_an_empty_database = answers_of(other)
        first.write_every_table()
        writer = StateServer(root=first_checkout, data_directory=data_directory)
        return Answers(
            to_an_empty_database=to_an_empty_database,
            to_the_other_repository=answers_of(other),
            to_the_one_that_wrote=answers_of(writer),
        )

    def test_one_read_of_each_tool_answers_as_it_does_an_empty_database(
        self, answers: Answers
    ) -> None:
        assert answers.to_the_other_repository == answers.to_an_empty_database

    def test_the_same_reads_answer_the_repository_that_wrote_with_what_it_wrote(
        self, answers: Answers
    ) -> None:
        told_and_empty = zip(
            answers.to_the_one_that_wrote, answers.to_an_empty_database, strict=True
        )

        assert [told for told, empty in told_and_empty if told == empty] == []


class TestAChangeUnderOneKey:
    @pytest.fixture
    def closed_in_the_first_and_staged_in_the_second(
        self, only_the_first_written: Clones
    ) -> Clones:
        only_the_first_written.second.stage_the_ticket()
        return only_the_first_written

    @pytest.fixture
    def number_of_the_second_repositorys_first_crashout(
        self, only_the_first_written: Clones
    ) -> str:
        return only_the_first_written.second.crashouts.add(CRASHOUT).text

    def test_a_ticket_closed_under_one_key_is_as_it_was_under_the_other(
        self, closed_in_the_first_and_staged_in_the_second: Clones
    ) -> None:
        clones = closed_in_the_first_and_staged_in_the_second

        assert (clones.first.ticket_status(), clones.second.ticket_status()) == ('closed', 'staged')

    def test_each_repository_numbers_its_own_crashouts_from_one(
        self, number_of_the_second_repositorys_first_crashout: str
    ) -> None:
        assert number_of_the_second_repositorys_first_crashout == 'journaled crashout #1\n'
