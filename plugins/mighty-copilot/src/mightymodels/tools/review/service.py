"""The review service: a review run, its findings, the user's decisions and the fix outcomes.

A run records its scope, depth, persona weights and reviewer models at HEAD. A reviewer's model
comes from the depth alone, and `override` moves the heavier-weighted reviewer of the run to the
strongest model once; on equal weights the first persona, merge-vader, is the heavier. `add` reads a
persona's report from the run directory and records its findings; the reports and the metrics
file are the only files a run keeps, and `report` returns its text for the agent to write.
`listing` names the newest runs and says so when older ones are left out.
Every write is validated in full before anything is stored, so a rejected batch stores nothing.
A recorded batch says after its own line which findings resemble a row stored earlier, of any kind.
Only the user's dispositions move a finding to remediation, and a decision stands for the finding
as the user saw it: when a later `add` merges into a decided finding and changes it, its decision
and its fix outcome are deleted and `add` names it as back to undecided.

The service is built once by whoever owns the workspace and the store, the server in its
lifespan, and holds both with the git queries it asks for HEAD. Each action opens one transaction
on its store, which hands it the review repository. That repository hands out values and never a
row, so what the rendering takes and what an action returns holds none. Everything above the class
reads no service state.

A stored decision is read back as it is and not validated as a request, so text longer than a
request may carry, stored before the lengths were enforced or lengthened by redaction, does not
make its run unreadable.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from mightymodels.clock import now
from mightymodels.core.declarative import NAME_LIMIT, PROSE_LIMIT
from mightymodels.core.errors import StateError
from mightymodels.core.routing import EFFORT, OVERRIDE_MODEL, Depth, Worker, reviewer_model
from mightymodels.core.run_id import RunId
from mightymodels.core.workspace import GitQueries, Workspace, revision_error
from mightymodels.redaction import redact_within
from mightymodels.tools.review.errors import (
    BaseRequiredError,
    CommitRequiredError,
    NotChosenError,
    OverrideSpentError,
    PersonaChoiceError,
    ReasonRequiredError,
    ReportMissingError,
    ResultReasonError,
    RunExistsError,
    SlugRequiredError,
    UnknownFindingError,
    WeightRangeError,
    WeightsMissingError,
    WeightSumError,
)
from mightymodels.tools.review.finding_merge import fold, normalized
from mightymodels.tools.review.rendering import Standing, gate_text, report_text, verdict_of
from mightymodels.tools.review.report_parser import parse_report
from mightymodels.tools.review.repository import RUNS_LISTED
from mightymodels.tools.review.schema import (
    Decision,
    DisposePayload,
    Disposition,
    Emphasis,
    Finding,
    FindingInput,
    Persona,
    ResolvePayload,
    Result,
    ReviewRun,
    ReviewScope,
    ReviewView,
    Shape,
    StartPayload,
)
from mightymodels.tools.review.store import (
    DecidedFinding,
    ResolvedFinding,
    ReviewRepository,
    ReviewStore,
)
from mightymodels.tools.similarity.rendering import duplicates_text

STANDARD_THRESHOLD = 0.25
WEIGHT_TOLERANCE = 0.001
RUN_ID_FORMAT = '%Y%m%d-%H%M%S'
NEEDS_REASON = frozenset({Decision.ACCEPT_RISK, Decision.DISMISS})
NEEDS_BASE = frozenset({ReviewScope.BRANCH, ReviewScope.TICKET})
PRESETS: Mapping[Emphasis, Mapping[Persona, float]] = MappingProxyType(
    {
        Emphasis.RELEASE: MappingProxyType({Persona.MERGE_VADER: 0.7, Persona.UNCLE_BOB: 0.3}),
        Emphasis.MAINTAINABILITY: MappingProxyType(
            {Persona.MERGE_VADER: 0.3, Persona.UNCLE_BOB: 0.7}
        ),
        Emphasis.BALANCED: MappingProxyType({Persona.MERGE_VADER: 0.5, Persona.UNCLE_BOB: 0.5}),
    }
)
REPORT_FILES: Mapping[Persona, str] = MappingProxyType(
    {
        Persona.MERGE_VADER: 'MERGE-VADER-REPORT.md',
        Persona.UNCLE_BOB: 'UNCLE-BOB-REPORT.md',
    }
)
REVIEWERS: Mapping[Persona, Worker] = MappingProxyType(
    {
        Persona.MERGE_VADER: Worker.MERGE_VADER,
        Persona.UNCLE_BOB: Worker.UNCLE_BOB,
    }
)
NO_RUNS = 'no review runs\n'
OLDER_LEFT_OUT = f'older review runs are left out: these are the latest {RUNS_LISTED.rows}\n'


def findings_of(repository: ReviewRepository, run: RunId) -> dict[str, Finding]:
    return {finding.id: finding for finding in repository.findings(run)}


def dispositions_of(repository: ReviewRepository, run: RunId) -> dict[str, Disposition]:
    return {
        decided.finding_id: Disposition.model_construct(
            decision=decided.decision, reason=decided.reason
        )
        for decided in repository.decisions.dispositions(run)
    }


def standing_of(repository: ReviewRepository, run: ReviewRun) -> Standing:
    outcomes = repository.decisions.outcomes(run.run_id)
    return Standing(
        run=run,
        dispositions=dispositions_of(repository, run.run_id),
        results={resolved.finding_id: resolved.result for resolved in outcomes},
    )


def target_error(payload: StartPayload) -> StateError | None:
    if payload.scope in NEEDS_BASE and payload.base is None:
        return BaseRequiredError(payload.scope)
    if payload.scope is ReviewScope.TICKET and payload.slug is None:
        return SlugRequiredError()
    if payload.base is None:
        return None
    return revision_error(payload.base)


def weights_for(payload: StartPayload) -> Mapping[Persona, float]:
    if payload.emphasis is not Emphasis.CUSTOM:
        return PRESETS[payload.emphasis]
    weights = payload.weights
    if weights is None:
        raise WeightsMissingError
    if set(weights) != set(Persona) or not all(0 <= value <= 1 for value in weights.values()):
        raise WeightRangeError
    if abs(sum(weights.values()) - 1) > WEIGHT_TOLERANCE:
        raise WeightSumError
    return weights


def personas_for(
    depth: Depth, weights: Mapping[Persona, float], chosen: Persona | None
) -> list[Persona]:
    if depth is Depth.DEEP:
        return list(Persona)
    if depth is Depth.STANDARD:
        return [persona for persona in Persona if weights[persona] >= STANDARD_THRESHOLD]
    if chosen is not None:
        return [chosen]
    heaviest = max(weights.values())
    leaders = [persona for persona in Persona if weights[persona] == heaviest]
    if len(leaders) > 1:
        raise PersonaChoiceError
    return leaders


def reviewer_models(personas: Sequence[Persona], depth: Depth) -> dict[str, str]:
    return {REVIEWERS[persona].value: reviewer_model(depth).value for persona in personas}


def override_spent(run: ReviewRun) -> bool:
    return OVERRIDE_MODEL.value in run.models.values()


def heavier_persona(run: ReviewRun) -> Persona:
    return max(run.personas, key=run.weights.__getitem__)


def overridden_text(run: RunId, reviewer: Worker) -> str:
    return (
        f'run {run}: {reviewer} on {OVERRIDE_MODEL}\n'
        f'dispatch it with effort {EFFORT[OVERRIDE_MODEL]}\n'
    )


def started_text(started_run: ReviewRun, relative: str) -> str:
    listed = ', '.join(f'{name} on {model}' for name, model in started_run.models.items())
    return f'run {started_run.run_id} at {relative}\n{started_run.depth} review: {listed}\n'


def reopened_ids(
    recorded: Mapping[str, Finding], changed: Sequence[Finding], decided: Collection[str]
) -> list[str]:
    return [
        finding.id
        for finding in changed
        if finding.id in decided and recorded[finding.id] != finding
    ]


def record_batch(
    repository: ReviewRepository, run: RunId, batch: Sequence[FindingInput]
) -> ReviewView:
    incoming = [normalized(entry, index) for index, entry in enumerate(batch)]
    recorded = findings_of(repository, run)
    changed = fold(recorded, incoming)
    reopened = reopened_ids(recorded, changed, dispositions_of(repository, run))
    duplicates = repository.record_findings(run, changed)
    repository.decisions.reopen(run, reopened)
    ids = ', '.join(finding.id for finding in changed) or 'none'
    tail = f'; back to undecided: {", ".join(reopened)}' if reopened else ''
    text = (
        f'{len(incoming)} findings in, {len(changed)} recorded: {ids}{tail}\n'
        f'{duplicates_text(duplicates)}'
    )
    return ReviewView(text=text, run_id=run.root)


def decided_finding(finding_id: str, entry: Disposition, *, by: str) -> DecidedFinding:
    if entry.decision in NEEDS_REASON and not entry.reason.strip():
        raise ReasonRequiredError(finding_id, entry.decision)
    return DecidedFinding(
        finding_id=finding_id,
        decision=entry.decision,
        reason=redact_within(entry.reason.strip(), 'reason', PROSE_LIMIT),
        by=redact_within(by, 'by', NAME_LIMIT),
        at=now(),
    )


def resolution_error(payload: ResolvePayload) -> StateError | None:
    if payload.commit is not None and (error := revision_error(payload.commit)) is not None:
        return error
    if payload.result is Result.FIXED and payload.commit is None:
        return CommitRequiredError(payload.finding)
    if payload.result is not Result.FIXED and (payload.reason is None or not payload.reason):
        return ResultReasonError(payload.finding, payload.result)
    return None


def listing_line(repository: ReviewRepository, run: ReviewRun) -> str:
    findings = list(findings_of(repository, run.run_id).values())
    verdict = verdict_of(findings, standing_of(repository, run))
    slug = '-' if run.slug is None else run.slug
    return f'{run.run_id}\t{slug}\t{run.depth}\t{len(findings)} findings\t{verdict}\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewService:
    workspace: Workspace
    store: ReviewStore
    git: GitQueries

    def start(self, payload: StartPayload, *, started: datetime) -> ReviewView:
        if (error := target_error(payload)) is not None:
            raise error
        weights = weights_for(payload)
        personas = personas_for(payload.depth, weights, payload.persona)
        run = RunId(started.strftime(RUN_ID_FORMAT))
        with self.store.transaction() as repository:
            if repository.run(run) is not None:
                raise RunExistsError(run)
            started_run = ReviewRun(
                run_id=run,
                slug=payload.slug,
                scope=payload.scope,
                base=payload.base,
                head=self.git.resolve_head(),
                depth=payload.depth,
                emphasis=payload.emphasis,
                weights=weights,
                personas=tuple(personas),
                models=reviewer_models(personas, payload.depth),
                created_at=started.isoformat(timespec='seconds'),
            )
            repository.record_run(started_run)
            directory = self.workspace.review_directory(payload.slug, run)
            directory.mkdir(parents=True, exist_ok=True)
        text = started_text(started_run, self.workspace.relative_to_root(directory))
        return ReviewView(text=text, run_id=run.root)

    def override(self, run: RunId) -> ReviewView:
        with self.store.transaction() as repository:
            started_run = repository.started_run(run)
            if override_spent(started_run):
                raise OverrideSpentError(run)
            reviewer = REVIEWERS[heavier_persona(started_run)]
            repository.record_models(
                run, {**started_run.models, reviewer.value: OVERRIDE_MODEL.value}
            )
        return ReviewView(text=overridden_text(run, reviewer), run_id=run.root)

    def add(self, run: RunId, persona: Persona) -> ReviewView:
        with self.store.transaction() as repository:
            started_run = repository.started_run(run)
            report = self.workspace.persona_report(
                started_run.slug, run, name=REPORT_FILES[persona]
            )
            if report.file is None or not report.file.is_file():
                raise ReportMissingError(persona, report.relative)
            batch = parse_report(report.file.read_text(encoding='utf-8'), persona)
            return record_batch(repository, run, batch)

    def add_findings(self, run: RunId, batch: Sequence[FindingInput]) -> ReviewView:
        with self.store.transaction() as repository:
            repository.started_run(run)
            return record_batch(repository, run, batch)

    def gate(self, run: RunId) -> ReviewView:
        with self.store.transaction() as repository:
            started_run = repository.started_run(run)
            findings = list(findings_of(repository, run).values())
            standing = standing_of(repository, started_run)
        return ReviewView(text=gate_text(findings, standing), run_id=run.root)

    def dispose(self, run: RunId, payload: DisposePayload) -> ReviewView:
        with self.store.transaction() as repository:
            repository.started_run(run)
            findings = findings_of(repository, run)
            unknown = next(
                (finding_id for finding_id in payload.decisions if finding_id not in findings), None
            )
            if unknown is not None:
                raise UnknownFindingError(unknown)
            decided = [
                decided_finding(finding_id, entry, by=payload.by)
                for finding_id, entry in payload.decisions.items()
            ]
            repository.decisions.record_dispositions(run, decided)
            disposed = set(dispositions_of(repository, run)) | set(payload.decisions)
        undecided = [finding_id for finding_id in findings if finding_id not in disposed]
        tail = f'; undecided: {", ".join(undecided)}' if undecided else ''
        return ReviewView(text=f'{len(decided)} dispositions recorded{tail}\n', run_id=run.root)

    def resolve(self, run: RunId, payload: ResolvePayload) -> ReviewView:
        with self.store.transaction() as repository:
            repository.started_run(run)
            if payload.finding not in findings_of(repository, run):
                raise UnknownFindingError(payload.finding)
            chosen = dispositions_of(repository, run).get(payload.finding)
            if chosen is None or chosen.decision is not Decision.FIX:
                raise NotChosenError(payload.finding)
            if (error := resolution_error(payload)) is not None:
                raise error
            repository.decisions.record_outcome(
                run,
                ResolvedFinding(
                    finding_id=payload.finding,
                    result=payload.result,
                    commit='' if payload.commit is None else payload.commit,
                    reason=''
                    if payload.reason is None
                    else redact_within(payload.reason, 'reason', PROSE_LIMIT),
                    at=now(),
                ),
            )
        return ReviewView(text=f'{payload.finding} {payload.result}\n', run_id=run.root)

    def report(self, run: RunId, shape: Shape) -> ReviewView:
        with self.store.transaction() as repository:
            started_run = repository.started_run(run)
            findings = list(findings_of(repository, run).values())
            standing = standing_of(repository, started_run)
        text = report_text(shape, findings, standing)
        return ReviewView(text=text, run_id=run.root, verdict=verdict_of(findings, standing))

    def listing(self) -> ReviewView:
        with self.store.transaction() as repository:
            listed = repository.latest_runs()
            lines = [listing_line(repository, run) for run in listed.rows]
        note = OLDER_LEFT_OUT if listed.older_left_out else ''
        return ReviewView(text=(''.join(lines) or NO_RUNS) + note)
