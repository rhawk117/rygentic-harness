from enum import StrEnum
from pathlib import Path
from typing import get_args, get_type_hints

import pytest
from mcp.types import CallToolResult
from mightymodels_plugin.core.database import DATABASE_NAME
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.server import SERVER_NAME, TOOLS, AppState
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.protocol import ActionTool, LifespanState, MisroutedRequestError
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.similarity.service import SimilarityService
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.tools.task.schema import ReadyTask, ShowTask, TaskAction, TaskStart
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.task.tool import task_tool
from mightymodels_plugin.tools.tests.support import (
    ActivityKind,
    DatabaseActivity,
    StateServer,
    ToolCall,
    text_of,
    tree,
)
from mightymodels_plugin.tools.tests.tool_names import TOOL_NAMES
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

SLUG = 'retry-queue'
ANSWERS = {
    'summary': 'Retry queue drains slowly',
    'scope': 'large',
    'compaction': True,
    'branch': 'fix/retry-queue',
    'context': ['drain loop sleeps between batches'],
}
COMMAND = {'id': 'T1.AC-1', 'argv': ['true'], 'approved_by': 'user'}
START = {'by': 'engineer', 'owned': ['src/queue.py']}
FAILED_FIX: dict[str, object] = {
    'action': 'record',
    'slug': SLUG,
    'payload': {'task_id': 'T1', 'change': {'hypothesis': 'the drain loop sleeps'}},
}


def ticket_results(server: StateServer, *calls: ToolCall) -> list[CallToolResult]:
    requests: list[ToolCall] = [
        (name, {'request': {'slug': SLUG, **arguments}}) for name, arguments in calls
    ]
    return server.call(*requests)


def served_actions(tool: object) -> type[StrEnum]:
    return get_args(get_type_hints(type(tool))['handlers'])[0]


class TestStateServer:
    def test_is_named_state(self, state_server: StateServer) -> None:
        assert state_server.name() == SERVER_NAME == 'state'

    def test_lists_its_tools_through_the_in_memory_client(self, state_server: StateServer) -> None:
        assert sorted(state_server.tools()) == TOOL_NAMES

    @pytest.mark.parametrize('name', TOOL_NAMES)
    def test_each_tool_takes_the_arguments_the_surface_gives_it(
        self, name: str, state_server: StateServer
    ) -> None:
        schema = state_server.tools()[name].input_schema

        assert list(schema['properties']) == ['request']
        assert schema['required'] == ['request']

    def test_review_offers_the_eight_actions(self, state_server: StateServer) -> None:
        schema = state_server.tools()['review'].input_schema

        assert list(schema['$defs']['ReviewRequest']['discriminator']['mapping']) == [
            'add',
            'dispose',
            'gate',
            'list',
            'override',
            'report',
            'resolve',
            'start',
        ]

    def test_each_tool_is_described_by_its_docstring(self, state_server: StateServer) -> None:
        listed = state_server.tools()

        assert {name: tool.description for name, tool in listed.items()} == {
            tool.__name__: tool.__doc__ for tool in TOOLS
        }


class TestToolProtocol:
    @pytest.fixture
    def app_state(
        self,
        ticket_service: TicketService,
        task_service: TaskService,
        contract_service: ContractService,
        review_service: ReviewService,
        snapshot_service: SnapshotService,
        close_service: CloseService,
        investigation_service: InvestigationService,
        crashout_service: CrashoutService,
        similarity_service: SimilarityService,
    ) -> AppState:
        return AppState(
            tickets=ticket_service,
            tasks=task_service,
            contracts=contract_service,
            reviews=review_service,
            snapshots=snapshot_service,
            closings=close_service,
            investigations=investigation_service,
            crashouts=crashout_service,
            similarity=similarity_service,
        )

    @pytest.mark.parametrize(
        'tool', [pytest.param(tool.__self__, id=tool.__name__) for tool in TOOLS]
    )
    def test_each_registered_tool_satisfies_the_action_tool_protocol(self, tool: object) -> None:
        assert isinstance(tool, ActionTool)

    @pytest.mark.parametrize(
        ('tool', 'actions'),
        [
            pytest.param(tool.__self__, served_actions(tool.__self__), id=tool.__name__)
            for tool in TOOLS
        ],
    )
    def test_each_tool_handlers_cover_its_whole_action_enum(
        self, tool: ActionTool[StrEnum, object, object, object], actions: type[StrEnum]
    ) -> None:
        assert set(tool.handlers) == set(actions)

    def test_a_request_routed_to_the_handler_of_another_action_is_refused(
        self, task_service: TaskService
    ) -> None:
        ready = ReadyTask(action=TaskAction.READY, slug=Slug(SLUG))

        with pytest.raises(MisroutedRequestError) as refused:
            task_tool.handlers[TaskAction.SHOW](task_service, ready)

        assert (refused.value.variant, refused.value.request) == (ShowTask, ready)
        assert str(refused.value) == 'a ReadyTask request was routed to the handler of ShowTask'

    def test_the_lifespan_state_satisfies_what_the_tools_resolve(self, app_state: AppState) -> None:
        assert isinstance(app_state, LifespanState)


