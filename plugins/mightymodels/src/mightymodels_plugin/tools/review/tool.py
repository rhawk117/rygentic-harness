"""The `review` tool: each handler checks the call's arguments and asks the review service.

Every action but `start` and `list` works on one run, and `run_id_for` is the one place that
refuses a call that names none.

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

from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.tools.asking import answer_of, chosen, needs_input_text
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.review.questions import (
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
from mightymodels_plugin.tools.review.schema import (
    AddPayload,
    DisposePayload,
    DisposeRequest,
    Disposition,
    ReportPayload,
    ResolvePayload,
    ReviewAction,
    ReviewPayload,
    ReviewView,
    StartPayload,
    StartRequest,
)
from mightymodels_plugin.tools.review.service import ReviewService

RUN_ID_ARGUMENT = 'run_id'


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
class ReviewCall:
    run_id: RunId | None
    payload: ReviewPayload | None
    asked: ReviewAsked


def run_id_for(action: ReviewAction, call: ReviewCall) -> RunId:
    if call.run_id is None:
        raise MissingArgumentsError(action, RUN_ID_ARGUMENT)
    return call.run_id


def start_run(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    request = StartRequest() if call.payload is None else call.payload
    if not isinstance(request, StartRequest):
        raise MissingArgumentsError(
            ReviewAction.START, 'no payload, or a payload holding scope, depth and emphasis'
        )
    scope = request.scope or chosen(call.asked.start.scope)
    depth = request.depth or chosen(call.asked.start.depth)
    emphasis = request.emphasis or chosen(call.asked.start.emphasis)
    if scope is None or depth is None or emphasis is None:
        unanswered = [
            question
            for question, value in ((SCOPE, scope), (DEPTH, depth), (EMPHASIS, emphasis))
            if value is None
        ]
        return ReviewView(text=needs_input_text(unanswered))
    payload = StartPayload.model_validate(
        request.model_dump() | {'scope': scope, 'depth': depth, 'emphasis': emphasis}
    )
    return reviews.start(payload, started=datetime.now(tz=UTC))


def override_reviewer(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    return reviews.override(run_id_for(ReviewAction.OVERRIDE, call))


def add_persona_report(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    run = run_id_for(ReviewAction.ADD, call)
    if not isinstance(call.payload, AddPayload):
        raise MissingArgumentsError(
            ReviewAction.ADD, 'a payload holding the persona whose report to read'
        )
    return reviews.add(run, call.payload.persona)


def gate_run(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    return reviews.gate(run_id_for(ReviewAction.GATE, call))


def dispose_findings(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    run = run_id_for(ReviewAction.DISPOSE, call)
    request = call.payload
    if not isinstance(request, DisposeRequest):
        raise MissingArgumentsError(ReviewAction.DISPOSE, 'a payload holding by and decisions')
    if request.decisions is not None:
        return reviews.dispose(run, DisposePayload(by=request.by, decisions=request.decisions))
    if request.finding is None:
        raise MissingArgumentsError(
            ReviewAction.DISPOSE, 'decisions, or the finding to ask the user about'
        )
    answer = answer_of(call.asked.disposition)
    if answer is None or answer.choice is None:
        text = needs_input_text([disposition_question(request.finding)])
        return ReviewView(text=text, run_id=run.root)
    decision = Disposition(decision=answer.choice, reason=answer.reason)
    decisions = {request.finding: decision}
    return reviews.dispose(run, DisposePayload(by=request.by, decisions=decisions))


def resolve_finding(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    run = run_id_for(ReviewAction.RESOLVE, call)
    if not isinstance(call.payload, ResolvePayload):
        raise MissingArgumentsError(ReviewAction.RESOLVE, 'a payload holding finding and result')
    return reviews.resolve(run, call.payload)


def render_report(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    run = run_id_for(ReviewAction.REPORT, call)
    payload = ReportPayload() if call.payload is None else call.payload
    if not isinstance(payload, ReportPayload):
        raise MissingArgumentsError(
            ReviewAction.REPORT, 'no payload, or a payload holding only shape'
        )
    return reviews.report(run, payload.shape)


def list_runs(reviews: ReviewService, _call: ReviewCall) -> ReviewView:
    return reviews.listing()


def lifespan_reviews(ctx: Context[ServedState]) -> ReviewService:
    return served_services(ctx).reviews


ResolvedReviews = Annotated[ReviewService, Resolve(lifespan_reviews)]


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewServed:
    reviews: ReviewService
    asked: ReviewAsked


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
    handlers: Mapping[ReviewAction, ServiceHandler[ReviewService, ReviewCall, ReviewView]]

    def review(
        self,
        action: ReviewAction,
        run_id: RunId | None = None,
        payload: ReviewPayload | None = None,
        *,
        served: ServedReview,
    ) -> ReviewView:
        """Record a review run, findings, dispositions and resolutions; render the report text."""
        call = ReviewCall(run_id=run_id, payload=payload, asked=served.asked)
        return dispatch_to_service(self.handlers, action, call, service=served.reviews)


review_tool = ReviewTool(
    handlers=MappingProxyType(
        {
            ReviewAction.START: start_run,
            ReviewAction.OVERRIDE: override_reviewer,
            ReviewAction.ADD: add_persona_report,
            ReviewAction.GATE: gate_run,
            ReviewAction.DISPOSE: dispose_findings,
            ReviewAction.RESOLVE: resolve_finding,
            ReviewAction.REPORT: render_report,
            ReviewAction.LIST: list_runs,
        }
    )
)
review_action_tool: ActionTool[ReviewAction, ReviewService, ReviewCall, ReviewView] = review_tool
