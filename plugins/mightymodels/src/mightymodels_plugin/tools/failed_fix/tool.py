"""The `failed_fix` tool: records a fix that failed, through the task service that counts them.

It is a tool of its own so that an engineer, whose `tools:` names this one and not `task`, cannot
start, verify or mark a task. The count, its limit and its refusal stay in the task service.

`ResolvedTasks` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.tools.failed_fix.schema import FailedFixAction, FailedFixRequest
from mightymodels_plugin.tools.protocol import (
    ActionHandler,
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.task.schema import TaskView
from mightymodels_plugin.tools.task.service import TaskService


def record_failed_fix(tasks: TaskService, request: FailedFixRequest) -> TaskView:
    return tasks.record_failed_fix(request.slug, request.payload.task_id, request.payload.change)


def lifespan_tasks(ctx: Context[ServedState]) -> TaskService:
    return served_services(ctx).tasks


ResolvedTasks = Annotated[TaskService, Resolve(lifespan_tasks)]


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedFixTool:
    handlers: Mapping[FailedFixAction, ServiceHandler[TaskService, FailedFixRequest, TaskView]]

    def failed_fix(self, request: FailedFixRequest, *, tasks: ResolvedTasks) -> TaskView:
        """Record a fix that failed, with the hypothesis it tested; the fourth is refused."""
        return dispatch_to_service(self.handlers, request.action, request, service=tasks)


failed_fix_tool = FailedFixTool(
    handlers=MappingProxyType(
        {FailedFixAction.RECORD: ActionHandler(variant=FailedFixRequest, handle=record_failed_fix)}
    )
)
failed_fix_action_tool: ActionTool[FailedFixAction, TaskService, FailedFixRequest, TaskView] = (
    failed_fix_tool
)
