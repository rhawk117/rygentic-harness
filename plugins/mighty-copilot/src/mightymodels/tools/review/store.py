"""The seam under the review service: a store whose transaction hands out the review repository.

`ReviewStore.transaction` is a context manager, and what it yields is a `ReviewRepository` that
lives for that one transaction. The SQLite store in `repository.py` wraps the database, and a
store in test support holds the runs in memory, so the review service runs on either.

The repository is two Protocols. `ReviewRepository` is the runs and their findings, and its
`decisions` is the `DecisionRepository` of the same transaction, which holds what the user decided
and what each fix came to.

A repository hands out frozen values and never a row: a run is a `ReviewRun` and a finding a
`Finding`, as the service recorded them. `DecidedFinding` and `ResolvedFinding` are a decision and
a fix outcome as they are stored, written and read back in the same shape.
"""

from collections.abc import Collection, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mightymodels.core.database import Latest
from mightymodels.core.run_id import RunId
from mightymodels.core.slug import Slug
from mightymodels.tools.review.schema import Decision, Finding, Result, ReviewRun
from mightymodels.tools.similarity.schema import Duplicate


@dataclass(slots=True, kw_only=True, frozen=True)
class DecidedFinding:
    finding_id: str
    decision: Decision
    reason: str
    by: str
    at: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ResolvedFinding:
    finding_id: str
    result: Result
    commit: str
    reason: str
    at: str


@runtime_checkable
class DecisionRepository(Protocol):
    def dispositions(self, run: RunId) -> list[DecidedFinding]: ...

    def outcomes(self, run: RunId) -> list[ResolvedFinding]: ...

    def record_dispositions(self, run: RunId, decided: Iterable[DecidedFinding]) -> None: ...

    def record_outcome(self, run: RunId, resolved: ResolvedFinding) -> None: ...

    def reopen(self, run: RunId, finding_ids: Collection[str]) -> None: ...


@runtime_checkable
class ReviewRepository(Protocol):
    @property
    def decisions(self) -> DecisionRepository: ...

    def run(self, run: RunId) -> ReviewRun | None: ...

    def started_run(self, run: RunId) -> ReviewRun: ...

    def latest_runs(self) -> Latest[ReviewRun]: ...

    def latest_run(self, slug: Slug) -> ReviewRun | None: ...

    def findings(self, run: RunId) -> list[Finding]: ...

    def record_run(self, run: ReviewRun) -> None: ...

    def record_models(self, run: RunId, models: Mapping[str, str | None]) -> None: ...

    def record_findings(self, run: RunId, findings: Iterable[Finding]) -> list[Duplicate]: ...


@runtime_checkable
class ReviewStore(Protocol):
    def transaction(self) -> AbstractContextManager[ReviewRepository]: ...
