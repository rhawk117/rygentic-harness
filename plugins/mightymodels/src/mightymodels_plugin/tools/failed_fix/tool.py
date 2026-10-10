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

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.failed_fix.schema import FailedFixAction, FailedFixPayload
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.task.schema import TaskView
from mightymodels_plugin.tools.task.service import TaskService


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedFixCall:
    slug: Slug
    payload: FailedFixPayload


def record_failed_fix(tasks: TaskService, call: FailedFixCall) -> TaskView:
    return tasks.record_failed_fix(call.slug, call.payload.task_id, call.payload.change)


def lifespan_tasks(ctx: Context[ServedState]) -> TaskService:
    return served_services(ctx).tasks


ResolvedTasks = Annotated[TaskService, Resolve(lifespan_tasks)]


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedFixTool:
    handlers: Mapping[FailedFixAction, ServiceHandler[TaskService, FailedFixCall, TaskView]]

    def failed_fix(
        self,
        action: FailedFixAction,
        slug: Slug,
        payload: FailedFixPayload,
        *,
        tasks: ResolvedTasks,
    ) -> TaskView:
        """Record a fix that failed, with the hypothesis it tested; the fourth is refused."""
        call = FailedFixCall(slug=slug, payload=payload)
        return dispatch_to_service(self.handlers, action, call, service=tasks)


failed_fix_tool = FailedFixTool(
    handlers=MappingProxyType({FailedFixAction.RECORD: record_failed_fix})
)
failed_fix_action_tool: ActionTool[FailedFixAction, TaskService, FailedFixCall, TaskView] = (
    failed_fix_tool
)
