"""The slug is the only caller-chosen text that becomes a path, so it is checked in one type."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels_plugin.cli import main
from mightymodels_plugin.core.data_directory import SESSION_DATA_VARIABLE
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.slug import InvalidSlugError, Slug, parsed_slug
from mightymodels_plugin.core.tests.hostile_slugs import HOSTILE
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.core.workspace import workspace_at
from mightymodels_plugin.tools.investigation.schema import InvestigationStart, TargetKind
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.review.tables import ReviewFindingRow
from mightymodels_plugin.tools.tests.support import (
    ActivityKind,
    DatabaseActivity,
    StateServer,
    ToolCall,
    text_of,
    tree,
)
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import InvalidTicketError, TicketService

REJECTED = 2
OUTSIDE = '../../../outside'
ANSWERS = {
    'summary': 'Retry queue drains slowly',
    'scope': 'med',
    'compaction': False,
    'branch': 'fix/retry-queue',
    'context': ['drain loop sleeps between batches'],
}
HOSTILE_RUN_IDS = [
    pytest.param('../../etc', id='parents'),
    pytest.param('..', id='dot-dot'),
    pytest.param('20260101-000000/../x', id='trailing-parent'),
    pytest.param('20260101-000000\n', id='trailing-newline'),
    pytest.param('/etc', id='absolute'),
    pytest.param('', id='empty'),
]
RUN_CALLS = [
    pytest.param({'action': 'add', 'payload': {'persona': 'merge-vader'}}, id='add'),
    pytest.param({'action': 'gate'}, id='gate'),
    pytest.param(
        {'action': 'dispose', 'payload': {'by': 'user', 'decisions': {'F1': {'decision': 'fix'}}}},
        id='dispose',
    ),
    pytest.param(
        {'action': 'resolve', 'payload': {'finding': 'F1', 'result': 'failed', 'reason': 'r'}},
        id='resolve',
    ),
    pytest.param({'action': 'report'}, id='report'),
]
NON_ASCII_DIGIT_RUN_ID = '2026010\u0662-000000'
NON_ASCII_DIGIT_FINDING_ID = 'F\u0662'
WELL_FORMED_RUN_ID = '20260101-000000'
NON_ASCII_DIGIT_FINDING_CALLS = [
    pytest.param(
        {
            'action': 'dispose',
            'payload': {
                'by': 'user',
                'decisions': {NON_ASCII_DIGIT_FINDING_ID: {'decision': 'fix'}},
            },
        },
        id='dispose',
    ),
    pytest.param(
        {
            'action': 'resolve',
            'payload': {'finding': NON_ASCII_DIGIT_FINDING_ID, 'result': 'failed', 'reason': 'r'},
        },
        id='resolve',
    ),
]
START_PAYLOAD = {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'}
TOOL_CALLS = (
    ('ticket-write', 'ticket', {'action': 'write', 'fields': ANSWERS}),
    ('ticket-validate', 'ticket', {'action': 'validate'}),
    ('ticket-show', 'ticket', {'action': 'show'}),
    ('ticket-context', 'ticket', {'action': 'update-context', 'fields': {'context': ['x']}}),
    (
        'task-start',
        'task',
        {
            'action': 'start',
            'payload': {
                'task_id': 'T1',
                'change': {'by': 'engineer', 'owned': ['a.py'], 'acceptance': ['AC-1']},
            },
        },
    ),
    (
        'task-verify',
        'task',
        {'action': 'verify', 'payload': {'task_id': 'T1', 'change': {'commit': 'HEAD'}}},
    ),
    ('task-show', 'task', {'action': 'show'}),
    ('task-ready', 'task', {'action': 'ready'}),
    (
        'contract-approve',
        'contract',
        {'action': 'approve', 'commands': [{'id': 'I1', 'argv': ['true'], 'approved_by': 'user'}]},
    ),
    ('contract-status', 'contract', {'action': 'status'}),
)
CALLS = [pytest.param(name, arguments, id=label) for label, name, arguments in TOOL_CALLS]


LEAKING_REPORT = """## Findings

### High

#### UB-1 | [G5] Hardcoded password=hunter22 in the store \u2014 `src/store.py:4`

