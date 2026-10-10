"""The `ticket` tool: each handler checks the call's arguments and asks the ticket service.

`write` asks the user for the scope, the compaction and the branch when the fields leave them out,
through the resolvers in `questions`. `ServedTicket` holds the service and the answers, which a
tool's argument limit leaves no room to take as separate parameters.

`ResolvedTickets` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.asking import answer_of, chosen, needs_input_text
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.ticket.questions import (
    BRANCH,
    COMPACTION,
    SCOPE,
    AskedBranch,
    AskedCompaction,
    AskedScope,
    BranchAnswer,
    CompactionAnswer,
    ScopeAnswer,
)
from mightymodels_plugin.tools.ticket.schema import (
    TicketAction,
    TicketAnswers,
    TicketContext,
    TicketFields,
    TicketRequest,
    TicketView,
)
from mightymodels_plugin.tools.ticket.service import TicketService


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketAsked:
    scope: ElicitationResult[ScopeAnswer]
    compaction: ElicitationResult[CompactionAnswer]
    branch: ElicitationResult[BranchAnswer]


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketCall:
    slug: Slug
    fields: TicketFields | None
    asked: TicketAsked


def named_branch(tickets: TicketService, request: TicketRequest, asked: TicketAsked) -> str | None:
    if request.branch is not None:
        return request.branch
    answer = answer_of(asked.branch)
    if answer is None or answer.choice is None:
        return None
    return tickets.branch_named(answer.choice, answer.name)


def write_ticket(tickets: TicketService, call: TicketCall) -> TicketView:
    request = call.fields
    if not isinstance(request, TicketRequest):
        raise MissingArgumentsError(TicketAction.WRITE, 'fields holding the interview answers')
    scope = request.scope or chosen(call.asked.scope)
    compaction = chosen(call.asked.compaction) if request.compaction is None else request.compaction
    branch = named_branch(tickets, request, call.asked)
    if scope is None or compaction is None or branch is None:
        unanswered = [
            question
            for question, value in ((SCOPE, scope), (COMPACTION, compaction), (BRANCH, branch))
            if value is None
        ]
        return TicketView(text=needs_input_text(unanswered))
    answers = TicketAnswers.model_validate(
        request.model_dump() | {'scope': scope, 'compaction': compaction, 'branch': branch}
    )
    return tickets.write(call.slug, answers)


def validate_ticket(tickets: TicketService, call: TicketCall) -> TicketView:
    return tickets.validate(call.slug)


def show_ticket(tickets: TicketService, call: TicketCall) -> TicketView:
    return tickets.show(call.slug)


def update_ticket_context(tickets: TicketService, call: TicketCall) -> TicketView:
    if not isinstance(call.fields, TicketContext):
        raise MissingArgumentsError(
            TicketAction.UPDATE_CONTEXT, 'fields holding only the context lines'
        )
    return tickets.update_context(call.slug, call.fields)


def lifespan_tickets(ctx: Context[ServedState]) -> TicketService:
    return served_services(ctx).tickets


ResolvedTickets = Annotated[TicketService, Resolve(lifespan_tickets)]


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketServed:
    tickets: TicketService
    asked: TicketAsked


def serve_tickets(
    tickets: ResolvedTickets, *, scope: AskedScope, compaction: AskedCompaction, branch: AskedBranch
) -> TicketServed:
    asked = TicketAsked(scope=scope, compaction=compaction, branch=branch)
    return TicketServed(tickets=tickets, asked=asked)


ServedTicket = Annotated[TicketServed, Resolve(serve_tickets)]


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketTool:
    handlers: Mapping[TicketAction, ServiceHandler[TicketService, TicketCall, TicketView]]

    def ticket(
        self,
        action: TicketAction,
        slug: Slug,
        fields: TicketFields | None = None,
        *,
        served: ServedTicket,
    ) -> TicketView:
        """Create, validate, read or update a ticket's context lines; writes the fixed models."""
        call = TicketCall(slug=slug, fields=fields, asked=served.asked)
        return dispatch_to_service(self.handlers, action, call, service=served.tickets)


ticket_tool = TicketTool(
    handlers=MappingProxyType(
        {
            TicketAction.WRITE: write_ticket,
            TicketAction.VALIDATE: validate_ticket,
            TicketAction.SHOW: show_ticket,
            TicketAction.UPDATE_CONTEXT: update_ticket_context,
        }
    )
)
ticket_action_tool: ActionTool[TicketAction, TicketService, TicketCall, TicketView] = ticket_tool
