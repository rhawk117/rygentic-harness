"""The workspace: contained paths under `.mightymodels/`, and where git cannot answer."""

from collections.abc import Callable
from dataclasses import dataclass
from operator import methodcaller
from pathlib import Path

import pytest
from mightymodels.core.run_id import RunId
from mightymodels.core.workspace import (
    Git,
    OutsideStateDirectoryError,
    RecordFiles,
    UnsafeRevisionError,
    Workspace,
    revision_error,
    workspace_at,
)
from mightymodels.tools.tests.slug_calls import (
    REVIEW,
    SHOW,
    SLUG,
    START_REVIEW,
    TICKET,
    VALIDATE,
    WRITE,
    slug_results,
)
from mightymodels.tools.tests.support import StateServer, ToolCall, text_of, tree

type PathRequest = Callable[[Workspace], object]


RUN = RunId('20260101-000000')
ESCAPES = 'resolves outside .mightymodels/'
REPORT = Path(__file__).parent.joinpath('fixtures', 'merge-vader-report.md')
LIST_REVIEWS: ToolCall = ('review', {'request': {'action': 'list'}})


def snapshot_files(workspace: Workspace) -> RecordFiles:
    return workspace.handoffs.snapshot(TICKET)


def first_archive_files(workspace: Workspace) -> RecordFiles:
    return workspace.handoffs.archive(TICKET, 1)


def live_debug_note(workspace: Workspace) -> Path:
    return workspace.handoffs.live_debug(TICKET)


@dataclass(slots=True, kw_only=True, frozen=True)
class Escape:
    server: StateServer
    outside: Path
    untouched: dict[str, bytes]


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    directory = tmp_path.joinpath('outside')
    directory.mkdir()
    return directory


class TestSafeRevision:
    START_FROM_A_NEWLINE_BASE: ToolCall = (
        'review',
        {
            'request': {
                'action': 'start',
                'payload': {**REVIEW, 'scope': 'branch', 'base': 'main\n'},
            }
        },
    )

    @pytest.mark.parametrize(
        'revision',
        [
            pytest.param('main\n', id='trailing-newline'),
            pytest.param('\nmain', id='leading-newline'),
            pytest.param('--output=/tmp/pwned', id='option'),
            pytest.param('main branch', id='space'),
            pytest.param('main;id', id='shell-separator'),
            pytest.param('', id='empty'),
        ],
    )
    def test_safe_revision_refuses_anything_but_a_whole_plain_name(self, revision: str) -> None:
        refusal = revision_error(revision)

        assert isinstance(refusal, UnsafeRevisionError)
        assert refusal.revision == revision

    @pytest.mark.parametrize(
        'revision',
        [
            pytest.param('main', id='branch'),
            pytest.param('HEAD', id='head'),
            pytest.param('origin/fix/retry-queue', id='remote-branch'),
            pytest.param('v1.0.0-rc_1', id='tag'),
            pytest.param('a' * 40, id='sha'),
        ],
    )
    def test_safe_revision_accepts_a_plain_name(self, revision: str) -> None:
        assert revision_error(revision) is None

    def test_safe_revision_names_the_first_unsafe_name_of_several(self) -> None:
        refusal = revision_error('main', 'HEAD\n', '--all')

        assert isinstance(refusal, UnsafeRevisionError)
        assert refusal.revision == 'HEAD\n'

    def test_safe_revision_keeps_an_option_out_of_the_unpushed_commit_count(
        self, repository_git: Git
    ) -> None:
        with pytest.raises(UnsafeRevisionError) as refusal:
            repository_git.commits_on_no_remote('--all')

        assert refusal.value.revision == '--all'

    def test_safe_revision_keeps_a_trailing_newline_out_of_a_review_base(
        self, state_server: StateServer
    ) -> None:
        started, listed = state_server.call(self.START_FROM_A_NEWLINE_BASE, LIST_REVIEWS)

        assert started.is_error
        assert "'main\\n' is not a plain revision name" in text_of(started)
        assert listed.structured_content['text'] == 'no review runs\n'


