"""The `close` tool: each handler takes its action's request and asks the close service.

`check` takes the ticket only. `close` also takes the closing, what the user says the ticket
shipped, and the schema refuses a `close` without it.

`ResolvedClosings` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels.tools.close.schema import (
    CheckClose,
    CloseAction,
    CloseClose,
    CloseRequest,
    CloseView,
)
from mightymodels.tools.close.service import CloseService
from mightymodels.tools.protocol import (
    ActionHandler,
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)


def check_live_work(closings: CloseService, request: CheckClose) -> CloseView:
    return closings.check(request.slug)


def close_ticket(closings: CloseService, request: CloseClose) -> CloseView:
    return closings.close(request.slug, request.closing)


def lifespan_closings(ctx: Context[ServedState]) -> CloseService:
    return served_services(ctx).closings


ResolvedClosings = Annotated[CloseService, Resolve(lifespan_closings)]


@dataclass(slots=True, kw_only=True, frozen=True)
class CloseTool:
    handlers: Mapping[CloseAction, ServiceHandler[CloseService, CloseRequest, CloseView]]

    def close(self, request: CloseRequest, *, closings: ResolvedClosings) -> CloseView:
        """List live work that blocks closing, or close the ticket and return the archive text."""
        return dispatch_to_service(self.handlers, request.action, request, service=closings)


close_tool = CloseTool(
    handlers=MappingProxyType(
        {
            CloseAction.CHECK: ActionHandler(variant=CheckClose, handle=check_live_work),
            CloseAction.CLOSE: ActionHandler(variant=CloseClose, handle=close_ticket),
        }
    )
)
close_action_tool: ActionTool[CloseAction, CloseService, CloseRequest, CloseView] = close_tool
