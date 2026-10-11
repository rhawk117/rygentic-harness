from collections.abc import Callable
from dataclasses import dataclass

import pytest
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import Database, ReadLimit, WriteLimitError
from mightymodels_plugin.core.process import process_runner
from mightymodels_plugin.core.workspace import Workspace, git_at
from mightymodels_plugin.tools.contract.repository import COMMANDS, contract_store
from mightymodels_plugin.tools.contract.schema import ContractCommand
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.investigation.repository import ENTRIES
from mightymodels_plugin.tools.investigation.schema import EntryKind, LedgerEntry, Source
from mightymodels_plugin.tools.review.repository import FINDINGS, review_store
from mightymodels_plugin.tools.review.schema import (
    Decision,
    FindingInput,
    ReportedSeverity,
    Result,
    Shape,
)
from mightymodels_plugin.tools.review.store import DecidedFinding, ResolvedFinding
from mightymodels_plugin.tools.review.tables import ReviewDispositionRow, ReviewOutcomeRow
from mightymodels_plugin.tools.task.repository import TASKS, task_store
from mightymodels_plugin.tools.task.schema import Implementer, TaskStart
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.tests.bounded_reads import (
    LEDGER,
    RUN,
    SLUG,
    TICKET,
    SizedRead,
    commands,
    commands_of_the_ticket,
    decisions_on,
    dispositions,
    entries_of_the_ledger,
    finding_ids,
    findings_of_the_run,
    investigation_service,
    ledger_entries,
    outcomes,
    outcomes_of,
    review_service,
    store,
    tasks,
    tasks_of_the_ticket,
)


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
    ContractService(
        workspace=workspace,
        store=contract_store(database),
        git=git_at(workspace.root),
        processes=process_runner(),
    ).approve(TICKET, approved)


def start_tasks(workspace: Workspace, database: Database, numbers: range) -> None:
    service = TaskService(
        workspace=workspace, store=task_store(database), git=git_at(workspace.root)
    )
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
    review_service(workspace, database).add_findings(RUN, found)


def decide_findings(_workspace: Workspace, database: Database, numbers: range) -> None:
    decided = [
        DecidedFinding(
            finding_id=f'F{number}', decision=Decision.FIX, reason='', by='user', at=now()
        )
        for number in numbers
    ]
    with review_store(database).transaction() as repository:
        repository.decisions.record_dispositions(RUN, decided)


def resolve_findings(_workspace: Workspace, database: Database, numbers: range) -> None:
    with review_store(database).transaction() as repository:
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
    investigation_service(workspace, database).add(LEDGER, 1, entries)


def contract_status(workspace: Workspace, database: Database) -> str:
    return (
        ContractService(
            workspace=workspace,
            store=contract_store(database),
            git=git_at(workspace.root),
            processes=process_runner(),
        )
        .status(TICKET)
        .text
    )


def task_listing(workspace: Workspace, database: Database) -> str:
    return (
        TaskService(workspace=workspace, store=task_store(database), git=git_at(workspace.root))
        .show(TICKET)
        .text
    )


def review_report(workspace: Workspace, database: Database) -> str:
    return review_service(workspace, database).report(RUN, Shape.FULL).text


def rendered_ledger(workspace: Workspace, database: Database) -> str:
    return investigation_service(workspace, database).render(LEDGER).text


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
