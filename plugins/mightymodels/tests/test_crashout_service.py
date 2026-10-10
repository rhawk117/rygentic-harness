"""The crashout service: an append-only journal in the database, and the texts it reports."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import STATE_DIRECTORY
from mightymodels_plugin.tools.crashout.repository import crashout_transaction
from mightymodels_plugin.tools.crashout.schema import (
    CrashoutEntry,
    JournaledCrashout,
    Severity,
    Verdict,
)
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.tests.support import (
    FILES_OF_AN_OPEN_DATABASE,
    ActivityKind,
    DatabaseActivity,
    StateServer,
    stored_bytes,
    text_of,
    tree,
)
from pydantic import ValidationError

FAKE_TOKEN = 'ghp_' + 'a' * 36
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
ENTRY = SKIPPED_TESTS.model_dump(mode='json')


@pytest.fixture
def journal_of_one(crashout_service: CrashoutService) -> CrashoutService:
    crashout_service.add(SKIPPED_TESTS)
    return crashout_service


@pytest.fixture
def journal_of_three(journal_of_one: CrashoutService) -> CrashoutService:
    journal_of_one.add(SKIPPED_TESTS_AGAIN)
    journal_of_one.add(WRONG_BRANCH)
    return journal_of_one


def last_entry(crashouts: CrashoutService) -> JournaledCrashout:
    return JournaledCrashout.model_validate(crashouts.last().entry)


def journal_times(crashouts: CrashoutService) -> list[str]:
    with crashout_transaction(crashouts.database) as repository:
        return [row.at for row in repository.latest_rows().rows]


class TestAdd:
    LEAKING = CrashoutEntry(
        branch=f'fix/{FAKE_TOKEN}',
        severity=Severity.CRASHOUT,
        verdict=Verdict.UNREASONABLE,
        rant='you pasted password=hunter2 into the log',
        failures=('logged token=abc123',),
        root_cause='copied secret=s3cr3tvalue from the environment',
        corrective_action=f'never echo {FAKE_TOKEN}',
        barked_back=True,
    )
    SECRETS = (FAKE_TOKEN, 'hunter2', 'abc123', 's3cr3tvalue')

    @pytest.fixture
    def journal_of_a_leaking_crashout(self, crashout_service: CrashoutService) -> CrashoutService:
        crashout_service.add(self.LEAKING)
        return crashout_service

    def test_add_answers_with_the_number_of_the_crashout(
        self, journal_of_one: CrashoutService
    ) -> None:
        second = journal_of_one.add(SKIPPED_TESTS_AGAIN)
        third = journal_of_one.add(WRONG_BRANCH)

        assert (second.text, third.text) == ('journaled crashout #2\n', 'journaled crashout #3\n')
        assert (second.entry, third.entry) == (None, None)

    def test_the_first_crashout_is_number_one(self, crashout_service: CrashoutService) -> None:
        assert crashout_service.add(SKIPPED_TESTS).text == 'journaled crashout #1\n'

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

    def test_every_free_text_field_is_redacted_before_it_is_stored(
        self, journal_of_a_leaking_crashout: CrashoutService
    ) -> None:
        journaled = last_entry(journal_of_a_leaking_crashout)
        stored = stored_bytes(journal_of_a_leaking_crashout.database)

        assert journaled.branch == 'fix/[REDACTED:github-token]'
        assert journaled.corrective_action == 'never echo [REDACTED:github-token]'
        assert [secret for secret in self.SECRETS if secret in journaled.model_dump_json()] == []
        assert [secret for secret in self.SECRETS if secret.encode() in stored] == []

    def test_a_call_writes_nothing_outside_the_database(
        self, journal_of_three: CrashoutService, repository: Path, data_directory: Path
    ) -> None:
        journal_of_three.stats()
        journal_of_three.last()

        written = {name for name in tree(repository) if not name.startswith('.git/')}
        assert written == set()
        assert set(tree(data_directory)) == FILES_OF_AN_OPEN_DATABASE
        assert not repository.joinpath('.gitignore').exists()
        assert not repository.joinpath(STATE_DIRECTORY, 'crashouts.yml').exists()


class TestStats:
    def test_stats_of_an_empty_journal_is_serenity(self, crashout_service: CrashoutService) -> None:
        view = crashout_service.stats()

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
    def test_last_of_an_empty_journal_says_so(self, crashout_service: CrashoutService) -> None:
        view = crashout_service.last()

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


class TestRefusals:
    @pytest.mark.parametrize(
        'entry',
        [
            pytest.param({**ENTRY, 'at': '2026-01-01T00:00:00Z'}, id='its-own-timestamp'),
            pytest.param({**ENTRY, 'mood': 'bad'}, id='unknown-key'),
            pytest.param({**ENTRY, 'severity': 'furious'}, id='unknown-severity'),
            pytest.param({**ENTRY, 'verdict': 'guilty'}, id='unknown-verdict'),
            pytest.param({**ENTRY, 'failures': []}, id='no-failures'),
            pytest.param({**ENTRY, 'failures': ['skipped', '  ']}, id='blank-failure'),
            pytest.param({**ENTRY, 'rant': ' \n '}, id='blank-rant'),
            pytest.param({**ENTRY, 'root_cause': '  '}, id='blank-root-cause'),
            pytest.param({**ENTRY, 'corrective_action': ''}, id='blank-corrective-action'),
            pytest.param({**ENTRY, 'barked_back': 'loudly'}, id='barked-back-not-a-bool'),
            pytest.param({**ENTRY, 'ticket': '../outside'}, id='path-shaped-ticket'),
            pytest.param(
                {key: value for key, value in ENTRY.items() if key != 'rant'}, id='no-rant'
            ),
        ],
    )
    def test_an_entry_outside_the_schema_is_refused_and_nothing_is_stored(
        self,
        entry: dict[str, object],
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (refused,) = connected_server.call(('crashout', {'action': 'add', 'entry': entry}))

        with pytest.raises(ValidationError):
            CrashoutEntry.model_validate(entry)
        assert refused.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert connected_server.files_on_disk() == tree_after_the_connect

    def test_add_without_an_entry_says_what_it_needs(
        self, connected_server: StateServer, database_activity: DatabaseActivity
    ) -> None:
        (refused,) = connected_server.call(('crashout', {'action': 'add'}))

        assert refused.is_error
        assert 'add needs an entry holding the crashout' in text_of(refused)
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()

    def test_an_unknown_action_is_refused(self, connected_server: StateServer) -> None:
        (refused,) = connected_server.call(('crashout', {'action': 'prune'}))

        assert refused.is_error


class TestTheTool:
    def test_a_crashout_is_journaled_read_back_and_counted_through_the_tool(
        self, state_server: StateServer
    ) -> None:
        added, last, stats = state_server.call(
            ('crashout', {'action': 'add', 'entry': ENTRY}),
            ('crashout', {'action': 'last'}),
            ('crashout', {'action': 'stats'}),
        )

        assert added.structured_content == {'text': 'journaled crashout #1\n', 'entry': None}
        assert last.structured_content['entry'] == {
            **ENTRY,
            'at': last.structured_content['entry']['at'],
            'rant': 'WHY did you skip the tests\n  AGAIN',
            'root_cause': 'optimised for speed',
        }
        assert stats.structured_content['text'].startswith('entries: 1\nseverity: heated=1\n')
