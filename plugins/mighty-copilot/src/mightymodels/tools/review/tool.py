"""The `review` tool: each handler takes its action's request and asks the review service.

Every action but `start` and `list` works on one run, and the schema refuses a call that names
none. `dispose` takes its decisions or the one finding to ask the user about, a choice between
two fields that the schema does not state, so `dispose_findings` refuses a payload holding
neither.

`start` and `dispose` ask the user for what the payload leaves out, through the resolvers in
`questions`. `ServedReview` holds the service and the answers, which a tool's argument limit leaves
no room to take as separate parameters.

`ResolvedReviews` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Annotated

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Context, Resolve

from mightymodels.tools.asking import answer_of, chosen, needs_input_text
from mightymodels.tools.protocol import (
    ActionHandler,
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels.tools.review.questions import (
    DEPTH,
    EMPHASIS,
    SCOPE,
    AskedDepth,
    AskedDisposition,
    AskedEmphasis,
    AskedScope,
    DepthAnswer,
    DispositionAnswer,
    EmphasisAnswer,
    ScopeAnswer,
    disposition_question,
)
from mightymodels.tools.review.schema import (
    AddReview,
    DisposePayload,
    DisposeReview,
    Disposition,
    GateReview,
    ListReview,
    OverrideReview,
    ReportPayload,
    ReportReview,
    ResolveReview,
    ReviewAction,
    ReviewRequest,
    ReviewView,
    StartPayload,
    StartRequest,
    StartReview,
)
from mightymodels.tools.review.service import ReviewService


@dataclass(slots=True, kw_only=True, frozen=True)
class StartAsked:
    scope: ElicitationResult[ScopeAnswer]
    depth: ElicitationResult[DepthAnswer]
    emphasis: ElicitationResult[EmphasisAnswer]


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewAsked:
    start: StartAsked
    disposition: ElicitationResult[DispositionAnswer]


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewServed:
    reviews: ReviewService
    asked: ReviewAsked


def start_run(served: ReviewServed, request: StartReview) -> ReviewView:
    payload = StartRequest() if request.payload is None else request.payload
    asked = served.asked.start
    scope = payload.scope or chosen(asked.scope)
    depth = payload.depth or chosen(asked.depth)
    emphasis = payload.emphasis or chosen(asked.emphasis)
    if scope is None or depth is None or emphasis is None:
        unanswered = [
            question
            for question, value in ((SCOPE, scope), (DEPTH, depth), (EMPHASIS, emphasis))
            if value is None
        ]
        return ReviewView(text=needs_input_text(unanswered))
    complete = StartPayload.model_validate(
        payload.model_dump() | {'scope': scope, 'depth': depth, 'emphasis': emphasis}
    )
    return served.reviews.start(complete, started=datetime.now(tz=UTC))


def override_reviewer(served: ReviewServed, request: OverrideReview) -> ReviewView:
    return served.reviews.override(request.run_id)


def add_persona_report(served: ReviewServed, request: AddReview) -> ReviewView:
    return served.reviews.add(request.run_id, request.payload.persona)


def gate_run(served: ReviewServed, request: GateReview) -> ReviewView:
    return served.reviews.gate(request.run_id)


def dispose_findings(served: ReviewServed, request: DisposeReview) -> ReviewView:
    run, payload = request.run_id, request.payload
    if payload.decisions is not None:
        complete = DisposePayload(by=payload.by, decisions=payload.decisions)
        return served.reviews.dispose(run, complete)
    if payload.finding is None:
        raise MissingArgumentsError(
            ReviewAction.DISPOSE, 'decisions, or the finding to ask the user about'
        )
    answer = answer_of(served.asked.disposition)
    if answer is None or answer.choice is None:
        text = needs_input_text([disposition_question(payload.finding)])
        return ReviewView(text=text, run_id=run.root)
    decision = Disposition(decision=answer.choice, reason=answer.reason)
    decisions = {payload.finding: decision}
    return served.reviews.dispose(run, DisposePayload(by=payload.by, decisions=decisions))


def resolve_finding(served: ReviewServed, request: ResolveReview) -> ReviewView:
    return served.reviews.resolve(request.run_id, request.payload)


def render_report(served: ReviewServed, request: ReportReview) -> ReviewView:
    payload = ReportPayload() if request.payload is None else request.payload
    return served.reviews.report(request.run_id, payload.shape)


def list_runs(served: ReviewServed, _request: ListReview) -> ReviewView:
    return served.reviews.listing()


def lifespan_reviews(ctx: Context[ServedState]) -> ReviewService:
    return served_services(ctx).reviews


ResolvedReviews = Annotated[ReviewService, Resolve(lifespan_reviews)]


def start_asked(scope: AskedScope, depth: AskedDepth, emphasis: AskedEmphasis) -> StartAsked:
    return StartAsked(scope=scope, depth=depth, emphasis=emphasis)


StartAskedFor = Annotated[StartAsked, Resolve(start_asked)]


def serve_reviews(
    reviews: ResolvedReviews, start: StartAskedFor, disposition: AskedDisposition
) -> ReviewServed:
    return ReviewServed(reviews=reviews, asked=ReviewAsked(start=start, disposition=disposition))


ServedReview = Annotated[ReviewServed, Resolve(serve_reviews)]


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewTool:
    handlers: Mapping[ReviewAction, ServiceHandler[ReviewServed, ReviewRequest, ReviewView]]

    def review(self, request: ReviewRequest, *, served: ServedReview) -> ReviewView:
        """Record a review run, findings, dispositions and resolutions; render the report text."""
        return dispatch_to_service(self.handlers, request.action, request, service=served)


review_tool = ReviewTool(
    handlers=MappingProxyType(
        {
            ReviewAction.START: ActionHandler(variant=StartReview, handle=start_run),
            ReviewAction.OVERRIDE: ActionHandler(variant=OverrideReview, handle=override_reviewer),
            ReviewAction.ADD: ActionHandler(variant=AddReview, handle=add_persona_report),
            ReviewAction.GATE: ActionHandler(variant=GateReview, handle=gate_run),
            ReviewAction.DISPOSE: ActionHandler(variant=DisposeReview, handle=dispose_findings),
            ReviewAction.RESOLVE: ActionHandler(variant=ResolveReview, handle=resolve_finding),
            ReviewAction.REPORT: ActionHandler(variant=ReportReview, handle=render_report),
            ReviewAction.LIST: ActionHandler(variant=ListReview, handle=list_runs),
        }
    )
)
review_action_tool: ActionTool[ReviewAction, ReviewServed, ReviewRequest, ReviewView] = review_tool
