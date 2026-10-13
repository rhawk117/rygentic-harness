"""The `task` tool: each handler takes its action's request and asks the task service.

`ResolvedTasks` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.tools.protocol import (
    ActionHandler,
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.task.schema import (
    MarkTask,
    ReadyTask,
    ShowTask,
    StartTask,
    TaskAction,
    TaskRequest,
    TaskView,
    VerifyTask,
)
from mightymodels_plugin.tools.task.service import TaskService


def start_task(tasks: TaskService, request: StartTask) -> TaskView:
    return tasks.start(request.slug, request.payload.task_id, request.payload.change)


def verify_task(tasks: TaskService, request: VerifyTask) -> TaskView:
    return tasks.verify(request.slug, request.payload.task_id, request.payload.change)


def mark_task(tasks: TaskService, request: MarkTask) -> TaskView:
    return tasks.mark(request.slug, request.payload.task_id, request.payload.change)


def show_tasks(tasks: TaskService, request: ShowTask) -> TaskView:
    return tasks.show(request.slug)


def gate_readiness(tasks: TaskService, request: ReadyTask) -> TaskView:
    return tasks.ready(request.slug)


def lifespan_tasks(ctx: Context[ServedState]) -> TaskService:
    return served_services(ctx).tasks


ResolvedTasks = Annotated[TaskService, Resolve(lifespan_tasks)]


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskTool:
    handlers: Mapping[TaskAction, ServiceHandler[TaskService, TaskRequest, TaskView]]

    def task(self, request: TaskRequest, *, tasks: ResolvedTasks) -> TaskView:
        """Start, mark, verify or list tasks, and gate the ticket on readiness."""
        return dispatch_to_service(self.handlers, request.action, request, service=tasks)


task_tool = TaskTool(
    handlers=MappingProxyType(
        {
            TaskAction.START: ActionHandler(variant=StartTask, handle=start_task),
            TaskAction.VERIFY: ActionHandler(variant=VerifyTask, handle=verify_task),
            TaskAction.MARK: ActionHandler(variant=MarkTask, handle=mark_task),
            TaskAction.SHOW: ActionHandler(variant=ShowTask, handle=show_tasks),
            TaskAction.READY: ActionHandler(variant=ReadyTask, handle=gate_readiness),
        }
    )
)
task_action_tool: ActionTool[TaskAction, TaskService, TaskRequest, TaskView] = task_tool
