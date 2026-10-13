"""Every read of the state database is bounded: what its statements say and what they fetch.

A write that adds to what a whole read returns is held to that read's limit, so no write the
plugin accepts makes a ticket, a run or an investigation unreadable.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from mightymodels_plugin.core.database import Database, Latest, ReadLimit
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.crashout import service as crashouts
from mightymodels_plugin.tools.crashout.repository import JOURNAL_WINDOW, crashout_store
from mightymodels_plugin.tools.crashout.schema import JournaledCrashout, Severity, Verdict
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.investigation import service as investigations
from mightymodels_plugin.tools.investigation.repository import (
    INVESTIGATIONS_LISTED,
    investigation_store,
)
from mightymodels_plugin.tools.review import service as reviews
from mightymodels_plugin.tools.review.repository import RUNS_LISTED, review_store
from mightymodels_plugin.tools.task.repository import task_store
from mightymodels_plugin.tools.tests.bounded_reads import (
    LEDGER,
    RUN,
    TARGET,
    TASK,
    TICKET,
    Read,
    attempt_counts,
    attempts_in_modes,
    commands,
    dispositions,
    finding_ids,
    investigation_service,
    latest_receipts,
    ledger_entries,
    outcomes,
    review_service,
    selects_of,
    started,
    stuck_transitions,
    tasks,
    unrecorded_investigations,
)
from mightymodels_plugin.tools.ticket.repository import ticket_store

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


def ticket_row(database: Database) -> None:
    with ticket_store(database).transaction() as repository:
        repository.ticket(TICKET)


def task_row(database: Database) -> None:
    with task_store(database).transaction() as repository:
        repository.task(TICKET, TASK)


def run_row(database: Database) -> None:
    with review_store(database).transaction() as repository:
        repository.run(RUN)


def latest_runs(database: Database) -> Latest[str]:
    with review_store(database).transaction() as repository:
        latest = repository.latest_runs()
        return Latest(
            rows=tuple(run.run_id.root for run in latest.rows), older_left_out=latest.older_left_out
        )


def latest_run_of_the_ticket(database: Database) -> None:
    with review_store(database).transaction() as repository:
        repository.latest_run(TICKET)


def ledger_target(database: Database) -> None:
    with investigation_store(database).transaction() as repository:
        repository.has_entries(LEDGER)


def latest_investigations(database: Database) -> Latest[str]:
    with investigation_store(database).transaction() as repository:
        latest = repository.latest_rounds()
    return Latest(
        rows=tuple(investigation for investigation, _ in latest.rows),
        older_left_out=latest.older_left_out,
    )


def latest_crashouts(database: Database) -> Latest[str]:
    with crashout_store(database).transaction() as repository:
        latest = repository.latest_crashouts()
        return Latest(
            rows=tuple(crashout.at for crashout in latest.rows),
            older_left_out=latest.older_left_out,
        )


def latest_crashout(database: Database) -> None:
    with crashout_store(database).transaction() as repository:
        repository.latest_crashout()


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
    with crashout_store(database).transaction() as repository:
        for at in times:
            repository.journal(JOURNALED.model_copy(update={'at': at}))
    return times


def start_runs(database: Database, count: int) -> list[str]:
    runs = [RunId(f'20260928-{number:06d}') for number in range(count)]
    with review_store(database).transaction() as repository:
        for run in runs:
            repository.record_run(started(run))
    return [run.root for run in runs]


def start_investigations(database: Database, count: int) -> list[str]:
    started = [Slug(f'20260928-queue-{number:04d}') for number in range(count)]
    with investigation_store(database).transaction() as repository:
        for investigation in started:
            repository.append(investigation, [TARGET])
    return [investigation.root for investigation in started]


def crashout_stats(_workspace: Workspace, database: Database) -> str:
    return CrashoutService(store=crashout_store(database)).stats().text


def review_listing(workspace: Workspace, database: Database) -> str:
    return review_service(workspace, database).listing().text


def investigation_listing(workspace: Workspace, database: Database) -> str:
    return investigation_service(workspace, database).listing().text


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
