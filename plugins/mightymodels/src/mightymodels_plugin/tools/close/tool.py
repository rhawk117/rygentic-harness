"""The `close` tool: each handler checks the call's arguments and asks the close service.

`check` needs the ticket only. `close` also needs the closing, what the user says the ticket
shipped, and `close_ticket` is the one place that refuses a call without it.

`ResolvedClosings` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.close.schema import CloseAction, CloseView, Closing
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class CloseCall:
    slug: Slug
    closing: Closing | None


def check_live_work(closings: CloseService, call: CloseCall) -> CloseView:
    return closings.check(call.slug)


def close_ticket(closings: CloseService, call: CloseCall) -> CloseView:
    if call.closing is None:
        raise MissingArgumentsError(CloseAction.CLOSE, 'a closing holding shipped, pr and gotchas')
    return closings.close(call.slug, call.closing)


def lifespan_closings(ctx: Context[ServedState]) -> CloseService:
    return served_services(ctx).closings


ResolvedClosings = Annotated[CloseService, Resolve(lifespan_closings)]


@dataclass(slots=True, kw_only=True, frozen=True)
class CloseTool:
    handlers: Mapping[CloseAction, ServiceHandler[CloseService, CloseCall, CloseView]]

    def close(
        self,
        action: CloseAction,
        slug: Slug,
        closing: Closing | None = None,
        *,
        closings: ResolvedClosings,
    ) -> CloseView:
        """List live work that blocks closing, or close the ticket and return the archive text."""
        call = CloseCall(slug=slug, closing=closing)
        return dispatch_to_service(self.handlers, action, call, service=closings)


close_tool = CloseTool(
    handlers=MappingProxyType({CloseAction.CHECK: check_live_work, CloseAction.CLOSE: close_ticket})
)
close_action_tool: ActionTool[CloseAction, CloseService, CloseCall, CloseView] = close_tool
