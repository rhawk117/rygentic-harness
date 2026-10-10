"""The `investigation` tool: each handler checks the call's arguments and asks the service.

Every action but `start` and `list` works on one investigation, and `investigation_for` is the
one place that refuses a call that names none. `knowns` reads the whole table when the call
carries no filter.

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

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.asking import chosen, needs_input_text
from mightymodels_plugin.tools.investigation.questions import AskedKind, KindAnswer, kind_question
from mightymodels_plugin.tools.investigation.schema import (
    InvestigationAction,
    InvestigationPayload,
    InvestigationStart,
    InvestigationStartRequest,
    InvestigationView,
    KnownsFilter,
    LedgerRound,
)
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)

INVESTIGATION_ARGUMENT = 'investigation_id'


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationCall:
    investigation_id: Slug | None
    payload: InvestigationPayload
    asked: ElicitationResult[KindAnswer]


def investigation_for(action: InvestigationAction, call: InvestigationCall) -> Slug:
    if call.investigation_id is None:
        raise MissingArgumentsError(action, INVESTIGATION_ARGUMENT)
    return call.investigation_id


def start_investigation(
    investigations: InvestigationService, call: InvestigationCall
) -> InvestigationView:
    request = call.payload.request
    if not isinstance(request, InvestigationStartRequest):
        raise MissingArgumentsError(InvestigationAction.START, 'a request holding target and kind')
    kind = request.kind or chosen(call.asked)
    if kind is None:
        return InvestigationView(text=needs_input_text([kind_question(request.target)]))
    started = InvestigationStart(target=request.target, kind=kind)
    return investigations.start(started, started=datetime.now(tz=UTC))


def add_entries(investigations: InvestigationService, call: InvestigationCall) -> InvestigationView:
    investigation = investigation_for(InvestigationAction.ADD, call)
    if call.payload.entries is None or not isinstance(call.payload.request, LedgerRound):
        raise MissingArgumentsError(InvestigationAction.ADD, 'entries and a request holding round')
    return investigations.add(investigation, call.payload.request.round, call.payload.entries)


def render_ledger(
    investigations: InvestigationService, call: InvestigationCall
) -> InvestigationView:
    return investigations.render(investigation_for(InvestigationAction.RENDER, call))


def render_knowns(
    investigations: InvestigationService, call: InvestigationCall
) -> InvestigationView:
    investigation = investigation_for(InvestigationAction.KNOWNS, call)
    selection = KnownsFilter() if call.payload.request is None else call.payload.request
    if not isinstance(selection, KnownsFilter):
        raise MissingArgumentsError(
            InvestigationAction.KNOWNS, 'no request, or a request holding only kinds and limit'
        )
    return investigations.knowns(investigation, selection)


def list_investigations(
    investigations: InvestigationService, _call: InvestigationCall
) -> InvestigationView:
    return investigations.listing()


def lifespan_investigations(ctx: Context[ServedState]) -> InvestigationService:
    return served_services(ctx).investigations


ResolvedInvestigations = Annotated[InvestigationService, Resolve(lifespan_investigations)]


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationServed:
    investigations: InvestigationService
    asked: ElicitationResult[KindAnswer]


def serve_investigations(
    investigations: ResolvedInvestigations, asked: AskedKind
) -> InvestigationServed:
    return InvestigationServed(investigations=investigations, asked=asked)


ServedInvestigation = Annotated[InvestigationServed, Resolve(serve_investigations)]


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationTool:
    handlers: Mapping[
        InvestigationAction,
        ServiceHandler[InvestigationService, InvestigationCall, InvestigationView],
    ]

    def investigation(
        self,
        action: InvestigationAction,
        investigation_id: Slug | None = None,
        payload: InvestigationPayload | None = None,
        *,
        served: ServedInvestigation,
    ) -> InvestigationView:
        """Open an investigation, append ledger entries, or render the ledger or its knowns."""
        call = InvestigationCall(
            investigation_id=investigation_id,
            payload=InvestigationPayload() if payload is None else payload,
            asked=served.asked,
        )
        return dispatch_to_service(self.handlers, action, call, service=served.investigations)


investigation_tool = InvestigationTool(
    handlers=MappingProxyType(
        {
            InvestigationAction.START: start_investigation,
            InvestigationAction.ADD: add_entries,
            InvestigationAction.RENDER: render_ledger,
            InvestigationAction.KNOWNS: render_knowns,
            InvestigationAction.LIST: list_investigations,
        }
    )
)
investigation_action_tool: ActionTool[
    InvestigationAction, InvestigationService, InvestigationCall, InvestigationView
] = investigation_tool
