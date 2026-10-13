"""The investigation service on a real repository and SQLite: the database file, and HEAD in git.

These tests read the bytes of the database file, or arrange a real repository to see where HEAD is
read from: packed refs, a linked worktree, a detached HEAD and a directory that is no repository.
"""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.tools.investigation.ledger import recorded_ledger
from mightymodels_plugin.tools.investigation.schema import (
    EntryKind,
    InvestigationStart,
    KnownsFilter,
    LedgerEntry,
    Source,
    TargetKind,
)
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.store import LedgerRecord
from mightymodels_plugin.tools.investigation.tests.support import investigation_service_at
from mightymodels_plugin.tools.tests.support import stored_bytes

FAKE_TOKEN = 'ghp_' + 'a' * 36
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
STARTED = datetime(2026, 9, 28, 12, tzinfo=UTC)
TARGET = InvestigationStart(target='Queue drains slowly', kind=TargetKind.BEHAVIOR)
EVERY_KIND = KnownsFilter()


def known(text: str, cite: str) -> LedgerEntry:
    return LedgerEntry(kind=EntryKind.KNOWN, text=text, cite=cite, source=Source.CODE_SCOUT)


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    investigations: InvestigationService
    runner: GitRunner
    root: Path

    def git(self, *arguments: str) -> str:
        return self.runner(self.root, *IDENTITY, *arguments).strip()

    def commit(self, message: str) -> str:
        self.git('commit', '--quiet', '--allow-empty', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def start(self, target: InvestigationStart = TARGET) -> Slug:
        return Slug(str(self.investigations.start(target, started=STARTED).investigation_id))

    def add(self, investigation: Slug, round_number: int, *entries: LedgerEntry) -> str:
        return self.investigations.add(investigation, round_number, entries).text

    def knowns(self, investigation: Slug, selection: KnownsFilter = EVERY_KIND) -> str:
        return self.investigations.knowns(investigation, selection).text

    def stored(self, investigation: Slug) -> tuple[LedgerRecord, ...]:
        with self.investigations.store.transaction() as repository:
            return recorded_ledger(repository, investigation).records


@pytest.fixture
def workspace(
    investigation_service: InvestigationService, git: GitRunner, repository: Path
) -> Workspace:
    return Workspace(investigations=investigation_service, runner=git, root=repository)


@pytest.fixture
def investigation(workspace: Workspace) -> Slug:
    return workspace.start()


@pytest.fixture
def investigation_with_a_known(workspace: Workspace, investigation: Slug) -> Slug:
    workspace.add(investigation, 1, known('a', 'a:1'))
    return investigation


@dataclass(frozen=True, slots=True, kw_only=True)
class Committed:
    workspace: Workspace
    head: str


@pytest.fixture
def committed(workspace: Workspace) -> Committed:
    return Committed(workspace=workspace, head=workspace.commit('base'))


class TestWhatReachesTheDatabaseFile:
    LEAKING_TARGET = InvestigationStart(
        target=f'Why does {FAKE_TOKEN} reach the log', kind=TargetKind.BEHAVIOR
    )
    LEAKING = known(f'CI uses {FAKE_TOKEN} and password=hunter2', 'ci.yml:3')

    def test_a_secret_in_the_target_reaches_neither_the_row_nor_the_id(
        self, workspace: Workspace, repository_database: Database
    ) -> None:
        investigation = workspace.start(self.LEAKING_TARGET)
        (target,) = workspace.stored(investigation)

        assert target.text == 'Why does [REDACTED:github-token] reach the log'
        assert investigation.root == '20260928-why-does-redacted-github-token-reach-the'
        assert FAKE_TOKEN.encode() not in stored_bytes(repository_database)

    def test_secrets_are_redacted_before_they_reach_disk(
        self, workspace: Workspace, investigation: Slug, repository_database: Database
    ) -> None:
        saved = workspace.add(investigation, 1, self.LEAKING)
        stored = stored_bytes(repository_database)

        assert '(2 redacted)' in saved
        assert FAKE_TOKEN.encode() not in stored
        assert b'hunter2' not in stored


class TestWhereHeadIsRead:
    @pytest.fixture
    def packed(self, committed: Committed) -> Committed:
        committed.workspace.git('pack-refs', '--all')
        return committed

    @pytest.fixture
    def detached(self, committed: Committed) -> Committed:
        committed.workspace.git('checkout', '--quiet', '--detach')
        return committed

    @pytest.fixture
    def in_a_worktree(
        self, committed: Committed, tmp_path: Path, data_directory: Path, git: GitRunner
    ) -> Generator[Committed]:
        linked = tmp_path.joinpath('feature')
        committed.workspace.git('worktree', 'add', '--quiet', str(linked), '-b', 'feature')
        with investigation_service_at(linked, data_directory) as investigations:
            yield Committed(
                workspace=Workspace(investigations=investigations, runner=git, root=linked),
                head=committed.head,
            )

    def test_head_resolves_through_packed_refs(self, packed: Committed) -> None:
        (target,) = packed.workspace.stored(packed.workspace.start())
        packed_refs = packed.workspace.root.joinpath('.git', 'packed-refs')

        assert target.head == packed.head
        assert packed.head in packed_refs.read_text(encoding='utf-8')

    def test_head_resolves_from_a_worktree(self, in_a_worktree: Committed) -> None:
        (target,) = in_a_worktree.workspace.stored(in_a_worktree.workspace.start())

        assert target.head == in_a_worktree.head
        assert in_a_worktree.workspace.root.joinpath('.git').is_file()

    def test_detached_head_is_the_sha_itself(self, detached: Committed) -> None:
        (target,) = detached.workspace.stored(detached.workspace.start())

        assert target.head == detached.head
        assert detached.workspace.git('rev-parse', '--abbrev-ref', 'HEAD') == 'HEAD'


class TestOutsideARepository:
    @pytest.fixture
    def repository(self, tmp_path: Path) -> Path:
        directory = tmp_path.joinpath('plain-directory')
        directory.mkdir()
        return directory

    def test_outside_a_repository_an_investigation_is_stored_and_every_entry_is_a_lead(
        self, workspace: Workspace, investigation_with_a_known: Slug
    ) -> None:
        table = workspace.knowns(investigation_with_a_known)

        assert [record.head for record in workspace.stored(investigation_with_a_known)] == [
            None,
            None,
        ]
        assert '| e2 | known | a | a:1 | code-scout | 1 | lead |' in table
        assert not workspace.root.joinpath('.git').exists()
