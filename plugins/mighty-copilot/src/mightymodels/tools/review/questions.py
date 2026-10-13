"""The questions `review` puts to the user when a call leaves the answer out.

`start` asks the scope, the depth and the emphasis of whatever the payload leaves out. `dispose`
asks what to do with the one finding its payload names when it carries no decisions, and stores
that one decision. The persona of a quick balanced review is not asked: the skill lists no choices
for it.

`AskedScope` and the other `Asked...` names are plain assignments because the SDK does not see a
`Resolve` marker behind a PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from typing import Annotated

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Elicit, Resolve

from mightymodels.core.routing import Depth
from mightymodels.tools.asking import AnswerProse, Choice, Question, enumerated
from mightymodels.tools.review.schema import (
    Decision,
    DisposeRequest,
    DisposeReview,
    Emphasis,
    ReviewRequest,
    ReviewScope,
    StartRequest,
    StartReview,
)

ScopeChoices = Annotated[ReviewScope, enumerated(ReviewScope)]
DepthChoices = Annotated[Depth, enumerated(Depth)]
EmphasisChoices = Annotated[Emphasis, enumerated(Emphasis)]
DecisionChoices = Annotated[Decision, enumerated(Decision)]

ScopeAnswer = Choice[ScopeChoices]
DepthAnswer = Choice[DepthChoices]
EmphasisAnswer = Choice[EmphasisChoices]


class DispositionAnswer(Choice[DecisionChoices]):
    reason: AnswerProse = ''


SCOPE = Question(
    message='What should the review cover?', answer=ScopeAnswer, argument='request.payload.scope'
)
DEPTH = Question(
    message='How deep should the review go?', answer=DepthAnswer, argument='request.payload.depth'
)
EMPHASIS = Question(
    message='What should the review emphasize?',
    answer=EmphasisAnswer,
    argument='request.payload.emphasis',
)


def disposition_question(finding: str) -> Question:
    decision = '{"decision": <choice>, "reason": "<why>"}'
    return Question(
        message=f'What should happen to {finding}? accept-risk and dismiss need a reason.',
        answer=DispositionAnswer,
        argument=f'request.payload.decisions {{"{finding}": {decision}}}',
    )


def start_request(request: ReviewRequest) -> StartRequest | None:
    if not isinstance(request, StartReview):
        return None
    return StartRequest() if request.payload is None else request.payload


def dispose_request(request: ReviewRequest) -> DisposeRequest | None:
    if not isinstance(request, DisposeReview):
        return None
    return request.payload


def ask_scope(request: ReviewRequest) -> ScopeAnswer | Elicit[ScopeAnswer]:
    start = start_request(request)
    if start is None or start.scope is not None:
        return ScopeAnswer(choice=None)
    return Elicit(SCOPE.message, ScopeAnswer)


def ask_depth(request: ReviewRequest) -> DepthAnswer | Elicit[DepthAnswer]:
    start = start_request(request)
    if start is None or start.depth is not None:
        return DepthAnswer(choice=None)
    return Elicit(DEPTH.message, DepthAnswer)


def ask_emphasis(request: ReviewRequest) -> EmphasisAnswer | Elicit[EmphasisAnswer]:
    start = start_request(request)
    if start is None or start.emphasis is not None:
        return EmphasisAnswer(choice=None)
    return Elicit(EMPHASIS.message, EmphasisAnswer)


def ask_disposition(request: ReviewRequest) -> DispositionAnswer | Elicit[DispositionAnswer]:
    dispose = dispose_request(request)
    if dispose is None or dispose.decisions is not None or dispose.finding is None:
        return DispositionAnswer(choice=None)
    return Elicit(disposition_question(dispose.finding).message, DispositionAnswer)


AskedScope = Annotated[ElicitationResult[ScopeAnswer], Resolve(ask_scope)]
AskedDepth = Annotated[ElicitationResult[DepthAnswer], Resolve(ask_depth)]
AskedEmphasis = Annotated[ElicitationResult[EmphasisAnswer], Resolve(ask_emphasis)]
AskedDisposition = Annotated[ElicitationResult[DispositionAnswer], Resolve(ask_disposition)]