class TestSymlinkBelowTheStateDirectory:
    ESCAPING = (
        pytest.param((SLUG,), methodcaller('ticket_file', TICKET), id='ticket-directory'),
        pytest.param((SLUG, 'ticket.yml'), methodcaller('ticket_file', TICKET), id='ticket-file'),
        pytest.param(
            (SLUG, 'ticket.yml.tmp'), methodcaller('ticket_draft', TICKET), id='ticket-draft'
        ),
        pytest.param((SLUG, 'briefs'), methodcaller('task_brief', TICKET, 4), id='briefs'),
        pytest.param(
            (SLUG, 'review'), methodcaller('review_directory', TICKET, RUN), id='ticket-reviews'
        ),
        pytest.param(('.runtime',), methodcaller('review_directory', None, RUN), id='runtime'),
        pytest.param(
            ('.runtime', 'reviews', RUN.root),
            methodcaller('persona_report', None, RUN, name='UNCLE-BOB-REPORT.md'),
            id='run-directory',
        ),
        pytest.param((SLUG, 'handoffs'), snapshot_files, id='handoffs'),
        pytest.param(('archives',), first_archive_files, id='archives'),
        pytest.param((SLUG, 'whats-broken.md'), live_debug_note, id='debug-note'),
    )

    @pytest.fixture
    def state(self, tmp_path: Path) -> Path:
        directory = tmp_path.joinpath('checkout', '.mightymodels')
        directory.mkdir(parents=True)
        return directory

    @pytest.fixture
    def workspace_with_a_symlink_to_outside(
        self, request: pytest.FixtureRequest, state: Path, outside: Path
    ) -> Workspace:
        planted = state.joinpath(*request.param)
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.symlink_to(outside)
        return workspace_at(state.parent)

    @pytest.fixture
    def workspace_with_a_dangling_symlink(self, state: Path, tmp_path: Path) -> Workspace:
        state.joinpath(SLUG).symlink_to(tmp_path.joinpath('never-created'))
        return workspace_at(state.parent)

    @pytest.fixture
    def workspace_with_a_symlink_that_stays_inside(self, state: Path) -> Workspace:
        state.joinpath('first-name').mkdir()
        state.joinpath(SLUG).symlink_to(state.joinpath('first-name'))
        return workspace_at(state.parent)

    @pytest.mark.parametrize(
        ('workspace_with_a_symlink_to_outside', 'requested'),
        ESCAPING,
        indirect=['workspace_with_a_symlink_to_outside'],
    )
    def test_a_symlink_that_leads_outside_is_refused_wherever_it_sits(
        self, workspace_with_a_symlink_to_outside: Workspace, requested: PathRequest
    ) -> None:
        with pytest.raises(OutsideStateDirectoryError) as refusal:
            requested(workspace_with_a_symlink_to_outside)

        assert refusal.value.shown.startswith('.mightymodels/')
        assert ESCAPES in str(refusal.value)

    def test_a_dangling_symlink_is_refused_before_anything_is_created_through_it(
        self, workspace_with_a_dangling_symlink: Workspace, tmp_path: Path
    ) -> None:
        with pytest.raises(OutsideStateDirectoryError):
            workspace_with_a_dangling_symlink.ticket_file(TICKET)

        assert not tmp_path.joinpath('never-created').exists()

    def test_a_symlink_that_stays_inside_the_state_directory_is_followed(
        self, workspace_with_a_symlink_that_stays_inside: Workspace, state: Path
    ) -> None:
        ticket = workspace_with_a_symlink_that_stays_inside.ticket_file(TICKET)

        assert ticket == state.joinpath('first-name', 'ticket.yml')


class TestStateDirectoryBoundary:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Workspace:
        return workspace_at(tmp_path)

    @pytest.fixture
    def workspace_whose_state_directory_is_a_symlink(
        self, tmp_path: Path, outside: Path
    ) -> Workspace:
        root = tmp_path.joinpath('linked-checkout')
        root.mkdir()
        root.joinpath('.mightymodels').symlink_to(outside)
        return workspace_at(root)

    def test_a_symlinked_state_directory_holds_the_paths_and_keeps_their_shown_names(
        self, workspace_whose_state_directory_is_a_symlink: Workspace, outside: Path
    ) -> None:
        ticket = workspace_whose_state_directory_is_a_symlink.ticket_file(TICKET)
        shown = workspace_whose_state_directory_is_a_symlink.relative_to_root(ticket)

        assert ticket == outside.joinpath(SLUG, 'ticket.yml')
        assert shown == f'.mightymodels/{SLUG}/ticket.yml'

    @pytest.mark.parametrize(
        'parts',
        [
            pytest.param(('..', 'outside'), id='parent'),
            pytest.param((SLUG, '..', '..', 'outside'), id='nested-parent'),
            pytest.param(('/etc',), id='absolute'),
        ],
    )
    def test_parts_that_climb_out_of_the_state_directory_are_refused(
        self, workspace: Workspace, parts: tuple[str, ...]
    ) -> None:
        with pytest.raises(OutsideStateDirectoryError):
            workspace.contained(*parts)


class TestHandoffFiles:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Workspace:
        return workspace_at(tmp_path)

    @pytest.mark.parametrize(
        ('repeat', 'name'),
        [
            pytest.param(1, SLUG, id='first'),
            pytest.param(2, f'{SLUG}-2', id='second'),
            pytest.param(11, f'{SLUG}-11', id='eleventh'),
        ],
    )
    def test_an_archive_is_named_for_the_ticket_and_numbered_from_its_second(
        self, workspace: Workspace, repeat: int, name: str
    ) -> None:
        files = workspace.handoffs.archive(TICKET, repeat)

        assert [workspace.relative_to_root(files.markdown), files.record.name] == [
            f'.mightymodels/archives/{name}.md',
            f'{name}.json',
        ]

    def test_the_snapshot_and_the_debug_note_sit_in_the_ticket_directory(
        self, workspace: Workspace
    ) -> None:
        snapshot = workspace.handoffs.snapshot(TICKET)
        note = workspace.handoffs.live_debug(TICKET)

        assert [
            workspace.relative_to_root(path) for path in (snapshot.markdown, snapshot.record, note)
        ] == [
            f'.mightymodels/{SLUG}/handoffs/snapshot.md',
            f'.mightymodels/{SLUG}/handoffs/snapshot.json',
            f'.mightymodels/{SLUG}/whats-broken.md',
        ]


