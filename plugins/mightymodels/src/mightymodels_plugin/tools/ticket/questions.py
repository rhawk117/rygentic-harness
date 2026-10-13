"""The questions `ticket` puts to the user when `write` leaves the scope, compaction or branch out.

The branch answer is the current checkout or a new branch; a new one carries its name, and
`TicketService.branch_named` turns the answer into the name that is written. A caller that asked
the user itself passes the branch name on the fields.

The `Asked...` names are plain assignments because the SDK does not see a `Resolve` marker behind
a PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from typing import Annotated

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Elicit, Resolve

from mightymodels_plugin.core.routing import Scope
from mightymodels_plugin.tools.asking import AnswerName, Choice, Question, enumerated
from mightymodels_plugin.tools.ticket.schema import (
    BranchChoice,
    TicketInterview,
    TicketRequest,
    WriteTicket,
)

ScopeChoices = Annotated[Scope, enumerated(Scope)]
BranchChoices = Annotated[BranchChoice, enumerated(BranchChoice)]

ScopeAnswer = Choice[ScopeChoices]
CompactionAnswer = Choice[bool]


class BranchAnswer(Choice[BranchChoices]):
    name: AnswerName = ''


SCOPE = Question(
    message='What is the scope of each anticipated task?',
    answer=ScopeAnswer,
    argument='request.fields.scope',
)
COMPACTION = Question(
    message='Would implementing this likely cause at least one compaction?',
    answer=CompactionAnswer,
    argument='request.fields.compaction',
)
BRANCH = Question(
    message='Run the work on the current branch, or on a new one? A new one needs a name.',
    answer=BranchAnswer,
    argument='request.fields.branch (the current branch name, or the new branch name)',
)


def write_request(request: TicketRequest) -> TicketInterview | None:
    if not isinstance(request, WriteTicket):
        return None
    return request.fields


def ask_scope(request: TicketRequest) -> ScopeAnswer | Elicit[ScopeAnswer]:
    interview = write_request(request)
    if interview is None or interview.scope is not None:
        return ScopeAnswer(choice=None)
    return Elicit(SCOPE.message, ScopeAnswer)


def ask_compaction(request: TicketRequest) -> CompactionAnswer | Elicit[CompactionAnswer]:
    interview = write_request(request)
    if interview is None or interview.compaction is not None:
        return CompactionAnswer(choice=None)
    return Elicit(COMPACTION.message, CompactionAnswer)


def ask_branch(request: TicketRequest) -> BranchAnswer | Elicit[BranchAnswer]:
    interview = write_request(request)
    if interview is None or interview.branch is not None:
        return BranchAnswer(choice=None)
    return Elicit(BRANCH.message, BranchAnswer)


AskedScope = Annotated[ElicitationResult[ScopeAnswer], Resolve(ask_scope)]
AskedCompaction = Annotated[ElicitationResult[CompactionAnswer], Resolve(ask_compaction)]
AskedBranch = Annotated[ElicitationResult[BranchAnswer], Resolve(ask_branch)]
