"""The investigation service against a real git repository, with ledger.py's tests moved here."""

from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.investigation.errors import (
    RoundRegressionError,
    UnknownInvestigationError,
    UnknownSupersededError,
)
from mightymodels_plugin.tools.investigation.ledger import recorded_ledger
from mightymodels_plugin.tools.investigation.repository import (
    LedgerRecord,
    investigation_transaction,
)
from mightymodels_plugin.tools.investigation.schema import (
    EntryKind,
    InvestigationStart,
    KnownsFilter,
    LedgerEntry,
    Source,
    TargetKind,
)
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.tests.support import investigation_service_at
from mightymodels_plugin.tools.tests.support import (
    ActivityKind,
    DatabaseActivity,
    StateServer,
    stored_bytes,
    text_of,
)

type GitRunner = Callable[..., str]

FAKE_TOKEN = 'ghp_' + 'a' * 36
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
STARTED = datetime(2026, 9, 28, 12, tzinfo=UTC)
TARGET = InvestigationStart(target='Queue drains slowly', kind=TargetKind.BEHAVIOR)
EVERY_KIND = KnownsFilter()
START_REQUEST = {'target': 'Queue drains slowly', 'kind': 'behavior'}
VALID_ENTRY = {'kind': 'known', 'text': 'first', 'cite': 'a.py:1', 'source': 'code-scout'}


def known(text: str, cite: str) -> LedgerEntry:
    return LedgerEntry(kind=EntryKind.KNOWN, text=text, cite=cite, source=Source.CODE_SCOUT)


DRAIN_LOOP = known('drain loop sleeps 10s', 'src/queue.py:41')
QUESTION = LedgerEntry(kind=EntryKind.OPEN, text='is backoff 30s?', source=Source.WEB_SCOUT)


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    investigations: InvestigationService
    runner: GitRunner

    @property
    def root(self) -> Path:
        return self.investigations.workspace.root

    def git(self, *arguments: str) -> str:
        return self.runner(self.root, *IDENTITY, *arguments).strip()

    def commit(self, message: str) -> str:
        self.git('commit', '--quiet', '--allow-empty', '-m', message)
        return self.git('rev-parse', 'HEAD')

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
        with investigation_transaction(self.investigations.database) as repository:
            return recorded_ledger(repository, investigation).records

    def database_bytes(self) -> bytes:
        return stored_bytes(self.investigations.database)


def added_empty_round(workspace: Workspace, investigation: Slug) -> str:
    return workspace.add(investigation, 1)


@pytest.fixture
def workspace(investigation_service: InvestigationService, git: GitRunner) -> Workspace:
    return Workspace(investigations=investigation_service, runner=git)


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


