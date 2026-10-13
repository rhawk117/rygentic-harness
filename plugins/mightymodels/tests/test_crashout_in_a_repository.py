"""The crashout service on a real repository and SQLite: what reaches the file and the tree.

These tests read the bytes of the database file and the files on disk, which a store kept in
memory has none of.
"""

from pathlib import Path

import pytest
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import STATE_DIRECTORY
from mightymodels_plugin.tools.crashout.schema import (
    CrashoutEntry,
    JournaledCrashout,
    Severity,
    Verdict,
)
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.tests.support import FILES_OF_AN_OPEN_DATABASE, stored_bytes, tree

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


@pytest.fixture
def journal_of_three(crashout_service: CrashoutService) -> CrashoutService:
    crashout_service.add(SKIPPED_TESTS)
    crashout_service.add(SKIPPED_TESTS_AGAIN)
    crashout_service.add(WRONG_BRANCH)
    return crashout_service


def last_entry(crashouts: CrashoutService) -> JournaledCrashout:
    return JournaledCrashout.model_validate(crashouts.last().entry)


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

    def test_every_free_text_field_is_redacted_before_it_is_stored(
        self, journal_of_a_leaking_crashout: CrashoutService, repository_database: Database
    ) -> None:
        journaled = last_entry(journal_of_a_leaking_crashout)
        stored = stored_bytes(repository_database)

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
