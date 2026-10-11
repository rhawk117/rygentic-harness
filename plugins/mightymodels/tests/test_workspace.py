"""The workspace: contained paths under `.mightymodels/`, and where git cannot answer."""

import sys
from collections.abc import Callable
from dataclasses import dataclass
from operator import methodcaller
from pathlib import Path

import pytest
import sqlalchemy as sql
from mcp.types import CallToolResult
from mightymodels_plugin.cli import main
from mightymodels_plugin.core.data_directory import SESSION_DATA_VARIABLE
from mightymodels_plugin.core.process import process_runner
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.core.workspace import (
    PROJECT_DIR_VARIABLE,
    Git,
    OutsideStateDirectoryError,
    RecordFiles,
    UnsafeRevisionError,
    Workspace,
    git_at,
    revision_error,
    workspace_at,
)
from mightymodels_plugin.tools.contract.repository import contract_store
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.task.tables import TransitionRow
from mightymodels_plugin.tools.tests.support import (
    StateServer,
    ToolCall,
    text_of,
    tree,
    workspace_database,
)

type PathRequest = Callable[[Workspace], object]


SLUG = 'retry-queue'
TICKET = Slug(SLUG)
RUN = RunId('20260101-000000')
PASSED, REJECTED = 0, 2
TOOL_NAMES = [
    'close',
    'contract',
    'crashout',
    'failed_fix',
    'investigation',
    'review',
    'similarity',
    'snapshot',
    'task',
    'ticket',
]
ESCAPES = 'resolves outside .mightymodels/'
NEEDS_GIT = 'this needs git and no git executable is on PATH'
NOT_A_REPOSITORY = 'is not inside a git repository'
MARKER = 'ran.txt'
MARKER_COMMAND = {
    'id': 'I1',
    'argv': [sys.executable, '-c', f'from pathlib import Path; Path({MARKER!r}).write_text("ran")'],
    'approved_by': 'user',
}
REVIEW = {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'}
REPORT = Path(__file__).parent.joinpath('fixtures', 'merge-vader-report.md')
WRITE: ToolCall = (
    'ticket',
    {
        'action': 'write',
        'fields': {
            'summary': 'Retry queue drains slowly',
            'scope': 'med',
            'compaction': False,
            'branch': 'fix/retry-queue',
            'context': ['drain loop sleeps between batches'],
        },
    },
)
VALIDATE: ToolCall = ('ticket', {'action': 'validate'})
SHOW: ToolCall = ('ticket', {'action': 'show'})
START_TASK: ToolCall = (
    'task',
    {
        'action': 'start',
        'payload': {'task_id': 'T1', 'change': {'by': 'engineer', 'owned': ['src/queue.py']}},
    },
)
VERIFY_TASK: ToolCall = (
    'task',
    {'action': 'verify', 'payload': {'task_id': 'T1', 'change': {'commit': 'HEAD'}}},
)
READY: ToolCall = ('task', {'action': 'ready'})
APPROVE: ToolCall = ('contract', {'action': 'approve', 'commands': [MARKER_COMMAND]})
STATUS: ToolCall = ('contract', {'action': 'status'})
START_REVIEW: ToolCall = ('review', {'action': 'start', 'payload': REVIEW})
LIST_REVIEWS: ToolCall = ('review', {'action': 'list'})


def snapshot_files(workspace: Workspace) -> RecordFiles:
    return workspace.handoffs.snapshot(TICKET)


def first_archive_files(workspace: Workspace) -> RecordFiles:
    return workspace.handoffs.archive(TICKET, 1)


def live_debug_note(workspace: Workspace) -> Path:
    return workspace.handoffs.live_debug(TICKET)


def slug_results(server: StateServer, *calls: ToolCall) -> list[CallToolResult]:
    return server.call(*((name, {'slug': SLUG, **arguments}) for name, arguments in calls))


@dataclass(slots=True, kw_only=True, frozen=True)
class Escape:
    server: StateServer
    outside: Path
    untouched: dict[str, bytes]


@dataclass(slots=True, kw_only=True, frozen=True)
class Project:
    server: StateServer
    data_directory: Path
    marker: Path

    def verify_a_started_task(self) -> CallToolResult:
        *_, verified = slug_results(self.server, WRITE, VALIDATE, START_TASK, VERIFY_TASK)
        return verified

    def transitions(self) -> list[tuple[str, str]]:
        query = sql.select(TransitionRow).order_by(TransitionRow.id)
        workspace = workspace_at(self.server.root)
        with (
            workspace_database(workspace, self.data_directory) as database,
            database.transaction() as session,
        ):
            return [(row.before, row.after) for row in session.scalars(query)]

    def command_states(self) -> list[str]:
        workspace = workspace_at(self.server.root)
        with workspace_database(workspace, self.data_directory) as database:
            status = ContractService(
                workspace=workspace,
                store=contract_store(database),
                git=git_at(self.server.root),
                processes=process_runner(),
            ).status(TICKET)
        return [command.state for command in status.commands]

    def created_files(self) -> dict[str, bytes]:
        return tree(self.server.root) | tree(self.data_directory)

    def results_of_the_other_actions(self) -> list[CallToolResult]:
        staged_then_asked = slug_results(self.server, WRITE, VALIDATE, START_TASK, READY, STATUS)
        return [*staged_then_asked[2:], *self.server.call(START_REVIEW)]


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    directory = tmp_path.joinpath('outside')
    directory.mkdir()
    return directory


@pytest.fixture
def project(
    state_server: StateServer, data_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> Project:
    monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(state_server.root))
    monkeypatch.setenv(SESSION_DATA_VARIABLE, str(data_directory))
    slug_results(state_server, APPROVE)
    return Project(
        server=state_server,
        data_directory=data_directory,
        marker=state_server.root.joinpath(MARKER),
    )


class TestSafeRevision:
    START_FROM_A_NEWLINE_BASE: ToolCall = (
        'review',
        {'action': 'start', 'payload': {**REVIEW, 'scope': 'branch', 'base': 'main\n'}},
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
                {'action': 'add', 'run_id': started_run, 'payload': {'persona': 'merge-vader'}},
            ),
            LIST_REVIEWS,
        )

        assert added.is_error
        assert ESCAPES in text_of(added)
        assert '\t0 findings\t' in listed.structured_content['text']
        assert tree(run_directory_outside.outside) == run_directory_outside.untouched