- Evidence (convention): ruff.toml S105; src/a.py:1, src/b.py:2
- Fix: Read the secret from the environment instead of ghp_abcdefghijklmnopqrstuvwxyzABCDEF123456.
- Verify: `rg -n 'password' src/store.py`
"""


@pytest.fixture
def project(repository: Path, data_directory: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(repository))
    monkeypatch.setenv(SESSION_DATA_VARIABLE, str(data_directory))
    repository.joinpath('outside.jsonl').write_text('', encoding='utf-8')
    return repository


class TestReservedName:
    WRITE_OF_THE_RESERVED_NAME: ToolCall = (
        'ticket',
        {'request': {'action': 'write', 'fields': ANSWERS, 'slug': 'archives'}},
    )

    def test_slug_reservation_a_parsed_slug_says_the_name_is_reserved(self) -> None:
        refusal = parsed_slug('archives')

        assert isinstance(refusal, InvalidSlugError)
        assert "never 'archives', the name reserved for the archive directory" in str(refusal)

    def test_slug_reservation_a_tool_call_says_the_name_is_reserved(
        self, state_server: StateServer
    ) -> None:
        (result,) = state_server.call(self.WRITE_OF_THE_RESERVED_NAME)

        assert result.is_error
        assert "'archives' is reserved for the archive directory" in text_of(result)

    @pytest.mark.parametrize(
        'raw',
        [
            pytest.param('archives-2', id='suffixed'),
            pytest.param('my-archives', id='prefixed'),
        ],
    )
    def test_slug_reservation_a_name_that_only_contains_the_reserved_one_stays_a_slug(
        self, raw: str
    ) -> None:
        assert parsed_slug(raw) == Slug(raw)


@pytest.fixture
def tmp_path_tree_after_the_connect(connected_server: StateServer) -> dict[str, bytes]:
    return tree(connected_server.root.parent)


@pytest.mark.usefixtures('project')
class TestHostileSlug:
    @pytest.fixture
    def tmp_path_tree_before_the_run(self, tmp_path: Path) -> dict[str, bytes]:
        return tree(tmp_path)

    @pytest.mark.parametrize('raw', HOSTILE)
    @pytest.mark.parametrize(('name', 'arguments'), CALLS)
    def test_slug_confinement_a_tool_reads_and_writes_nothing_for_a_hostile_slug(
        self,
        tmp_path: Path,
        connected_server: StateServer,
        tmp_path_tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
        *,
        name: str,
        arguments: dict[str, object],
        raw: str,
    ) -> None:
        (result,) = connected_server.call((name, {'request': {**arguments, 'slug': raw}}))

        assert result.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert tree(tmp_path) == tmp_path_tree_after_the_connect

    @pytest.mark.parametrize('raw', HOSTILE)
    def test_slug_confinement_verify_run_reads_and_writes_nothing_for_a_hostile_slug(
        self,
        tmp_path: Path,
        tmp_path_tree_before_the_run: dict[str, bytes],
        database_activity: DatabaseActivity,
        *,
        raw: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        code = main(['verify', 'run', f'--slug={raw}', '--all'])

        assert code == REJECTED
        assert 'is not a slug' in capsys.readouterr().err
        assert database_activity.kinds() == []
        assert tree(tmp_path) == tmp_path_tree_before_the_run


class TestInsideTheStateDirectory:
    RETRY_QUEUE_CALLS: tuple[ToolCall, ...] = tuple(
        (name, {'request': {**arguments, 'slug': 'retry-queue'}})
        for _, name, arguments in TOOL_CALLS
    )

    TARGET = InvestigationStart(target='Queue drains slowly', kind=TargetKind.BEHAVIOR)
    STARTED = datetime(2026, 9, 28, tzinfo=UTC)

    @pytest.fixture
    def started_investigation(self, investigation_service: InvestigationService) -> None:
        investigation_service.start(self.TARGET, started=self.STARTED)

    def stage(self, tickets: TicketService, investigations: list[str]) -> str:
        answers = TicketAnswers.model_validate({**ANSWERS, 'investigations': investigations})
        try:
            tickets.write(Slug('retry-queue'), answers)
            return tickets.validate(Slug('retry-queue')).text
        except InvalidTicketError as error:
            return str(error)

    @pytest.mark.usefixtures('started_investigation')
    def test_slug_confinement_a_written_investigation_id_cannot_name_a_file_outside(
        self, project: Path, ticket_service: TicketService
    ) -> None:
        assert f'investigation {OUTSIDE} is not a valid id' in self.stage(ticket_service, [OUTSIDE])
        assert not workspace_at(project).ticket_file(Slug('retry-queue')).exists()

    @pytest.mark.usefixtures('started_investigation')
    def test_slug_confinement_a_hand_edited_investigation_id_cannot_name_a_file_outside(
        self, project: Path, ticket_service: TicketService
    ) -> None:
        self.stage(ticket_service, [])
        path = workspace_at(project).ticket_file(Slug('retry-queue'))
        text = path.read_text(encoding='utf-8')
        path.write_text(f'{text}  - "{OUTSIDE}"\n', encoding='utf-8')

        with pytest.raises(InvalidTicketError) as error:
            ticket_service.validate(Slug('retry-queue'))

        assert error.value.problems == [f'investigation {OUTSIDE} is not a valid id']

    def test_slug_confinement_a_valid_slug_writes_only_under_the_state_directory(
        self, project: Path, state_server: StateServer, git: GitRunner
    ) -> None:
        results = state_server.call(*self.RETRY_QUEUE_CALLS)

        written = {Path(name).parts[0] for name in tree(project)} - {'.git', 'outside.jsonl'}
        assert not any(result.is_error for result in results)
        assert written == {'.mightymodels'}
        assert git(project, 'status', '--porcelain') == '?? outside.jsonl\n'


@pytest.mark.usefixtures('project')
class TestReviewConfinement:
    @pytest.fixture
    def run_with_a_leaking_report(self, project: Path, state_server: StateServer) -> str:
        (started,) = state_server.call(
            ('review', {'request': {'action': 'start', 'payload': START_PAYLOAD}})
        )
        run = started.structured_content['run_id']
        report = project.joinpath('.mightymodels', '.runtime', 'reviews', run)
        report.joinpath('UNCLE-BOB-REPORT.md').write_text(LEAKING_REPORT, encoding='utf-8')
        return run

    @pytest.mark.parametrize('raw', HOSTILE)
    def test_slug_confinement_review_start_reads_and_writes_nothing_for_a_hostile_slug(
        self,
        tmp_path: Path,
        connected_server: StateServer,
        tmp_path_tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
        raw: str,
    ) -> None:
        payload = {**START_PAYLOAD, 'scope': 'ticket', 'base': 'main', 'slug': raw}
        (result,) = connected_server.call(
            ('review', {'request': {'action': 'start', 'payload': payload}})
        )

        assert result.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert tree(tmp_path) == tmp_path_tree_after_the_connect

    @pytest.mark.parametrize('raw', HOSTILE_RUN_IDS)
    @pytest.mark.parametrize('arguments', RUN_CALLS)
    def test_slug_confinement_a_path_shaped_run_id_reads_and_writes_nothing(
        self,
        tmp_path: Path,
        connected_server: StateServer,
        tmp_path_tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
        *,
        arguments: dict[str, object],
        raw: str,
    ) -> None:
        (result,) = connected_server.call(('review', {'request': {**arguments, 'run_id': raw}}))

        assert result.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert tree(tmp_path) == tmp_path_tree_after_the_connect

    @pytest.mark.parametrize('arguments', RUN_CALLS)
    def test_slug_confinement_a_run_id_holding_a_non_ascii_digit_reads_and_writes_nothing(
        self,
        tmp_path: Path,
        connected_server: StateServer,
        tmp_path_tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
        arguments: dict[str, object],
    ) -> None:
        call: ToolCall = ('review', {'request': {**arguments, 'run_id': NON_ASCII_DIGIT_RUN_ID}})
        (result,) = connected_server.call(call)

        assert result.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert tree(tmp_path) == tmp_path_tree_after_the_connect

    @pytest.mark.parametrize('arguments', NON_ASCII_DIGIT_FINDING_CALLS)
    def test_slug_confinement_a_finding_id_holding_a_non_ascii_digit_reads_and_writes_nothing(
        self,
        tmp_path: Path,
        connected_server: StateServer,
        tmp_path_tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
        arguments: dict[str, object],
    ) -> None:
        call: ToolCall = ('review', {'request': {**arguments, 'run_id': WELL_FORMED_RUN_ID}})
        (result,) = connected_server.call(call)

        assert result.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert tree(tmp_path) == tmp_path_tree_after_the_connect

    def test_slug_confinement_a_run_without_a_ticket_keeps_its_directory_under_runtime(
        self, project: Path, state_server: StateServer
    ) -> None:
        (result,) = state_server.call(
            ('review', {'request': {'action': 'start', 'payload': START_PAYLOAD}})
        )

        run = result.structured_content['run_id']
        state = project.joinpath('.mightymodels')
        assert not result.is_error
        assert state.joinpath('.runtime', 'reviews', run).is_dir()
        assert {path.name for path in state.iterdir()} == {'.runtime'}

    def test_slug_confinement_a_run_with_a_ticket_keeps_its_directory_under_the_ticket(
        self, project: Path, state_server: StateServer
    ) -> None:
        payload = {**START_PAYLOAD, 'scope': 'ticket', 'base': 'main', 'slug': 'retry-queue'}
        (result,) = state_server.call(
            ('review', {'request': {'action': 'start', 'payload': payload}})
        )

        run = result.structured_content['run_id']
        state = project.joinpath('.mightymodels')
        assert not result.is_error
        assert state.joinpath('retry-queue', 'review', run).is_dir()
        assert {path.name for path in state.iterdir()} == {'retry-queue'}

    def test_slug_confinement_a_report_with_secrets_is_redacted_in_the_stored_rows(
        self,
        run_with_a_leaking_report: str,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        (added,) = state_server.call(
            (
                'review',
                {
                    'request': {
                        'action': 'add',
                        'run_id': run_with_a_leaking_report,
                        'payload': {'persona': 'uncle-bob'},
                    }
                },
            )
        )

        with repository_database.transaction() as session:
            rows = session.scalars(sql.select(ReviewFindingRow)).all()
            stored = ' '.join(
                str(getattr(row, column.name)) for row in rows for column in row.__table__.columns
            )
        assert not added.is_error
        assert 'hunter22' not in stored
        assert 'ghp_' not in stored
        assert 'Hardcoded [REDACTED:assignment] in the store' in stored
