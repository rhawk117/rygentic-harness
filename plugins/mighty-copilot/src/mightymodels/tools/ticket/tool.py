"""The `ticket` tool: each handler takes its action's request and asks the ticket service.

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

from mightymodels.tools.asking import answer_of, chosen, needs_input_text
from mightymodels.tools.protocol import (
    ActionHandler,
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels.tools.ticket.questions import (
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
from mightymodels.tools.ticket.schema import (
    ShowTicket,
    TicketAction,
    TicketAnswers,
    TicketInterview,
    TicketRequest,
    TicketView,
    UpdateContextTicket,
    ValidateTicket,
    WriteTicket,
)
from mightymodels.tools.ticket.service import TicketService


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketAsked:
    scope: ElicitationResult[ScopeAnswer]
    compaction: ElicitationResult[CompactionAnswer]
    branch: ElicitationResult[BranchAnswer]


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketServed:
    tickets: TicketService
    asked: TicketAsked


def named_branch(
    tickets: TicketService, interview: TicketInterview, asked: TicketAsked
) -> str | None:
    if interview.branch is not None:
        return interview.branch
    answer = answer_of(asked.branch)
    if answer is None or answer.choice is None:
        return None
    return tickets.branch_named(answer.choice, answer.name)


def write_ticket(served: TicketServed, request: WriteTicket) -> TicketView:
    interview, asked = request.fields, served.asked
    scope = interview.scope or chosen(asked.scope)
    compaction = chosen(asked.compaction) if interview.compaction is None else interview.compaction
    branch = named_branch(served.tickets, interview, asked)
    if scope is None or compaction is None or branch is None:
        unanswered = [
            question
            for question, value in ((SCOPE, scope), (COMPACTION, compaction), (BRANCH, branch))
            if value is None
        ]
        return TicketView(text=needs_input_text(unanswered))
    answers = TicketAnswers.model_validate(
        interview.model_dump() | {'scope': scope, 'compaction': compaction, 'branch': branch}
    )
    return served.tickets.write(request.slug, answers)


def validate_ticket(served: TicketServed, request: ValidateTicket) -> TicketView:
    return served.tickets.validate(request.slug)


def show_ticket(served: TicketServed, request: ShowTicket) -> TicketView:
    return served.tickets.show(request.slug)


def update_ticket_context(served: TicketServed, request: UpdateContextTicket) -> TicketView:
    return served.tickets.update_context(request.slug, request.fields)


def lifespan_tickets(ctx: Context[ServedState]) -> TicketService:
    return served_services(ctx).tickets


ResolvedTickets = Annotated[TicketService, Resolve(lifespan_tickets)]


def serve_tickets(
    tickets: ResolvedTickets, *, scope: AskedScope, compaction: AskedCompaction, branch: AskedBranch
) -> TicketServed:
    asked = TicketAsked(scope=scope, compaction=compaction, branch=branch)
    return TicketServed(tickets=tickets, asked=asked)


ServedTicket = Annotated[TicketServed, Resolve(serve_tickets)]


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketTool:
    handlers: Mapping[TicketAction, ServiceHandler[TicketServed, TicketRequest, TicketView]]

    def ticket(self, request: TicketRequest, *, served: ServedTicket) -> TicketView:
        """Create, validate, read or update a ticket's context lines; writes the fixed models."""
        return dispatch_to_service(self.handlers, request.action, request, service=served)


ticket_tool = TicketTool(
    handlers=MappingProxyType(
        {
            TicketAction.WRITE: ActionHandler(variant=WriteTicket, handle=write_ticket),
            TicketAction.VALIDATE: ActionHandler(variant=ValidateTicket, handle=validate_ticket),
            TicketAction.SHOW: ActionHandler(variant=ShowTicket, handle=show_ticket),
            TicketAction.UPDATE_CONTEXT: ActionHandler(
                variant=UpdateContextTicket, handle=update_ticket_context
            ),
        }
    )
)
ticket_action_tool: ActionTool[TicketAction, TicketServed, TicketRequest, TicketView] = ticket_tool
