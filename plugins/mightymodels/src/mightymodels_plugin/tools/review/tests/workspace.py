from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError

from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.tools.review.schema import (
    DisposePayload,
    FindingInput,
    ResolvePayload,
    ReviewView,
    Shape,
    StartPayload,
    Verdict,
)
from mightymodels_plugin.tools.review.service import ReviewService

SLUG = 'retry-queue'
ADVANCED, REJECTED = 0, 2
BALANCED = {'scope': 'ticket', 'slug': SLUG, 'base': 'main', 'emphasis': 'balanced'}


@dataclass(frozen=True, slots=True, kw_only=True)
class Outcome:
    code: int
    view: ReviewView | None
    err: str

    @property
    def out(self) -> str:
        return self.view.text if self.view else ''

    @property
    def verdict(self) -> Verdict | None:
        return self.view.verdict if self.view else None


def finding(source: str, severity: str, location: str, **extra: object) -> FindingInput:
    return FindingInput.model_validate(
        {
            'sources': [source],
            'severity': severity,
            'title': f'{source} title',
            'location': location,
            'fix': 'do the thing',
            'verify': 'uv run pytest -q',
            **extra,
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    reviews: ReviewService
    git: InMemoryGit

    def attempt(self, act: Callable[[ReviewService], ReviewView]) -> Outcome:
        try:
            view = act(self.reviews)
        except (StateError, ValidationError) as error:
            return Outcome(code=REJECTED, view=None, err=str(error))
        return Outcome(code=ADVANCED, view=view, err='')

    def try_start(self, payload: dict[str, object], started: datetime | None = None) -> Outcome:
        model = StartPayload.model_validate(payload)
        moment = started or datetime.now(tz=UTC)
        return self.attempt(lambda reviews: reviews.start(model, started=moment))

    def start(self, *, started: datetime | None = None, **payload: object) -> RunId:
        outcome = self.try_start({**BALANCED, **payload}, started)
        assert outcome.view is not None, outcome.err
        return RunId(outcome.view.run_id or '')

    def add(self, run: RunId, batch: list[FindingInput]) -> Outcome:
        return self.attempt(lambda reviews: reviews.add_findings(run, batch))

    def gate(self, run: RunId) -> Outcome:
        return self.attempt(lambda reviews: reviews.gate(run))

    def dispose(self, run: RunId, **payload: object) -> Outcome:
        model = DisposePayload.model_validate(payload)
        return self.attempt(lambda reviews: reviews.dispose(run, model))

    def resolve(self, run: RunId, **payload: object) -> Outcome:
        model = ResolvePayload.model_validate(payload)
        return self.attempt(lambda reviews: reviews.resolve(run, model))

    def report(self, run: RunId, shape: Shape = Shape.FULL) -> Outcome:
        return self.attempt(lambda reviews: reviews.report(run, shape))
