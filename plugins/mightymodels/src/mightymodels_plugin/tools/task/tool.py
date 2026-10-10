"""The `task` tool: each handler checks the call's arguments and asks the task service.

`ResolvedTasks` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.task.schema import (
    TaskAction,
    TaskMark,
    TaskPayload,
    TaskStart,
    TaskVerification,
    TaskView,
)
from mightymodels_plugin.tools.task.service import TaskService


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskCall:
    slug: Slug
    payload: TaskPayload


def start_task(tasks: TaskService, call: TaskCall) -> TaskView:
    if call.payload.task_id is None or not isinstance(call.payload.change, TaskStart):
        raise MissingArgumentsError(TaskAction.START, 'task_id and a change holding by and owned')
    return tasks.start(call.slug, call.payload.task_id, call.payload.change)


def verify_task(tasks: TaskService, call: TaskCall) -> TaskView:
    if call.payload.task_id is None or not isinstance(call.payload.change, TaskVerification):
        raise MissingArgumentsError(TaskAction.VERIFY, 'task_id and a change holding commit')
    return tasks.verify(call.slug, call.payload.task_id, call.payload.change)


def mark_task(tasks: TaskService, call: TaskCall) -> TaskView:
    if call.payload.task_id is None or not isinstance(call.payload.change, TaskMark):
        raise MissingArgumentsError(TaskAction.MARK, 'task_id and a change holding to and reason')
    return tasks.mark(call.slug, call.payload.task_id, call.payload.change)


def show_tasks(tasks: TaskService, call: TaskCall) -> TaskView:
    return tasks.show(call.slug)


def gate_readiness(tasks: TaskService, call: TaskCall) -> TaskView:
    return tasks.ready(call.slug)


def lifespan_tasks(ctx: Context[ServedState]) -> TaskService:
    return served_services(ctx).tasks


ResolvedTasks = Annotated[TaskService, Resolve(lifespan_tasks)]


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskTool:
    handlers: Mapping[TaskAction, ServiceHandler[TaskService, TaskCall, TaskView]]

    def task(
        self,
        action: TaskAction,
        slug: Slug,
        payload: TaskPayload | None = None,
        *,
        tasks: ResolvedTasks,
    ) -> TaskView:
        """Start, mark, verify or list tasks, and gate the ticket on readiness."""
        call = TaskCall(slug=slug, payload=TaskPayload() if payload is None else payload)
        return dispatch_to_service(self.handlers, action, call, service=tasks)


task_tool = TaskTool(
    handlers=MappingProxyType(
        {
            TaskAction.START: start_task,
            TaskAction.VERIFY: verify_task,
            TaskAction.MARK: mark_task,
            TaskAction.SHOW: show_tasks,
            TaskAction.READY: gate_readiness,
        }
    )
)
task_action_tool: ActionTool[TaskAction, TaskService, TaskCall, TaskView] = task_tool
