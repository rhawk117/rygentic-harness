"""The question `investigation` puts to the user when `start` leaves the kind of target out.

`AskedKind` is a plain assignment because the SDK does not see a `Resolve` marker behind a PEP 695
`type` alias and would put the parameter in the tool's schema.
"""

from typing import Annotated

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Elicit, Resolve

from mightymodels_plugin.tools.asking import Choice, Question, enumerated
from mightymodels_plugin.tools.investigation.schema import (
    InvestigationRequest,
    StartInvestigation,
    TargetKind,
)

KindChoices = Annotated[TargetKind, enumerated(TargetKind)]
KindAnswer = Choice[KindChoices]


def kind_question(target: str) -> Question:
    return Question(
        message=f'What kind of target is this? {target}',
        answer=KindAnswer,
        argument='request.payload.request.kind',
    )


def ask_kind(request: InvestigationRequest) -> KindAnswer | Elicit[KindAnswer]:
    if not isinstance(request, StartInvestigation):
        return KindAnswer(choice=None)
    if request.payload.request.kind is not None:
        return KindAnswer(choice=None)
    return Elicit(kind_question(request.payload.request.target).message, KindAnswer)


AskedKind = Annotated[ElicitationResult[KindAnswer], Resolve(ask_kind)]
