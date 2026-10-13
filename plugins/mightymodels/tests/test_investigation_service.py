"""The investigation service on the store and the git history kept in memory.

What reaches the database file, and where HEAD is read from in a real repository, is in
test_investigation_in_a_repository.py. The tool is in test_investigation_tool.py.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.tools.investigation.errors import (
    RoundRegressionError,
    UnknownInvestigationError,
    UnknownSupersededError,
)
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

FAKE_TOKEN = 'ghp_' + 'a' * 36
STARTED = datetime(2026, 9, 28, 12, tzinfo=UTC)
TARGET = InvestigationStart(target='Queue drains slowly', kind=TargetKind.BEHAVIOR)
EVERY_KIND = KnownsFilter()


def known(text: str, cite: str) -> LedgerEntry:
    return LedgerEntry(kind=EntryKind.KNOWN, text=text, cite=cite, source=Source.CODE_SCOUT)


DRAIN_LOOP = known('drain loop sleeps 10s', 'src/queue.py:41')
QUESTION = LedgerEntry(kind=EntryKind.OPEN, text='is backoff 30s?', source=Source.WEB_SCOUT)


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    investigations: InvestigationService
    git: InMemoryGit

    def commit(self) -> str:
        return self.git.commit()

    def start(self, target: InvestigationStart = TARGET) -> Slug:
        return Slug(str(self.investigations.start(target, started=STARTED).investigation_id))

    def add(self, investigation: Slug, round_number: int, *entries: LedgerEntry) -> str:
        return self.investigations.add(investigation, round_number, entries).text

    def render(self, investigation: Slug) -> str:
        return self.investigations.render(investigation).text

    def knowns(self, investigation: Slug, selection: KnownsFilter = EVERY_KIND) -> str:
        return self.investigations.knowns(investigation, selection).text

    def listing(self) -> str:
        return self.investigations.listing().text

    def stored(self, investigation: Slug) -> tuple[LedgerRecord, ...]:
        with self.investigations.store.transaction() as repository:
            return recorded_ledger(repository, investigation).records


def added_empty_round(workspace: Workspace, investigation: Slug) -> str:
    return workspace.add(investigation, 1)


@pytest.fixture
def workspace(
    in_memory_investigation_service: InvestigationService, in_memory_git: InMemoryGit
) -> Workspace:
    return Workspace(investigations=in_memory_investigation_service, git=in_memory_git)


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
    return Committed(workspace=workspace, head=workspace.commit())


class TestStart:
    LONG_TARGET = InvestigationStart(
        target='Retry queue drains at a tenth of its rate after 2am', kind=TargetKind.BEHAVIOR
    )
    PROPOSED_CHANGE = InvestigationStart(
        target='Replace the drain loop with a scheduler', kind=TargetKind.CHANGE
    )
    ONLY_PUNCTUATION = InvestigationStart(target='???', kind=TargetKind.CLAIM)

    @pytest.fixture
    def three_investigations_of_one_target(self, workspace: Workspace) -> list[Slug]:
        return [workspace.start() for _ in range(3)]

    def test_start_writes_a_versioned_target_record(
        self, workspace: Workspace, investigation: Slug
    ) -> None:
        (target,) = workspace.stored(investigation)

        assert investigation.root.endswith('queue-drains-slowly')
        assert (target.seq, target.kind, target.cite) == (1, 'target', 'behavior')

    def test_start_names_the_investigation_after_the_day_and_the_target(
        self, workspace: Workspace
    ) -> None:
        view = workspace.investigations.start(TARGET, started=STARTED)

        assert view.investigation_id == '20260928-queue-drains-slowly'
        assert view.text == 'started 20260928-queue-drains-slowly\n'

    def test_the_target_is_stored_as_the_users_entry_of_round_zero(
        self, workspace: Workspace, investigation: Slug
    ) -> None:
        (target,) = workspace.stored(investigation)

        assert (target.text, target.source, target.round) == ('Queue drains slowly', 'user', 0)
        assert (target.at, target.supersedes) == ('2026-09-28T12:00:00+00:00', ())

    def test_long_targets_are_cut_at_a_word_boundary(self, workspace: Workspace) -> None:
        investigation = workspace.start(self.LONG_TARGET)

        assert investigation.root.endswith('-retry-queue-drains-at-a-tenth-of-its')

    def test_a_repeated_target_gets_a_numbered_investigation(
        self, three_investigations_of_one_target: list[Slug]
    ) -> None:
        assert [investigation.root for investigation in three_investigations_of_one_target] == [
            '20260928-queue-drains-slowly',
            '20260928-queue-drains-slowly-2',
            '20260928-queue-drains-slowly-3',
        ]

    def test_a_target_without_a_letter_or_a_digit_is_named_investigation(
        self, workspace: Workspace
    ) -> None:
        assert workspace.start(self.ONLY_PUNCTUATION).root == '20260928-investigation'

    def test_a_proposed_change_is_a_target_kind(self, workspace: Workspace) -> None:
        investigation = workspace.start(self.PROPOSED_CHANGE)

        assert 'Target: Replace the drain loop with a scheduler (change)' in workspace.render(
            investigation
        )


class TestAdd:
    @pytest.fixture
    def investigation_at_round_two(self, workspace: Workspace, investigation: Slug) -> Slug:
        workspace.add(investigation, 2, known('a', 'a:1'))
        return investigation

    def test_added_known_renders_with_its_citation(
        self, workspace: Workspace, investigation: Slug
    ) -> None:
        saved = workspace.add(investigation, 1, DRAIN_LOOP)
        rendered = workspace.render(investigation)

        assert saved.startswith('saved e2 ')
        assert '- e2: drain loop sleeps 10s [src/queue.py:41] (code-scout, round 1)' in rendered

    def test_a_batch_is_numbered_in_order_and_names_its_investigation(
        self, workspace: Workspace, investigation: Slug
    ) -> None:
        saved = workspace.add(investigation, 1, DRAIN_LOOP, QUESTION)

        assert saved == f'saved e2 e3 to {investigation} (0 redacted)\n'
        assert [record.seq for record in workspace.stored(investigation)] == [1, 2, 3]

    def test_an_earlier_round_is_rejected(
        self, workspace: Workspace, investigation_at_round_two: Slug
    ) -> None:
        with pytest.raises(RoundRegressionError) as refusal:
            workspace.add(investigation_at_round_two, 1)

        assert 'earlier than the latest round 2' in str(refusal.value)


class TestRedaction:
    LEAKING_CITE = known('the token is in the workflow', f'ci.yml:3 {FAKE_TOKEN}')

    def test_a_secret_in_a_cite_is_redacted_and_counted(
        self, workspace: Workspace, investigation: Slug
    ) -> None:
        saved = workspace.add(investigation, 1, self.LEAKING_CITE)

        assert '(1 redacted)' in saved
        assert workspace.stored(investigation)[1].cite == 'ci.yml:3 [REDACTED:github-token]'


class TestSupersedes:
    ANSWER = LedgerEntry(
        kind=EntryKind.KNOWN,
        text='backoff is 30s',
        cite='https://docs.example/q#backoff',
        source=Source.CODE_SCOUT,
        supersedes=(2,),
    )
    SUPERSEDING_NOTHING = LedgerEntry(
        kind=EntryKind.KNOWN, text='x', cite='a.py:1', source=Source.CODE_SCOUT, supersedes=(99,)
    )
    SUPERSEDING_THE_TARGET = LedgerEntry(
        kind=EntryKind.KNOWN, text='x', cite='a.py:1', source=Source.CODE_SCOUT, supersedes=(1,)
    )
    SUPERSEDING_ITS_OWN_BATCH = LedgerEntry(
        kind=EntryKind.KNOWN, text='x', cite='a.py:1', source=Source.CODE_SCOUT, supersedes=(2,)
    )

    @pytest.fixture
    def investigation_with_an_answered_question(
        self, workspace: Workspace, investigation: Slug
    ) -> Slug:
        workspace.add(investigation, 1, QUESTION)
        workspace.add(investigation, 2, self.ANSWER)
        return investigation

    def test_superseded_entries_leave_the_rendered_ledger(
        self, workspace: Workspace, investigation_with_an_answered_question: Slug
    ) -> None:
        rendered = workspace.render(investigation_with_an_answered_question)
        stored = [
            record.text for record in workspace.stored(investigation_with_an_answered_question)
        ]

        assert 'is backoff 30s?' not in rendered
        assert 'backoff is 30s' in rendered
        assert 'is backoff 30s?' in stored

    def test_superseding_an_unknown_entry_is_rejected(
        self, workspace: Workspace, investigation: Slug
    ) -> None:
        with pytest.raises(UnknownSupersededError) as refusal:
            workspace.add(investigation, 1, self.SUPERSEDING_NOTHING)

        assert 'supersedes unknown entries [99]' in str(refusal.value)

    @pytest.mark.parametrize(
        ('batch', 'refused'),
        [
            pytest.param((SUPERSEDING_THE_TARGET,), 'entry 0: ', id='the-target'),
            pytest.param((DRAIN_LOOP, SUPERSEDING_ITS_OWN_BATCH), 'entry 1: ', id='its-own-batch'),
        ],
    )
    def test_only_an_entry_stored_before_the_batch_can_be_superseded(
        self,
        batch: tuple[LedgerEntry, ...],
        refused: str,
        workspace: Workspace,
        investigation: Slug,
    ) -> None:
        with pytest.raises(UnknownSupersededError) as refusal:
            workspace.add(investigation, 1, *batch)

        assert str(refusal.value).startswith(refused)
        assert len(workspace.stored(investigation)) == 1


class TestRender:
    FIRST_NEXT = LedgerEntry(kind=EntryKind.NEXT, text='find callers', source=Source.CODE_SCOUT)
    SECOND_NEXT = LedgerEntry(kind=EntryKind.NEXT, text='fetch changelog', source=Source.WEB_SCOUT)
    DECISION = LedgerEntry(kind=EntryKind.DECISION, text='keep the floor', source=Source.USER)
    RESOURCE = LedgerEntry(
        kind=EntryKind.RESOURCE, text='the queue runbook', cite='docs/queue.md', source=Source.USER
    )

    @pytest.fixture
    def investigation_with_next_questions_in_two_rounds(
        self, workspace: Workspace, investigation: Slug
    ) -> Slug:
        workspace.add(investigation, 1, self.FIRST_NEXT)
        workspace.add(investigation, 2, self.SECOND_NEXT)
        return investigation

    @pytest.fixture
    def investigation_with_every_kind(self, workspace: Workspace, investigation: Slug) -> Slug:
        workspace.add(investigation, 1, DRAIN_LOOP, QUESTION, self.FIRST_NEXT)
        workspace.add(investigation, 2, self.DECISION, self.RESOURCE, self.SECOND_NEXT)
        return investigation

    def test_only_the_latest_round_next_questions_render(
        self, workspace: Workspace, investigation_with_next_questions_in_two_rounds: Slug
    ) -> None:
        rendered = workspace.render(investigation_with_next_questions_in_two_rounds)

        assert 'fetch changelog' in rendered
        assert 'find callers' not in rendered

    def test_the_ledger_renders_a_section_per_kind_and_the_latest_next_questions(
        self, workspace: Workspace, investigation_with_every_kind: Slug
    ) -> None:
        assert workspace.render(investigation_with_every_kind).splitlines() == [
            '## Ledger, round 2',
            'Target: Queue drains slowly (behavior)',
            '',
            '### Knowns',
            '- e2: drain loop sleeps 10s [src/queue.py:41] (code-scout, round 1)',
            '',
            '### Open',
            '- e3: is backoff 30s? (web-scout, round 1)',
            '',
            '### Decisions',
            '- e5: keep the floor (user, round 2)',
            '',
            '### Resources',
            '- e6: the queue runbook [docs/queue.md] (user, round 2)',
            '',
            '### Next',
            '- e7: fetch changelog (web-scout, round 2)',
        ]


class TestRead:
    PIPED_KNOWNS = tuple(known(f'a | {index}', 'a:1') for index in range(3))
    WHY = LedgerEntry(kind=EntryKind.OPEN, text='why?', source=Source.USER)
    TWO_KNOWNS = KnownsFilter(kinds=(EntryKind.KNOWN,), limit=2)

    @pytest.fixture
    def investigation_at_round_three(self, workspace: Workspace, investigation: Slug) -> Slug:
        workspace.add(investigation, 3, known('a', 'a:1'))
        return investigation

    @pytest.fixture
    def investigation_with_three_knowns_and_a_question(
        self, workspace: Workspace, investigation: Slug
    ) -> Slug:
        workspace.add(investigation, 1, *self.PIPED_KNOWNS, self.WHY)
        return investigation

    def test_unknown_investigation_names_the_list_command(self, workspace: Workspace) -> None:
        with pytest.raises(UnknownInvestigationError) as refusal:
            workspace.render(Slug('missing'))

        assert 'run list' in str(refusal.value)
        assert str(refusal.value) == "no investigation named 'missing'; run list"

    @pytest.mark.parametrize(
        'read',
        [
            pytest.param(Workspace.knowns, id='knowns'),
            pytest.param(added_empty_round, id='add'),
        ],
    )
    def test_every_action_on_one_investigation_refuses_an_unknown_one(
        self, read: Callable[[Workspace, Slug], str], workspace: Workspace
    ) -> None:
        with pytest.raises(UnknownInvestigationError):
            read(workspace, Slug('missing'))

    def test_list_reports_each_investigation_with_its_round(
        self, workspace: Workspace, investigation_at_round_three: Slug
    ) -> None:
        assert workspace.listing() == f'{investigation_at_round_three}\tround 3\n'

    def test_list_says_when_there_is_no_investigation(self, workspace: Workspace) -> None:
        assert workspace.listing() == 'no investigations\n'

    def test_knowns_table_is_bounded_filtered_and_escaped(
        self, workspace: Workspace, investigation_with_three_knowns_and_a_question: Slug
    ) -> None:
        table = workspace.knowns(investigation_with_three_knowns_and_a_question, self.TWO_KNOWNS)

        assert r'a \| 0' in table
        assert 'why?' not in table
        assert '1 more rows; ask again with a larger limit' in table

    def test_the_knowns_table_shows_every_kind_but_the_target_by_default(
        self, workspace: Workspace, investigation_with_three_knowns_and_a_question: Slug
    ) -> None:
        table = workspace.knowns(investigation_with_three_knowns_and_a_question)

        assert table.splitlines()[1:] == [
            '| entry | kind | claim | cite | source | round | status |',
            '|---|---|---|---|---|---|---|',
            r'| e2 | known | a \| 0 | a:1 | code-scout | 1 | lead |',
            r'| e3 | known | a \| 1 | a:1 | code-scout | 1 | lead |',
            r'| e4 | known | a \| 2 | a:1 | code-scout | 1 | lead |',
            '| e5 | open | why? |  | user | 1 | lead |',
        ]


class TestHead:
    @pytest.fixture
    def investigation_with_a_known_at_head(self, committed: Committed) -> Slug:
        investigation = committed.workspace.start()
        committed.workspace.add(investigation, 1, known('a', 'a:1'))
        return investigation

    @pytest.fixture
    def investigation_spanning_two_heads(
        self, workspace: Workspace, investigation_with_a_known_at_head: Slug
    ) -> Slug:
        workspace.commit()
        workspace.add(investigation_with_a_known_at_head, 2, known('b', 'b:1'))
        return investigation_with_a_known_at_head

    def test_entries_verified_at_head_are_current(
        self, committed: Committed, investigation_with_a_known_at_head: Slug
    ) -> None:
        table = committed.workspace.knowns(investigation_with_a_known_at_head)

        assert f'at HEAD {committed.head[:12]}' in table
        assert '| e2 | known | a | a:1 | code-scout | 1 | current |' in table

    def test_entries_from_an_older_head_become_leads(
        self, workspace: Workspace, investigation_spanning_two_heads: Slug
    ) -> None:
        table = workspace.knowns(investigation_spanning_two_heads)

        assert '| e2 | known | a | a:1 | code-scout | 1 | lead |' in table
        assert '| e3 | known | b | b:1 | code-scout | 2 | current |' in table

    def test_before_the_first_commit_every_entry_is_a_lead(
        self, workspace: Workspace, investigation_with_a_known: Slug
    ) -> None:
        table = workspace.knowns(investigation_with_a_known)

        assert f'## Knowns table, {investigation_with_a_known} at HEAD unknown' in table
        assert '| e2 | known | a | a:1 | code-scout | 1 | lead |' in table