class TestStart:
    LONG_TARGET = InvestigationStart(
        target='Retry queue drains at a tenth of its rate after 2am', kind=TargetKind.BEHAVIOR
    )
    PROPOSED_CHANGE = InvestigationStart(
        target='Replace the drain loop with a scheduler', kind=TargetKind.CHANGE
    )
    LEAKING_TARGET = InvestigationStart(
        target=f'Why does {FAKE_TOKEN} reach the log', kind=TargetKind.BEHAVIOR
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

    def test_a_secret_in_the_target_reaches_neither_the_row_nor_the_id(
        self, workspace: Workspace
    ) -> None:
        investigation = workspace.start(self.LEAKING_TARGET)
        (target,) = workspace.stored(investigation)

        assert target.text == 'Why does [REDACTED:github-token] reach the log'
        assert investigation.root == '20260928-why-does-redacted-github-token-reach-the'
        assert FAKE_TOKEN.encode() not in workspace.database_bytes()


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
    LEAKING = known(f'CI uses {FAKE_TOKEN} and password=hunter2', 'ci.yml:3')
    LEAKING_CITE = known('the token is in the workflow', f'ci.yml:3 {FAKE_TOKEN}')

    def test_secrets_are_redacted_before_they_reach_disk(
        self, workspace: Workspace, investigation: Slug
    ) -> None:
        saved = workspace.add(investigation, 1, self.LEAKING)
        stored = workspace.database_bytes()

        assert '(2 redacted)' in saved
        assert FAKE_TOKEN.encode() not in stored
        assert b'hunter2' not in stored

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
        workspace.commit('later')
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
                workspace=Workspace(investigations=investigations, runner=git), head=committed.head
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


class TestTheTool:
    UNKNOWN_KIND = "Input should be 'target', 'known', 'open', 'decision', 'resource' or 'next'"

    @pytest.fixture
    def started_through_the_tool(self, state_server: StateServer) -> Slug:
        (started,) = state_server.call(
            ('investigation', {'action': 'start', 'payload': {'request': START_REQUEST}})
        )
        return Slug(started.structured_content['investigation_id'])

    def test_a_ledger_in_a_repository_is_never_tracked(
        self, state_server: StateServer, started_through_the_tool: Slug, git: GitRunner
    ) -> None:
        exclude = state_server.root.joinpath('.git', 'info', 'exclude')

        assert started_through_the_tool.root.endswith('queue-drains-slowly')
        assert '.mightymodels/' in exclude.read_text(encoding='utf-8').splitlines()
        assert git(state_server.root, 'status', '--porcelain') == ''

    @pytest.mark.parametrize(
        ('entry', 'reason'),
        [
            pytest.param(
                {'kind': 'known', 'text': 'no cite', 'source': 'code-scout'},
                'needs a cite',
                id='no-cite',
            ),
            pytest.param(
                {'kind': 'decision', 'text': 'use v2', 'source': 'primary'},
                'cannot come from primary',
                id='decision-from-primary',
            ),
            pytest.param(
                {'kind': 'target', 'text': 'x', 'source': 'user'}, 'written by start', id='target'
            ),
            pytest.param(
                {'kind': 'open', 'text': '  ', 'source': 'user'}, 'text is empty', id='blank-text'
            ),
            pytest.param(
                {'kind': 'nonsense', 'text': 'x', 'source': 'user'}, UNKNOWN_KIND, id='unknown-kind'
            ),
            pytest.param(
                {'kind': 'next', 'text': 'look again', 'source': 'primary'},
                'a next entry cannot come from primary',
                id='next-from-primary',
            ),
            pytest.param(
                {'kind': 'resource', 'text': 'the runbook', 'source': 'user'},
                'a resource entry needs a cite',
                id='resource-without-a-cite',
            ),
        ],
    )
    def test_invalid_entry_is_rejected_without_writing(
        self,
        entry: dict[str, str],
        reason: str,
        state_server: StateServer,
        started_through_the_tool: Slug,
        workspace: Workspace,
    ) -> None:
        before = workspace.stored(started_through_the_tool)
        (refused,) = state_server.call(
            (
                'investigation',
                {
                    'action': 'add',
                    'investigation_id': started_through_the_tool.root,
                    'payload': {'entries': [VALID_ENTRY, entry], 'request': {'round': 1}},
                },
            )
        )
        after = workspace.stored(started_through_the_tool)

        assert refused.is_error
        assert reason in text_of(refused)
        assert before == after

    def test_a_round_is_added_rendered_and_listed_through_the_tool(
        self, state_server: StateServer, started_through_the_tool: Slug
    ) -> None:
        investigation = started_through_the_tool.root
        added, rendered, knowns, listed = state_server.call(
            (
                'investigation',
                {
                    'action': 'add',
                    'investigation_id': investigation,
                    'payload': {'entries': [VALID_ENTRY], 'request': {'round': 1}},
                },
            ),
            ('investigation', {'action': 'render', 'investigation_id': investigation}),
            (
                'investigation',
                {
                    'action': 'knowns',
                    'investigation_id': investigation,
                    'payload': {'request': {'kinds': ['open'], 'limit': 5}},
                },
            ),
            ('investigation', {'action': 'list'}),
        )

        assert added.structured_content == {
            'text': f'saved e2 to {investigation} (0 redacted)\n',
            'investigation_id': investigation,
        }
        assert '- e2: first [a.py:1] (code-scout, round 1)' in rendered.structured_content['text']
        assert '| e2 |' not in knowns.structured_content['text']
        assert listed.structured_content == {
            'text': f'{investigation}\tround 1\n',
            'investigation_id': None,
        }

    def test_knowns_without_a_request_shows_the_whole_table(
        self, state_server: StateServer, started_through_the_tool: Slug
    ) -> None:
        investigation = started_through_the_tool.root
        _, knowns = state_server.call(
            (
                'investigation',
                {
                    'action': 'add',
                    'investigation_id': investigation,
                    'payload': {'entries': [VALID_ENTRY], 'request': {'round': 1}},
                },
            ),
            ('investigation', {'action': 'knowns', 'investigation_id': investigation}),
        )

        assert (
            '| e2 | known | first | a.py:1 | code-scout | 1 | lead |'
            in (knowns.structured_content['text'])
        )

    @pytest.mark.parametrize(
        ('arguments', 'needs'),
        [
            pytest.param(
                {'action': 'start'},
                'start needs a request holding target and kind',
                id='start-without-a-request',
            ),
            pytest.param(
                {'action': 'start', 'payload': {'request': {'round': 1}}},
                'start needs a request holding target and kind',
                id='start-with-a-round',
            ),
            pytest.param(
                {'action': 'add', 'payload': {'entries': [], 'request': {'round': 1}}},
                'add needs investigation_id',
                id='add-without-an-investigation',
            ),
            pytest.param(
                {'action': 'add', 'investigation_id': 'a', 'payload': {'request': {'round': 1}}},
                'add needs entries and a request holding round',
                id='add-without-entries',
            ),
            pytest.param(
                {'action': 'add', 'investigation_id': 'a', 'payload': {'entries': []}},
                'add needs entries and a request holding round',
                id='add-without-a-round',
            ),
            pytest.param(
                {'action': 'render'}, 'render needs investigation_id', id='render-of-nothing'
            ),
            pytest.param(
                {'action': 'knowns'}, 'knowns needs investigation_id', id='knowns-of-nothing'
            ),
            pytest.param(
                {'action': 'knowns', 'investigation_id': 'a', 'payload': {'request': {'round': 1}}},
                'knowns needs no request, or a request holding only kinds and limit',
                id='knowns-with-a-round',
            ),
        ],
    )
    def test_an_action_missing_its_part_says_what_it_needs(
        self,
        arguments: dict[str, object],
        needs: str,
        connected_server: StateServer,
        database_activity: DatabaseActivity,
    ) -> None:
        (refused,) = connected_server.call(('investigation', arguments))

        assert refused.is_error
        assert needs in text_of(refused)
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()

    @pytest.mark.parametrize(
        'arguments',
        [
            pytest.param({'action': 'delete'}, id='unknown-action'),
            pytest.param(
                {'action': 'render', 'investigation_id': '../outside'}, id='path-shaped-id'
            ),
            pytest.param(
                {'action': 'start', 'payload': {'request': {'target': 'x', 'kind': 'hunch'}}},
                id='unknown-target-kind',
            ),
            pytest.param(
                {
                    'action': 'start',
                    'payload': {'request': {**START_REQUEST, 'path': 'ledger.jsonl'}},
                },
                id='unknown-request-field',
            ),
            pytest.param(
                {'action': 'knowns', 'investigation_id': 'a', 'payload': {'request': {'limit': 0}}},
                id='knowns-limit-zero',
            ),
            pytest.param(
                {
                    'action': 'knowns',
                    'investigation_id': 'a',
                    'payload': {'request': {'kinds': ['target']}},
                },
                id='knowns-of-the-target',
            ),
            pytest.param(
                {
                    'action': 'knowns',
                    'investigation_id': 'a',
                    'payload': {'request': {'kinds': []}},
                },
                id='knowns-of-no-kind',
            ),
            pytest.param(
                {
                    'action': 'add',
                    'investigation_id': 'a',
                    'payload': {'request': {'round': 1}, 'entries': [{**VALID_ENTRY, 'seq': 7}]},
                },
                id='entry-numbering-itself',
            ),
            pytest.param(
                {
                    'action': 'add',
                    'investigation_id': 'a',
                    'payload': {
                        'request': {'round': 1},
                        'entries': [{**VALID_ENTRY, 'cite': '  '}],
                    },
                },
                id='blank-cite',
            ),
        ],
    )
    def test_arguments_outside_the_schema_are_refused(
        self,
        arguments: dict[str, object],
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (refused,) = connected_server.call(('investigation', arguments))

        assert refused.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert connected_server.files_on_disk() == tree_after_the_connect
