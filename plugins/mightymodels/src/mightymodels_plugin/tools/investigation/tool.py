"""The `investigation` tool: each handler takes its action's request and asks the service.

Every action but `start` and `list` works on one investigation, and the schema refuses a call
that names none. `knowns` reads the whole table when the call carries no filter.

`start` asks the user for the kind of target when the request leaves it out, through `AskedKind`.
`ServedInvestigation` holds the service and the answer, which a tool's argument limit leaves no
room to take as two parameters.

`ResolvedInvestigations` is a plain assignment because the SDK does not see a `Resolve` marker
behind a PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Annotated

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.tools.asking import chosen, needs_input_text
from mightymodels_plugin.tools.investigation.questions import AskedKind, KindAnswer, kind_question
from mightymodels_plugin.tools.investigation.schema import (
    AddInvestigation,
    InvestigationAction,
    InvestigationRequest,
    InvestigationStart,
    InvestigationView,
    KnownsFilter,
    KnownsInvestigation,
    ListInvestigation,
    RenderInvestigation,
    StartInvestigation,
)
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.protocol import (
    ActionHandler,
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationServed:
    investigations: InvestigationService
    asked: ElicitationResult[KindAnswer]


def start_investigation(
    served: InvestigationServed, request: StartInvestigation
) -> InvestigationView:
    target = request.payload.request
    kind = target.kind or chosen(served.asked)
    if kind is None:
        return InvestigationView(text=needs_input_text([kind_question(target.target)]))
    started = InvestigationStart(target=target.target, kind=kind)
    return served.investigations.start(started, started=datetime.now(tz=UTC))


def add_entries(served: InvestigationServed, request: AddInvestigation) -> InvestigationView:
    payload = request.payload
    return served.investigations.add(
        request.investigation_id, payload.request.round, payload.entries
    )


def render_ledger(served: InvestigationServed, request: RenderInvestigation) -> InvestigationView:
    return served.investigations.render(request.investigation_id)


def render_knowns(served: InvestigationServed, request: KnownsInvestigation) -> InvestigationView:
    selection = None if request.payload is None else request.payload.request
    return served.investigations.knowns(
        request.investigation_id, KnownsFilter() if selection is None else selection
    )


def list_investigations(
    served: InvestigationServed, _request: ListInvestigation
) -> InvestigationView:
    return served.investigations.listing()


def lifespan_investigations(ctx: Context[ServedState]) -> InvestigationService:
    return served_services(ctx).investigations


ResolvedInvestigations = Annotated[InvestigationService, Resolve(lifespan_investigations)]


def serve_investigations(
    investigations: ResolvedInvestigations, asked: AskedKind
) -> InvestigationServed:
    return InvestigationServed(investigations=investigations, asked=asked)


ServedInvestigation = Annotated[InvestigationServed, Resolve(serve_investigations)]


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationTool:
    handlers: Mapping[
        InvestigationAction,
        ServiceHandler[InvestigationServed, InvestigationRequest, InvestigationView],
    ]

    def investigation(
        self, request: InvestigationRequest, *, served: ServedInvestigation
    ) -> InvestigationView:
        """Open an investigation, append ledger entries, or render the ledger or its knowns."""
        return dispatch_to_service(self.handlers, request.action, request, service=served)


investigation_tool = InvestigationTool(
    handlers=MappingProxyType(
        {
            InvestigationAction.START: ActionHandler(
                variant=StartInvestigation, handle=start_investigation
            ),
            InvestigationAction.ADD: ActionHandler(variant=AddInvestigation, handle=add_entries),
            InvestigationAction.RENDER: ActionHandler(
                variant=RenderInvestigation, handle=render_ledger
            ),
            InvestigationAction.KNOWNS: ActionHandler(
                variant=KnownsInvestigation, handle=render_knowns
            ),
            InvestigationAction.LIST: ActionHandler(
                variant=ListInvestigation, handle=list_investigations
            ),
        }
    )
)
investigation_action_tool: ActionTool[
    InvestigationAction, InvestigationServed, InvestigationRequest, InvestigationView
] = investigation_tool
