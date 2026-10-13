"""The review store kept in memory: runs, their findings, the user's decisions and the outcomes.

It is built on the similarity store kept in memory, and its transaction opens that one's, so a
finding and its title's text are kept together as the SQLite repository stores them in one
transaction. A transaction works on a copy and keeps it only when its block ends without an error.

A run is held as it reads back from a row, its weights and models as plain dicts. Findings read
in the order of their numbers, and `latest_runs` is held to `RUNS_LISTED` as the SQLite read is.
No run is held to `FINDINGS`, and nothing here checks that a finding's run or a decision's finding
exists, which the database does when a transaction commits.
"""

from collections.abc import Collection, Generator, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from operator import attrgetter

from mightymodels_plugin.core.database import Latest
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.review.errors import RunNotFoundError
from mightymodels_plugin.tools.review.repository import RUNS_LISTED, written_finding
from mightymodels_plugin.tools.review.schema import Finding, ReviewRun
from mightymodels_plugin.tools.review.store import DecidedFinding, ResolvedFinding
from mightymodels_plugin.tools.similarity.schema import Duplicate
from mightymodels_plugin.tools.similarity.tests.in_memory import (
    InMemorySimilarityRepository,
    InMemorySimilarityStore,
)

type FindingKey = tuple[RunId, str]

NEWEST_RUN = attrgetter('run_id.root')


def as_stored(run: ReviewRun) -> ReviewRun:
    return replace(
        run, weights=dict(run.weights), personas=tuple(run.personas), models=dict(run.models)
    )


def number_order(finding: Finding) -> tuple[int, str]:
    return len(finding.id), finding.id


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryDecisionRepository:
    decided: dict[FindingKey, DecidedFinding]
    resolved: dict[FindingKey, ResolvedFinding]

    def dispositions(self, run: RunId) -> list[DecidedFinding]:
        return [decision for (owner, _), decision in self.decided.items() if owner == run]

    def outcomes(self, run: RunId) -> list[ResolvedFinding]:
        return [outcome for (owner, _), outcome in self.resolved.items() if owner == run]

    def record_dispositions(self, run: RunId, decided: Iterable[DecidedFinding]) -> None:
        self.decided.update({(run, decision.finding_id): decision for decision in decided})

    def record_outcome(self, run: RunId, resolved: ResolvedFinding) -> None:
        self.resolved[run, resolved.finding_id] = resolved

    def reopen(self, run: RunId, finding_ids: Collection[str]) -> None:
        for finding_id in finding_ids:
            self.decided.pop((run, finding_id), None)
            self.resolved.pop((run, finding_id), None)


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryReviewRepository:
    runs: dict[RunId, ReviewRun]
    found: dict[FindingKey, Finding]
    decisions: InMemoryDecisionRepository
    similarity: InMemorySimilarityRepository

    def run(self, run: RunId) -> ReviewRun | None:
        return self.runs.get(run)

    def started_run(self, run: RunId) -> ReviewRun:
        started = self.run(run)
        if started is None:
            raise RunNotFoundError(run)
        return started

    def latest_runs(self) -> Latest[ReviewRun]:
        return RUNS_LISTED.latest(sorted(self.runs.values(), key=NEWEST_RUN, reverse=True))

    def latest_run(self, slug: Slug) -> ReviewRun | None:
        of_the_ticket = (run for run in self.runs.values() if run.slug == slug)
        return max(of_the_ticket, key=NEWEST_RUN, default=None)

    def findings(self, run: RunId) -> list[Finding]:
        of_the_run = (finding for (owner, _), finding in self.found.items() if owner == run)
        return sorted(of_the_run, key=number_order)

    def record_run(self, run: ReviewRun) -> None:
        self.runs[run.run_id] = as_stored(run)

    def record_models(self, run: RunId, models: Mapping[str, str | None]) -> None:
        self.runs[run] = replace(self.started_run(run), models=dict(models))

    def record_findings(self, run: RunId, findings: Iterable[Finding]) -> list[Duplicate]:
        recorded = list(findings)
        self.found.update({(run, finding.id): finding for finding in recorded})
        return self.similarity.record_all(written_finding(run, finding) for finding in recorded)


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryReviewStore:
    similarity: InMemorySimilarityStore
    runs: dict[RunId, ReviewRun] = field(default_factory=dict)
    found: dict[FindingKey, Finding] = field(default_factory=dict)
    decided: dict[FindingKey, DecidedFinding] = field(default_factory=dict)
    resolved: dict[FindingKey, ResolvedFinding] = field(default_factory=dict)

    @contextmanager
    def transaction(self) -> Generator[InMemoryReviewRepository]:
        with self.similarity.transaction() as similarity:
            decisions = InMemoryDecisionRepository(
                decided=dict(self.decided), resolved=dict(self.resolved)
            )
            working = InMemoryReviewRepository(
                runs=dict(self.runs),
                found=dict(self.found),
                decisions=decisions,
                similarity=similarity,
            )
            yield working
            self.runs.clear()
            self.runs.update(working.runs)
            self.found.clear()
            self.found.update(working.found)
            self.decided.clear()
            self.decided.update(decisions.decided)
            self.resolved.clear()
            self.resolved.update(decisions.resolved)