class TestLifespanState:
    @pytest.fixture
    def activity_of_a_file_write_and_two_database_calls(
        self, state_server: StateServer, database_activity: DatabaseActivity
    ) -> DatabaseActivity:
        ticket_results(
            state_server,
            ('ticket', {'action': 'write', 'fields': ANSWERS}),
            ('ticket', {'action': 'validate'}),
            ('ticket', {'action': 'show'}),
        )
        return database_activity

    def test_one_engine_serves_every_call_and_is_disposed_when_the_client_closes(
        self, activity_of_a_file_write_and_two_database_calls: DatabaseActivity
    ) -> None:
        assert activity_of_a_file_write_and_two_database_calls.kinds() == [
            ActivityKind.TRANSACTION_OPENED,
            ActivityKind.TRANSACTION_OPENED,
            ActivityKind.ENGINE_DISPOSED,
        ]
        assert len(activity_of_a_file_write_and_two_database_calls.engines()) == 1


class TestOutsideARepository:
    @pytest.fixture
    def state_server(self, tmp_path: Path, data_directory: Path) -> StateServer:
        directory = tmp_path.joinpath('plain-directory')
        directory.mkdir()
        return StateServer(root=directory, data_directory=data_directory)

    def test_the_server_lists_its_tools_and_refuses_a_ticket_naming_the_missing_repository(
        self, state_server: StateServer
    ) -> None:
        listed = state_server.tools()
        written, shown = ticket_results(
            state_server,
            ('ticket', {'action': 'write', 'fields': ANSWERS}),
            ('ticket', {'action': 'show'}),
        )

        assert sorted(listed) == TOOL_NAMES
        assert (written.is_error, shown.is_error) == (True, True)
        assert f'{state_server.root} is not inside a git repository' in text_of(written)
        assert tree(state_server.root) == {}


class TestADatabaseFileThatIsNotADatabase:
    CONTENT = b'these bytes are not a database ' * 64
    CAUSE = 'file is not a database'

    @pytest.fixture
    def not_a_database(self, data_directory: Path) -> Path:
        data_directory.mkdir()
        database_file = data_directory.joinpath(DATABASE_NAME)
        database_file.write_bytes(self.CONTENT)
        return database_file

    def test_the_server_lists_its_tools_and_refuses_a_ticket_naming_the_file_and_the_cause(
        self, state_server: StateServer, not_a_database: Path
    ) -> None:
        listed = state_server.tools()
        (shown,) = ticket_results(state_server, ('ticket', {'action': 'show'}))

        assert sorted(listed) == TOOL_NAMES
        assert shown.is_error
        assert f'{not_a_database} could not be opened' in text_of(shown)
        assert self.CAUSE in text_of(shown)


