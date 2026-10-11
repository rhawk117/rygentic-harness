"""The `crashout` tool: each handler takes its action's request and asks the crashout service.

`add` takes the crashout to journal, and the schema refuses an `add` without it. `stats` and
`last` take nothing.

`ResolvedCrashouts` is a plain assignment because the SDK does not see a `Resolve` marker behind
a PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.tools.crashout.schema import (
    AddCrashout,
    CrashoutAction,
    CrashoutRequest,
    CrashoutView,
    LastCrashout,
    StatsCrashout,
)
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.protocol import (
    ActionHandler,
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)


def journal_crashout(crashouts: CrashoutService, request: AddCrashout) -> CrashoutView:
    return crashouts.add(request.entry)


def report_patterns(crashouts: CrashoutService, _request: StatsCrashout) -> CrashoutView:
    return crashouts.stats()


def show_last_crashout(crashouts: CrashoutService, _request: LastCrashout) -> CrashoutView:
    return crashouts.last()


def lifespan_crashouts(ctx: Context[ServedState]) -> CrashoutService:
    return served_services(ctx).crashouts


ResolvedCrashouts = Annotated[CrashoutService, Resolve(lifespan_crashouts)]


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutTool:
    handlers: Mapping[
        CrashoutAction, ServiceHandler[CrashoutService, CrashoutRequest, CrashoutView]
    ]

    def crashout(self, request: CrashoutRequest, *, crashouts: ResolvedCrashouts) -> CrashoutView:
        """Journal a crashout, or report recurring patterns."""
        return dispatch_to_service(self.handlers, request.action, request, service=crashouts)


crashout_tool = CrashoutTool(
    handlers=MappingProxyType(
        {
            CrashoutAction.ADD: ActionHandler(variant=AddCrashout, handle=journal_crashout),
            CrashoutAction.STATS: ActionHandler(variant=StatsCrashout, handle=report_patterns),
            CrashoutAction.LAST: ActionHandler(variant=LastCrashout, handle=show_last_crashout),
        }
    )
)
crashout_action_tool: ActionTool[CrashoutAction, CrashoutService, CrashoutRequest, CrashoutView] = (
    crashout_tool
)
