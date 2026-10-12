"""A stuck engineer's failed fixes: recorded per task, three accepted, the fourth refused."""

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mightymodels_plugin.core.declarative import PROSE_LIMIT
from mightymodels_plugin.core.edge import exclude_state_from_git
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.core.workspace import git_at, workspace_at
from mightymodels_plugin.redaction import RedactedTextTooLongError
from mightymodels_plugin.tools.failed_fix.schema import (
    FailedFixAction,
    FailedFixPayload,
    FailedFixRequest,
    TaskFailedFix,
)
from mightymodels_plugin.tools.failed_fix.tool import failed_fix_tool
from mightymodels_plugin.tools.task.errors import FixesSpentError, FixNotUnderwayError
from mightymodels_plugin.tools.task.repository import FAILED_FIX_LIMIT, task_store
from mightymodels_plugin.tools.task.schema import Implementer, Status, TaskStart, TaskView
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.tests.support import (
    StateServer,
    text_of,
    workspace_database,
)
from mightymodels_plugin.tools.ticket.repository import ticket_store
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

TICKET = Slug('retry-queue')
OTHER_TICKET = Slug('drain-loop')
HYPOTHESES = ('the sleep is in the drain loop', 'the batch size is zero', 'the lock is held')
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': 'fix/retry-queue',
        'context': ['drain loop sleeps between batches'],
    }
)
START = TaskStart(by=Implementer.ENGINEER, owned=('src/queue.py',), acceptance=('AC-1',))
CREDENTIALS = '://user:hunter2@'
REDACTED_CREDENTIALS = '://[REDACTED:url-credentials]@'


def record(tasks: TaskService, slug: Slug, task_id: str, hypothesis: str) -> TaskView:
    payload = FailedFixPayload(task_id=task_id, change=TaskFailedFix(hypothesis=hypothesis))
    request = FailedFixRequest(action=FailedFixAction.RECORD, slug=slug, payload=payload)
    return failed_fix_tool.failed_fix(request, tasks=tasks)


def tried(tasks: TaskService, slug: Slug, task_id: str) -> list[str]:
    with tasks.store.transaction() as repository:
        return repository.failed_fixes(slug, task_id)


def stage_and_start(tickets: TicketService, tasks: TaskService, slug: Slug, *task_ids: str) -> None:
    tickets.write(slug, ANSWERS)
    tickets.validate(slug)
    for task_id in task_ids:
        tasks.start(slug, task_id, START)


@dataclass(slots=True, kw_only=True, frozen=True)
class AnotherRepository:
    tasks: TaskService
    tickets: TicketService


@pytest.fixture
def started(ticket_service: TicketService, task_service: TaskService) -> TaskService:
    stage_and_start(ticket_service, task_service, TICKET, 'T1', 'T2')
    stage_and_start(ticket_service, task_service, OTHER_TICKET, 'T1')
    return task_service


@pytest.fixture
def three_failed(started: TaskService) -> TaskService:
    for hypothesis in HYPOTHESES:
        record(started, TICKET, 'T1', hypothesis)
    return started


@pytest.fixture
def another_repository(
    tmp_path: Path, data_directory: Path, git: GitRunner
) -> Generator[AnotherRepository]:
    root = tmp_path.joinpath('another')
    root.mkdir()
    git(root, 'init', '--quiet')
    queries = git_at(root)
    exclude_state_from_git(queries)
    workspace = workspace_at(root)
    with workspace_database(workspace, data_directory) as database:
        yield AnotherRepository(
            tasks=TaskService(workspace=workspace, store=task_store(database), git=queries),
            tickets=TicketService(workspace=workspace, store=ticket_store(database), git=queries),
        )


class TestAFailedFix:
    def test_is_recorded_with_the_hypothesis_it_tested(self, started: TaskService) -> None:
        view = record(started, TICKET, 'T1', HYPOTHESES[0])

        assert tried(started, TICKET, 'T1') == [HYPOTHESES[0]]
        assert HYPOTHESES[0] in view.text
        assert [record.status for record in view.tasks] == [Status.IN_PROGRESS]

    def test_says_how_many_fixes_are_left(self, started: TaskService) -> None:
        record(started, TICKET, 'T1', HYPOTHESES[0])
        view = record(started, TICKET, 'T1', HYPOTHESES[1])

        assert view.text.splitlines()[0].startswith('T1 failed fix 2 recorded')
        assert view.text.splitlines()[1] == '1 left'

    def test_is_refused_on_a_task_that_is_not_in_progress(self, started: TaskService) -> None:
        with pytest.raises(ToolError) as refused:
            record(started, TICKET, 'T9', HYPOTHESES[0])

        assert isinstance(refused.value.__cause__, FixNotUnderwayError)
        assert (refused.value.__cause__.task_id, refused.value.__cause__.current) == (
            'T9',
            Status.PENDING,
        )
        assert tried(started, TICKET, 'T9') == []