class TestToolCalls:
    ONE_CALL_OF_EACH_TOOL: tuple[ToolCall, ...] = (
        ('ticket', {'action': 'show', 'slug': SLUG}),
        ('task', {'action': 'show', 'slug': SLUG}),
        ('contract', {'action': 'status', 'slug': SLUG}),
        ('review', {'action': 'list'}),
        ('snapshot', {'slug': SLUG}),
        ('close', {'action': 'check', 'slug': SLUG}),
        ('investigation', {'action': 'list'}),
        ('crashout', {'action': 'stats'}),
        ('similarity', {'action': 'search', 'query': 'the drain loop'}),
        ('failed_fix', FAILED_FIX),
    )

    @pytest.fixture
    def server_with_a_started_task(
        self, state_server: StateServer, ticket_service: TicketService, task_service: TaskService
    ) -> StateServer:
        ticket_service.write(Slug(SLUG), TicketAnswers.model_validate(ANSWERS))
        ticket_service.validate(Slug(SLUG))
        task_service.start(Slug(SLUG), 'T1', TaskStart.model_validate(START))
        return state_server

    def test_each_tool_answers_one_call(self, server_with_a_started_task: StateServer) -> None:
        requests: list[ToolCall] = [
            (name, {'request': arguments}) for name, arguments in self.ONE_CALL_OF_EACH_TOOL
        ]
        results = server_with_a_started_task.call(*requests)

        assert [name for name, _ in self.ONE_CALL_OF_EACH_TOOL] == [tool.__name__ for tool in TOOLS]
        assert [result.is_error for result in results] == [False] * len(TOOLS)
        assert all(result.structured_content for result in results)

    def test_a_ticket_is_written_validated_and_read_back(self, state_server: StateServer) -> None:
        written, validated, shown = ticket_results(
            state_server,
            ('ticket', {'action': 'write', 'fields': ANSWERS}),
            ('ticket', {'action': 'validate'}),
            ('ticket', {'action': 'show'}),
        )

        assert state_server.root.joinpath('.mightymodels', SLUG, 'ticket.yml').is_file()
        assert written.structured_content == {
            'text': f'wrote .mightymodels/{SLUG}/ticket.yml; review it, then run validate\n',
            'unit': None,
        }
        assert validated.structured_content['unit']['ticket']['models']['architect'] == 'opus'
        assert shown.structured_content['unit'] == validated.structured_content['unit']

    def test_a_staged_ticket_takes_a_contract_and_a_task(self, state_server: StateServer) -> None:
        *_, approved, started, ready, status = ticket_results(
            state_server,
            ('ticket', {'action': 'write', 'fields': ANSWERS}),
            ('ticket', {'action': 'validate'}),
            ('contract', {'action': 'approve', 'commands': [COMMAND]}),
            ('task', {'action': 'start', 'payload': {'task_id': 'T1', 'change': START}}),
            ('task', {'action': 'ready'}),
            ('contract', {'action': 'status'}),
        )

        assert approved.structured_content['text'] == 'contract: 1 commands (1 new)\n'
        assert started.structured_content['tasks'][0]['attempts'] == {'engineer': 1}
        assert (ready.is_error, ready.structured_content['advanced']) == (False, False)
        assert status.structured_content['commands'] == [
            {'id': 'T1.AC-1', 'argv': ['true'], 'state': 'never-run'}
        ]

    def test_a_staged_ticket_gives_its_snapshot_and_its_live_work(
        self, state_server: StateServer
    ) -> None:
        *_, snapshot, checked, closed = ticket_results(
            state_server,
            ('ticket', {'action': 'write', 'fields': ANSWERS}),
            ('ticket', {'action': 'validate'}),
            ('snapshot', {'limit': 5}),
            ('close', {'action': 'check'}),
            ('close', {'action': 'close', 'closing': {'shipped': 'the queue drains'}}),
        )

        assert snapshot.structured_content['record']['ticket']['status'] == 'staged'
        assert snapshot.structured_content['record_path'] == (
            f'.mightymodels/{SLUG}/handoffs/snapshot.json'
        )
        assert checked.structured_content == {
            'text': 'live work remains\n  - no verified task work is recorded\n',
            'blocked': True,
            'blockers': ['no verified task work is recorded'],
            'archive': None,
        }
        assert (closed.is_error, closed.structured_content['blocked']) == (False, True)

    @pytest.mark.parametrize(
        ('name', 'arguments'),
        [
            pytest.param('snapshot', {}, id='snapshot'),
            pytest.param('close', {'action': 'check'}, id='close-check'),
        ],
    )
    def test_an_unstaged_ticket_is_refused_by_the_tools_that_read_it(
        self, name: str, arguments: dict[str, object], state_server: StateServer
    ) -> None:
        (result,) = ticket_results(state_server, (name, arguments))

        assert result.is_error
        assert f'{SLUG} is not staged; stage the ticket with open-ticket first' in text_of(result)

    def test_an_anticipated_failure_reaches_the_model_as_its_own_text(
        self, state_server: StateServer
    ) -> None:
        (shown,) = ticket_results(state_server, ('ticket', {'action': 'show'}))

        assert shown.is_error
        assert f'{SLUG} is not staged; stage the ticket with open-ticket first' in text_of(shown)

    @pytest.mark.parametrize(
        ('name', 'arguments', 'needs'),
        [
            pytest.param(
                'ticket', {'action': 'write'}, 'request.write.fields\n  Field required', id='write'
            ),
            pytest.param(
                'ticket',
                {'action': 'update-context', 'fields': ANSWERS},
                'request.update-context.fields.summary\n  Extra inputs are not permitted',
                id='update-context',
            ),
            pytest.param(
                'task',
                {'action': 'start', 'payload': {'task_id': 'T1'}},
                'request.start.payload.change\n  Field required',
                id='start',
            ),
            pytest.param(
                'task',
                {'action': 'verify', 'payload': {'change': START}},
                'request.verify.payload.task_id\n  Field required',
                id='verify',
            ),
            pytest.param(
                'task',
                {'action': 'mark', 'payload': {'task_id': 'T1'}},
                'request.mark.payload.change\n  Field required',
                id='mark',
            ),
            pytest.param(
                'contract',
                {'action': 'approve'},
                'request.approve.commands\n  Field required',
                id='approve',
            ),
            pytest.param(
                'close', {'action': 'close'}, 'request.close.closing\n  Field required', id='close'
            ),
        ],
    )
    def test_an_action_missing_its_arguments_says_what_it_needs(
        self, name: str, arguments: dict[str, object], needs: str, state_server: StateServer
    ) -> None:
        (result,) = ticket_results(state_server, (name, arguments))

        assert result.is_error
        assert needs in text_of(result)

    @pytest.mark.parametrize(
        ('name', 'arguments'),
        [
            pytest.param(
                'task',
                {'action': 'start', 'payload': {'task_id': 'X1', 'change': START}},
                id='task-id',
            ),
            pytest.param(
                'task',
                {
                    'action': 'mark',
                    'payload': {'task_id': 'T1', 'change': {'to': 'verified', 'reason': 'r'}},
                },
                id='mark-verified',
            ),
            pytest.param('ticket', {'action': 'delete'}, id='unknown-action'),
            pytest.param('snapshot', {'limit': 0}, id='snapshot-limit-zero'),
            pytest.param('snapshot', {'limit': 101}, id='snapshot-limit-over'),
            pytest.param('close', {'action': 'prune'}, id='close-unknown-action'),
            pytest.param(
                'close',
                {'action': 'close', 'closing': {'shipped': 's', 'confirm': True}},
                id='closing-unknown-field',
            ),
        ],
    )
    def test_arguments_outside_the_schema_are_refused(
        self,
        name: str,
        arguments: dict[str, object],
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (result,) = ticket_results(connected_server, (name, arguments))

        assert result.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert connected_server.files_on_disk() == tree_after_the_connect


class TestAnArgumentTheSchemaDoesNotName:
    UNNAMED_ARGUMENT = 'not_in_the_schema'
    ONE_CALL_OF_EACH_TOOL = TestToolCalls.ONE_CALL_OF_EACH_TOOL

    @pytest.mark.parametrize(
        ('name', 'arguments'),
        [pytest.param(name, arguments, id=name) for name, arguments in ONE_CALL_OF_EACH_TOOL],
    )
    def test_a_top_level_argument_the_schema_does_not_name_is_refused_by_name(
        self,
        name: str,
        arguments: dict[str, object],
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (result,) = connected_server.call(
            (name, {'request': arguments, self.UNNAMED_ARGUMENT: True})
        )

        assert result.is_error
        assert self.UNNAMED_ARGUMENT in text_of(result)
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert connected_server.files_on_disk() == tree_after_the_connect

    @pytest.mark.parametrize(
        ('name', 'arguments'),
        [pytest.param(name, arguments, id=name) for name, arguments in ONE_CALL_OF_EACH_TOOL],
    )
    def test_an_argument_inside_the_request_that_the_schema_does_not_name_is_refused_by_name(
        self,
        name: str,
        arguments: dict[str, object],
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (result,) = connected_server.call(
            (name, {'request': {**arguments, self.UNNAMED_ARGUMENT: True}})
        )

        assert result.is_error
        assert self.UNNAMED_ARGUMENT in text_of(result)
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert connected_server.files_on_disk() == tree_after_the_connect