class TestSymlinkedTicket:
    @pytest.fixture
    def ticket_directory(self, connected_server: StateServer) -> Path:
        state = connected_server.root.joinpath('.mightymodels')
        state.mkdir()
        return state.joinpath(SLUG)

    @pytest.fixture
    def empty_directory_outside(
        self, connected_server: StateServer, ticket_directory: Path, outside: Path
    ) -> Escape:
        ticket_directory.symlink_to(outside, target_is_directory=True)
        return Escape(server=connected_server, outside=outside, untouched=tree(outside))

    @pytest.fixture
    def valid_ticket_outside(
        self, connected_server: StateServer, ticket_directory: Path, outside: Path
    ) -> Escape:
        slug_results(connected_server, WRITE)
        ticket_directory.joinpath('ticket.yml').rename(outside.joinpath('ticket.yml'))
        ticket_directory.rmdir()
        ticket_directory.symlink_to(outside, target_is_directory=True)
        return Escape(server=connected_server, outside=outside, untouched=tree(outside))

    @pytest.fixture
    def draft_file_outside(
        self, connected_server: StateServer, ticket_directory: Path, outside: Path
    ) -> Escape:
        outside.joinpath('kept.txt').write_text('kept\n', encoding='utf-8')
        ticket_directory.mkdir()
        ticket_directory.joinpath('ticket.yml.tmp').symlink_to(outside.joinpath('kept.txt'))
        return Escape(server=connected_server, outside=outside, untouched=tree(outside))

    def test_ticket_write_through_a_symlink_to_a_directory_outside_is_refused(
        self, empty_directory_outside: Escape
    ) -> None:
        (written,) = slug_results(empty_directory_outside.server, WRITE)

        assert written.is_error
        assert ESCAPES in text_of(written)
        assert tree(empty_directory_outside.outside) == empty_directory_outside.untouched

    def test_ticket_validate_reads_nothing_through_a_symlink_to_a_directory_outside(
        self, valid_ticket_outside: Escape
    ) -> None:
        validated, shown = slug_results(valid_ticket_outside.server, VALIDATE, SHOW)

        assert validated.is_error
        assert ESCAPES in text_of(validated)
        assert f'{SLUG} is not staged' in text_of(shown)
        assert tree(valid_ticket_outside.outside) == valid_ticket_outside.untouched

    def test_ticket_write_does_not_write_through_a_symlinked_draft_file(
        self, draft_file_outside: Escape
    ) -> None:
        (written,) = slug_results(draft_file_outside.server, WRITE)

        assert written.is_error
        assert ESCAPES in text_of(written)
        assert tree(draft_file_outside.outside) == draft_file_outside.untouched


class TestSymlinkedReviewDirectory:
    @pytest.fixture
    def reviews_directory_outside(self, connected_server: StateServer, outside: Path) -> Escape:
        runtime = connected_server.root.joinpath('.mightymodels', '.runtime')
        runtime.mkdir(parents=True)
        runtime.joinpath('reviews').symlink_to(outside, target_is_directory=True)
        return Escape(server=connected_server, outside=outside, untouched=tree(outside))

    @pytest.fixture
    def started_run(self, connected_server: StateServer) -> str:
        (started,) = connected_server.call(START_REVIEW)
        return started.structured_content['run_id']

    @pytest.fixture
    def run_directory_outside(
        self, connected_server: StateServer, started_run: str, outside: Path
    ) -> Escape:
        report = outside.joinpath('MERGE-VADER-REPORT.md')
        report.write_text(REPORT.read_text(encoding='utf-8'), encoding='utf-8')
        directory = connected_server.root.joinpath(
            '.mightymodels', '.runtime', 'reviews', started_run
        )
        directory.rmdir()
        directory.symlink_to(outside, target_is_directory=True)
        return Escape(server=connected_server, outside=outside, untouched=tree(outside))

    def test_review_start_through_a_symlinked_reviews_directory_is_refused(
        self, reviews_directory_outside: Escape
    ) -> None:
        started, listed = reviews_directory_outside.server.call(START_REVIEW, LIST_REVIEWS)

        assert started.is_error
        assert ESCAPES in text_of(started)
        assert listed.structured_content['text'] == 'no review runs\n'
        assert tree(reviews_directory_outside.outside) == reviews_directory_outside.untouched

    def test_review_add_reads_no_report_through_a_symlinked_run_directory(
        self, run_directory_outside: Escape, started_run: str
    ) -> None:
        added, listed = run_directory_outside.server.call(
            (
                'review',
                {
                    'request': {
                        'action': 'add',
                        'run_id': started_run,
                        'payload': {'persona': 'merge-vader'},
                    }
                },
            ),
            LIST_REVIEWS,
        )

        assert added.is_error
        assert ESCAPES in text_of(added)
        assert '\t0 findings\t' in listed.structured_content['text']
        assert tree(run_directory_outside.outside) == run_directory_outside.untouched
