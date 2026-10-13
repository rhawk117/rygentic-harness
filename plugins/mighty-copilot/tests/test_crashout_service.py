"""The crashout service: an append-only journal, and the texts it reports.

The service runs on the crashout store kept in memory. What reaches the database file and the tree
is in test_crashout_in_a_repository.py, and the tool is in test_crashout_tool.py.
"""

from datetime import UTC, datetime, timedelta

import pytest
from mightymodels.core.slug import Slug
from mightymodels.tools.crashout.schema import (
    CrashoutEntry,
    JournaledCrashout,
    Severity,
    Verdict,
)
from mightymodels.tools.crashout.service import CrashoutService

SKIPPED_TESTS = CrashoutEntry(
    ticket=Slug('retry-queue'),
    branch='fix/retry-queue',
    severity=Severity.HEATED,
    verdict=Verdict.DESERVED,
    rant='WHY did you skip the tests\r\n  AGAIN   \r\r\n',
    failures=('skipped the tests', 'claimed done'),
    root_cause='  optimised for speed  ',
    corrective_action='run the gate  before reporting',
    barked_back=False,
)
SKIPPED_TESTS_AGAIN = CrashoutEntry(
    severity=Severity.FULL_MELTDOWN,
    verdict=Verdict.DESERVED,
    rant='\n\nnot again\n',
    failures=('skipped the tests again',),
    root_cause='the gate was not run',
    corrective_action='run the gate before reporting',
    barked_back=True,
)
WRONG_BRANCH = CrashoutEntry(
    severity=Severity.HEATED,
    verdict=Verdict.SPLIT,
    rant='that was my branch',
    failures=('committed to main',),
    root_cause='the branch was never checked',
    corrective_action='check the branch first',
    barked_back=False,
)


@pytest.fixture
def journal_of_one(in_memory_crashout_service: CrashoutService) -> CrashoutService:
    in_memory_crashout_service.add(SKIPPED_TESTS)
    return in_memory_crashout_service


@pytest.fixture
def journal_of_three(journal_of_one: CrashoutService) -> CrashoutService:
    journal_of_one.add(SKIPPED_TESTS_AGAIN)
    journal_of_one.add(WRONG_BRANCH)
    return journal_of_one


def last_entry(crashouts: CrashoutService) -> JournaledCrashout:
    return JournaledCrashout.model_validate(crashouts.last().entry)


def journal_times(crashouts: CrashoutService) -> list[str]:
    with crashouts.store.transaction() as repository:
        return [crashout.at for crashout in repository.latest_crashouts().rows]


class TestAdd:
    def test_add_answers_with_the_number_of_the_crashout(
        self, journal_of_one: CrashoutService
    ) -> None:
        second = journal_of_one.add(SKIPPED_TESTS_AGAIN)
        third = journal_of_one.add(WRONG_BRANCH)

        assert (second.text, third.text) == ('journaled crashout #2\n', 'journaled crashout #3\n')
        assert (second.entry, third.entry) == (None, None)

    def test_the_first_crashout_is_number_one(
        self, in_memory_crashout_service: CrashoutService
    ) -> None:
        assert in_memory_crashout_service.add(SKIPPED_TESTS).text == 'journaled crashout #1\n'

    def test_a_crashout_is_stored_with_the_time_the_server_received_it(
        self, journal_of_one: CrashoutService
    ) -> None:
        journaled = last_entry(journal_of_one)
        received = datetime.fromisoformat(journaled.at)

        assert received.utcoffset() == timedelta(0)
        assert datetime.now(tz=UTC) - received < timedelta(minutes=1)
        assert (journaled.ticket, journaled.branch) == ('retry-queue', 'fix/retry-queue')
        assert (journaled.severity, journaled.verdict) == (Severity.HEATED, Verdict.DESERVED)
        assert (journaled.failures, journaled.barked_back) == (
            ('skipped the tests', 'claimed done'),
            False,
        )

    def test_the_rant_keeps_its_words_and_loses_its_line_endings(
        self, journal_of_one: CrashoutService
    ) -> None:
        assert last_entry(journal_of_one).rant == 'WHY did you skip the tests\n  AGAIN'

    def test_the_root_cause_and_the_corrective_action_are_stripped(
        self, journal_of_one: CrashoutService
    ) -> None:
        journaled = last_entry(journal_of_one)

        assert journaled.root_cause == 'optimised for speed'
        assert journaled.corrective_action == 'run the gate  before reporting'


class TestStats:
    def test_stats_of_an_empty_journal_is_serenity(
        self, in_memory_crashout_service: CrashoutService
    ) -> None:
        view = in_memory_crashout_service.stats()

        assert (view.text, view.entry) == ('no crashouts recorded yet. serenity.\n', None)

    def test_stats_reports_recurring_patterns(self, journal_of_three: CrashoutService) -> None:
        first, second, third = journal_times(journal_of_three)

        assert journal_of_three.stats().text.splitlines() == [
            'entries: 3',
            'severity: heated=2 full-meltdown=1',
            'verdicts: deserved=2 split=1',
            'barked_back: 1/3',
            f'first: {first}  last: {third}',
            '',
            'failures:',
            f'  [{first[:10]} | deserved | heated] skipped the tests',
            f'  [{first[:10]} | deserved | heated] claimed done',
            f'  [{second[:10]} | deserved | full-meltdown] skipped the tests again',
            f'  [{third[:10]} | split | heated] committed to main',
            '',
            'standing corrective actions:',
            '  - run the gate before reporting',
            '  - check the branch first',
        ]


class TestLast:
    def test_last_of_an_empty_journal_says_so(
        self, in_memory_crashout_service: CrashoutService
    ) -> None:
        view = in_memory_crashout_service.last()

        assert (view.text, view.entry) == ('no crashouts recorded yet.\n', None)

    def test_last_returns_the_newest_crashout_as_typed_fields(
        self, journal_of_three: CrashoutService
    ) -> None:
        journaled = last_entry(journal_of_three)

        assert (journaled.severity, journaled.verdict) == (Severity.HEATED, Verdict.SPLIT)
        assert (journaled.ticket, journaled.branch) == (None, None)
        assert journaled.failures == ('committed to main',)

    def test_last_reads_as_text_in_the_journal_key_order(
        self, journal_of_one: CrashoutService
    ) -> None:
        view = journal_of_one.last()

        assert view.text.splitlines() == [
            f'at: {last_entry(journal_of_one).at}',
            'ticket: retry-queue',
            'branch: fix/retry-queue',
            'severity: heated',
            'verdict: deserved',
            'rant:',
            '  WHY did you skip the tests',
            '    AGAIN',
            'failures:',
            '  - skipped the tests',
            '  - claimed done',
            'root_cause: optimised for speed',
            'corrective_action: run the gate  before reporting',
            'barked_back: false',
        ]

    def test_an_absent_ticket_and_branch_read_as_none(
        self, journal_of_three: CrashoutService
    ) -> None:
        lines = journal_of_three.last().text.splitlines()

        assert lines[1:3] == ['ticket: none', 'branch: none']
        assert lines[-1] == 'barked_back: false'
