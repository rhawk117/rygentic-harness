from collections.abc import Callable, Iterable, Sized
from contextlib import suppress
from types import MappingProxyType

import sqlalchemy as sql

from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import Database, ReadLimitError
from mightymodels_plugin.core.declarative import Base
from mightymodels_plugin.core.routing import Depth, Scope
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import Workspace, git_at
from mightymodels_plugin.tools.contract.repository import contract_store
from mightymodels_plugin.tools.contract.tables import CommandRow
from mightymodels_plugin.tools.investigation.repository import TARGET_SEQ, investigation_store
from mightymodels_plugin.tools.investigation.schema import EntryKind, Source, TargetKind
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.store import LedgerRecord
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.review.repository import review_store
from mightymodels_plugin.tools.review.schema import (
    Decision,
    Emphasis,
    Persona,
    Result,
    ReviewRun,
    ReviewScope,
)
from mightymodels_plugin.tools.review.schema import Severity as FindingSeverity
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.review.tables import ReviewFindingRow
from mightymodels_plugin.tools.task.gates import STUCK
from mightymodels_plugin.tools.task.repository import task_store
from mightymodels_plugin.tools.task.schema import ArchitectMode, Status
from mightymodels_plugin.tools.task.tables import TaskRow
from mightymodels_plugin.tools.tests.support import (
    RowValues,
    SelectsSent,
    filled_row,
    selects_sent_to,
    table_of,
)
from mightymodels_plugin.tools.ticket.repository import ticket_store
from mightymodels_plugin.tools.ticket.tables import TicketRow

type Read = Callable[[Database], object]
type SizedRead = Callable[[Database], Sized]

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
TASK = 'T1'
RUN = RunId('20260928-120000')
LEDGER = Slug('20260928-queue')
OTHER_LEDGER = Slug('20260928-drain')
NEVER_STARTED = Slug('20260928-never-started')
MODES = frozenset(ArchitectMode)
SNAPSHOT_LIMIT = 3
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
        session.execute(sql.insert(table_of(row_type)), filled)


def commands(database: Database) -> Sized:
    with contract_store(database).transaction() as repository:
        return repository.commands(TICKET)


def latest_receipts(database: Database) -> dict[str, int]:
    with contract_store(database).transaction() as repository:
        latest = repository.latest_receipts(TICKET)
        return {command: receipt.duration_ms for command, receipt in latest.items()}


def tasks(database: Database) -> Sized:
    with task_store(database).transaction() as repository:
        return repository.tasks(TICKET)


def attempt_counts(database: Database) -> list[tuple[str, str, int]]:
    with task_store(database).transaction() as repository:
        counts = repository.attempts_by_worker(TICKET)
    return [
        (task, worker, count)
        for task, by_worker in counts.items()
        for worker, count in by_worker.items()
    ]


def attempts_in_modes(database: Database) -> int:
    with task_store(database).transaction() as repository:
        return repository.attempts_in_modes(TICKET, TASK, MODES)


def stuck_transitions(database: Database) -> list[str]:
    with task_store(database).transaction() as repository:
        latest = repository.latest_transitions_into(TICKET, STUCK, SNAPSHOT_LIMIT)
        return [str(transition.head) for transition in latest]


def finding_ids(database: Database) -> list[str]:
    with review_store(database).transaction() as repository:
        return [finding.id for finding in repository.findings(RUN)]


def dispositions(database: Database) -> Sized:
    with review_store(database).transaction() as repository:
        return repository.decisions.dispositions(RUN)


def outcomes(database: Database) -> Sized:
    with review_store(database).transaction() as repository:
        return repository.decisions.outcomes(RUN)


def ledger_entries(database: Database) -> Sized:
    with investigation_store(database).transaction() as repository:
        return repository.entries(LEDGER)


def unrecorded_investigations(database: Database) -> list[Slug]:
    with ticket_store(database).transaction() as repository:
        return repository.unrecorded_investigations([LEDGER, OTHER_LEDGER, NEVER_STARTED])


def selects_of(read: Read, database: Database) -> SelectsSent:
    with selects_sent_to(database) as selects, suppress(ReadLimitError):
        read(database)
    return selects


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


def review_service(workspace: Workspace, database: Database) -> ReviewService:
    return ReviewService(
        workspace=workspace, store=review_store(database), git=git_at(workspace.root)
    )


def investigation_service(workspace: Workspace, database: Database) -> InvestigationService:
    return InvestigationService(store=investigation_store(database), git=git_at(workspace.root))


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


def tasks_of_the_ticket(database: Database, count: int) -> None:
    store(database, TicketRow, [{'slug': SLUG, 'scope': Scope.MED, 'models': {}}])
    started = [
        {'slug': SLUG, 'task_id': f'T{number}', 'status': Status.VERIFIED}
        for number in range(count)
    ]
    store(database, TaskRow, started)


def findings_of_the_run(database: Database, count: int) -> None:
    with review_store(database).transaction() as repository:
        repository.record_run(started(RUN))
    found = [{**A_FINDING, 'finding_id': f'F{number}'} for number in range(count)]
    store(database, ReviewFindingRow, found)


def entries_of_the_ledger(database: Database, count: int) -> None:
    entries = [{**AN_ENTRY, 'seq': number} for number in range(1, count + 1)]
    store(database, LedgerEntryRow, entries)