class TestThreeFailedFixesOfOneTask:
    def test_are_all_accepted_in_order(self, three_failed: TaskService) -> None:
        assert len(HYPOTHESES) == FAILED_FIX_LIMIT
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)


class TestAFourthFailedFix:
    @pytest.fixture
    def refusal(self, three_failed: TaskService) -> FixesSpentError:
        with pytest.raises(ToolError) as refused:
            record(three_failed, TICKET, 'T1', 'a fourth idea')
        assert isinstance(refused.value.__cause__, FixesSpentError)
        return refused.value.__cause__

    def test_is_refused_with_the_three_hypotheses_in_order(self, refusal: FixesSpentError) -> None:
        assert refusal.tried == HYPOTHESES
        assert str(refusal).startswith('T1 is blocked')
        positions = [str(refusal).index(hypothesis) for hypothesis in HYPOTHESES]
        assert positions == sorted(positions)

    def test_stores_nothing(self, three_failed: TaskService, refusal: FixesSpentError) -> None:
        assert refusal.task_id == 'T1'
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)

    def test_is_answered_by_the_tool_as_an_error_and_not_a_traceback(
        self, three_failed: TaskService, connected_server: StateServer
    ) -> None:
        arguments: dict[str, object] = {
            'action': 'record',
            'slug': TICKET.root,
            'payload': {'task_id': 'T1', 'change': {'hypothesis': 'a fourth idea'}},
        }

        (result,) = connected_server.call(('failed_fix', {'request': arguments}))

        text = text_of(result)
        assert result.is_error
        assert 'T1 is blocked' in text
        assert [text.index(hypothesis) for hypothesis in HYPOTHESES] == sorted(
            text.index(hypothesis) for hypothesis in HYPOTHESES
        )
        assert 'Traceback' not in text
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)


class TestTheCount:
    def test_of_another_task_starts_at_zero(self, three_failed: TaskService) -> None:
        record(three_failed, TICKET, 'T2', 'another task, first idea')

        assert tried(three_failed, TICKET, 'T2') == ['another task, first idea']

    def test_of_another_ticket_starts_at_zero(self, three_failed: TaskService) -> None:
        record(three_failed, OTHER_TICKET, 'T1', 'another ticket, first idea')

        assert tried(three_failed, OTHER_TICKET, 'T1') == ['another ticket, first idea']
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)

    def test_of_another_repository_key_starts_at_zero(
        self, three_failed: TaskService, another_repository: AnotherRepository
    ) -> None:
        stage_and_start(another_repository.tickets, another_repository.tasks, TICKET, 'T1')

        record(another_repository.tasks, TICKET, 'T1', 'other key, first idea')

        assert tried(another_repository.tasks, TICKET, 'T1') == ['other key, first idea']
        assert tried(three_failed, TICKET, 'T1') == list(HYPOTHESES)


class TestTheHypothesis:
    def test_is_redacted_before_it_is_stored(self, started: TaskService) -> None:
        record(started, TICKET, 'T1', f'the config holds {CREDENTIALS}')

        (stored,) = tried(started, TICKET, 'T1')
        assert REDACTED_CREDENTIALS in stored
        assert 'hunter2' not in stored

    def test_is_refused_when_redaction_lengthens_it_past_its_column(
        self, started: TaskService
    ) -> None:
        hypothesis = 'x' * (PROSE_LIMIT - len(CREDENTIALS)) + CREDENTIALS

        with pytest.raises(ToolError) as refused:
            record(started, TICKET, 'T1', hypothesis)

        assert isinstance(refused.value.__cause__, RedactedTextTooLongError)
        assert refused.value.__cause__.field == 'hypothesis'
        assert tried(started, TICKET, 'T1') == []


class TestTheTaskTool:
    def test_refuses_the_old_action_as_unknown_and_stores_nothing(
        self, started: TaskService, connected_server: StateServer
    ) -> None:
        arguments: dict[str, object] = {
            'action': 'record-failed-fix',
            'slug': TICKET.root,
            'payload': {'task_id': 'T1', 'change': {'hypothesis': HYPOTHESES[0]}},
        }

        (result,) = connected_server.call(('task', {'request': arguments}))

        assert result.is_error
        assert 'record-failed-fix' in text_of(result)
        assert tried(started, TICKET, 'T1') == []