class TestInsideARepository:
    IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')

    @pytest.fixture
    def first_commit(self, repository: Path, git: GitRunner) -> None:
        git(repository, *self.IDENTITY, 'commit', '--quiet', '--allow-empty', '-m', 'first commit')

    @pytest.mark.usefixtures('first_commit')
    def test_verify_run_runs_the_approved_command_where_git_answers(
        self, project: Project, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(['verify', 'run', '--slug', SLUG, '--all'])

        assert code == PASSED
        assert capsys.readouterr().out.startswith('I1 pass ')
        assert project.marker.read_text(encoding='utf-8') == 'ran'
        assert project.command_states() == ['pass task expect=0']


class TestWhenGitIsMissing:
    @pytest.fixture
    def project_without_git(
        self, project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Project:
        monkeypatch.setenv('PATH', str(tmp_path.joinpath('no-binaries')))
        return project

    def test_when_git_is_missing_the_server_lists_its_tools_and_refuses_every_ticket_call(
        self, project_without_git: Project
    ) -> None:
        listed = project_without_git.server.tools()
        refused = slug_results(project_without_git.server, WRITE, VALIDATE, SHOW)

        assert sorted(listed) == TOOL_NAMES
        assert [result.is_error for result in refused] == [True, True, True]
        assert [NEEDS_GIT in text_of(result) for result in refused] == [True, True, True]

    def test_when_git_is_missing_task_verify_is_refused_and_records_no_transition(
        self, project_without_git: Project
    ) -> None:
        verified = project_without_git.verify_a_started_task()

        assert verified.is_error
        assert NEEDS_GIT in text_of(verified)
        assert project_without_git.transitions() == []

    def test_when_git_is_missing_verify_run_is_refused_before_any_command_runs(
        self, project_without_git: Project, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(['verify', 'run', '--slug', SLUG, '--all'])

        assert code == REJECTED
        assert NEEDS_GIT in capsys.readouterr().err
        assert not project_without_git.marker.exists()
        assert project_without_git.command_states() == ['never-run']

    def test_when_git_is_missing_every_other_action_is_refused_the_same_way(
        self, project_without_git: Project
    ) -> None:
        refused = project_without_git.results_of_the_other_actions()

        assert [result.is_error for result in refused] == [True] * 4
        assert [NEEDS_GIT in text_of(result) for result in refused] == [True] * 4


class TestOutsideARepository:
    @pytest.fixture
    def state_server(self, tmp_path: Path, data_directory: Path) -> StateServer:
        directory = tmp_path.joinpath('plain-directory')
        directory.mkdir()
        return StateServer(root=directory, data_directory=data_directory)

    def test_outside_a_repository_task_verify_is_refused_and_nothing_is_created(
        self, project: Project
    ) -> None:
        verified = project.verify_a_started_task()

        assert verified.is_error
        assert NOT_A_REPOSITORY in text_of(verified)
        assert project.created_files() == {}

    def test_outside_a_repository_verify_run_is_refused_before_any_command_runs(
        self, project: Project, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(['verify', 'run', '--slug', SLUG, '--all'])

        assert code == REJECTED
        assert NOT_A_REPOSITORY in capsys.readouterr().err
        assert project.created_files() == {}

    def test_outside_a_repository_every_other_action_is_refused_the_same_way(
        self, project: Project
    ) -> None:
        refused = project.results_of_the_other_actions()

        assert [result.is_error for result in refused] == [True] * 4
        assert [NOT_A_REPOSITORY in text_of(result) for result in refused] == [True] * 4
