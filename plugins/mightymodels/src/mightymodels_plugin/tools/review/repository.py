"""Review runs, their findings, the user's decisions and the fix outcomes, behind one repository.

`SqliteReviewStore` is the review store over the database: its `transaction` opens one and hands
out the review repository, so the review service never sees a session, and `review_store` builds
it as the `ReviewStore` a service holds. The repository also carries a `SqliteTicketRepository` on
that same session, which no caller reads and which is no part of the `ReviewRepository` a service
sees. Each repository here holds the key of the git repository the database was opened for, and
every read, write and delete is under that key.

The user's decisions and the fix outcomes sit on a `SqliteDecisionRepository` that the review
repository carries the same way. Its `reopen` is the only delete here: the findings it is given
lose their decision and their outcome and read as undecided again.

A run's findings, decisions and outcomes are each read whole, the findings in the order of their
numbers, and a read is refused once a run holds more than `FINDINGS`. `latest_runs` lists the
newest runs, oldest first, and no more than `RUNS_LISTED` of them.

No row leaves a repository here: `run_of`, `finding_of`, `decided_of` and `resolved_of` map each
row to the value a read hands out. A stored decision and a stored evidence are read back as they
are and not validated as requests.

Recording findings also stores each title in the similarity table in the same transaction, under
the run and the finding's id, and answers the near-duplicates of earlier rows that the titles
turned up. A finding that merges into a recorded one replaces its title there.

A write of findings, decisions or an outcome is refused with `WriteLimitError` when the run would
hold more than `FINDINGS` of them, and then stores none of what it was given. `write_error` counts
what the run holds of one row type once the write is flushed.

A method that writes takes values and builds the rows itself.
"""

from collections.abc import Collection, Generator, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

import sqlalchemy as sql
from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database, Latest, ReadLimit, WriteLimitError
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.review.errors import RunNotFoundError
from mightymodels_plugin.tools.review.schema import (
    Decision,
    Emphasis,
    Evidence,
    EvidenceKind,
    Finding,
    Kind,
    Persona,
    Result,
    ReviewRun,
    ReviewScope,
    Severity,
)
from mightymodels_plugin.tools.review.store import DecidedFinding, ResolvedFinding, ReviewStore
from mightymodels_plugin.tools.review.tables import (
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels_plugin.tools.similarity.repository import SqliteSimilarityRepository
from mightymodels_plugin.tools.similarity.schema import Duplicate, SimilarityKind
from mightymodels_plugin.tools.similarity.store import Written
from mightymodels_plugin.tools.ticket.repository import SqliteTicketRepository

type RowOfARun = ReviewFindingRow | ReviewDispositionRow | ReviewOutcomeRow

FINDINGS = ReadLimit(rows=1000, kept='findings')
RUNS_LISTED = ReadLimit(rows=50, kept='review runs')


def run_of(row: ReviewRunRow) -> ReviewRun:
    return ReviewRun(
        run_id=RunId(row.run_id),
        slug=None if row.slug is None else Slug(row.slug),
        scope=ReviewScope(row.scope),
        base=row.base,
        head=row.head,
        depth=Depth(row.depth),
        emphasis=Emphasis(row.emphasis),
        weights={Persona(persona): weight for persona, weight in row.weights.items()},
        personas=tuple(map(Persona, row.personas)),
        models=dict(row.models),
        created_at=row.created_at,
    )


def evidence_of(row: ReviewFindingRow) -> Evidence | None:
    if row.evidence_kind is None:
        return None
    cite = '' if row.evidence_cite is None else row.evidence_cite
    return Evidence.model_construct(kind=EvidenceKind(row.evidence_kind), cite=cite)


def finding_of(row: ReviewFindingRow) -> Finding:
    return Finding(
        id=row.finding_id,
        sources=tuple(row.sources),
        severity=Severity(row.severity),
        kind=Kind(row.kind),
        security=row.security,
        title=row.title,
        location=row.location,
        fix=row.fix,
        verify=row.verify,
        evidence=evidence_of(row),
        conflict=row.conflict,
    )


def decided_of(row: ReviewDispositionRow) -> DecidedFinding:
    return DecidedFinding(
        finding_id=row.finding_id,
        decision=Decision(row.decision),
        reason=row.reason,
        by=row.by,
        at=row.at,
    )


def resolved_of(row: ReviewOutcomeRow) -> ResolvedFinding:
    return ResolvedFinding(
        finding_id=row.finding_id,
        result=Result(row.result),
        commit=row.commit,
        reason=row.reason,
        at=row.at,
    )


def run_row_of(run: ReviewRun, *, repository_key: RepositoryKey) -> ReviewRunRow:
    return ReviewRunRow(
        repository_key=repository_key.root,
        run_id=run.run_id.root,
        slug=None if run.slug is None else run.slug.root,
        scope=run.scope,
        base=run.base,
        head=run.head,
        depth=run.depth,
        emphasis=run.emphasis,
        weights={persona.value: weight for persona, weight in run.weights.items()},
        personas=[persona.value for persona in run.personas],
        models=dict(run.models),
        created_at=run.created_at,
    )


def finding_row_of(
    run: RunId, finding: Finding, *, repository_key: RepositoryKey
) -> ReviewFindingRow:
    evidence = finding.evidence
    return ReviewFindingRow(
        repository_key=repository_key.root,
        run_id=run.root,
        finding_id=finding.id,
        sources=list(finding.sources),
        severity=finding.severity,
        kind=finding.kind,
        security=finding.security,
        title=finding.title,
        location=finding.location,
        fix=finding.fix,
        verify=finding.verify,
        evidence_kind=None if evidence is None else evidence.kind,
        evidence_cite=None if evidence is None else evidence.cite,
        conflict=finding.conflict,
    )


def written_finding(run: RunId, finding: Finding) -> Written:
    return Written(
        kind=SimilarityKind.REVIEW_FINDING, reference=f'{run} {finding.id}', text=finding.title
    )


def disposition_row_of(
    run: RunId, decided: DecidedFinding, *, repository_key: RepositoryKey
) -> ReviewDispositionRow:
    return ReviewDispositionRow(
        repository_key=repository_key.root,
        run_id=run.root,
        finding_id=decided.finding_id,
        decision=decided.decision,
        reason=decided.reason,
        by=decided.by,
        at=decided.at,
    )


def outcome_row_of(
    run: RunId, resolved: ResolvedFinding, *, repository_key: RepositoryKey
) -> ReviewOutcomeRow:
    return ReviewOutcomeRow(
        repository_key=repository_key.root,
        run_id=run.root,
        finding_id=resolved.finding_id,
        result=resolved.result,
        commit=resolved.commit,
        reason=resolved.reason,
        at=resolved.at,
    )


def write_error(
    session: Session, row_type: type[RowOfARun], run: RunId, *, repository_key: RepositoryKey
) -> WriteLimitError | None:
    session.flush()
    held = (
        sql.select(sql.func.count())
        .select_from(row_type)
        .where(row_type.repository_key == repository_key.root, row_type.run_id == run.root)
    )
    return FINDINGS.write_error(session.scalars(held).one(), owner=f'run {run}')


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteDecisionRepository:
    session: Session
    repository_key: RepositoryKey

    def dispositions(self, run: RunId) -> list[DecidedFinding]:
        query = (
            sql.select(ReviewDispositionRow)
            .where(
                ReviewDispositionRow.repository_key == self.repository_key.root,
                ReviewDispositionRow.run_id == run.root,
            )
            .limit(FINDINGS.fetched)
        )
        rows = list(self.session.scalars(query))
        if (error := FINDINGS.error(rows, owner=f'run {run}')) is not None:
            raise error
        return list(map(decided_of, rows))

    def outcomes(self, run: RunId) -> list[ResolvedFinding]:
        query = (
            sql.select(ReviewOutcomeRow)
            .where(
                ReviewOutcomeRow.repository_key == self.repository_key.root,
                ReviewOutcomeRow.run_id == run.root,
            )
            .limit(FINDINGS.fetched)
        )
        rows = list(self.session.scalars(query))
        if (error := FINDINGS.error(rows, owner=f'run {run}')) is not None:
            raise error
        return list(map(resolved_of, rows))

    def record_dispositions(self, run: RunId, decided: Iterable[DecidedFinding]) -> None:
        for decision in decided:
            self.session.merge(
                disposition_row_of(run, decision, repository_key=self.repository_key)
            )
        error = write_error(
            self.session, ReviewDispositionRow, run, repository_key=self.repository_key
        )
        if error is not None:
            raise error

    def record_outcome(self, run: RunId, resolved: ResolvedFinding) -> None:
        self.session.merge(outcome_row_of(run, resolved, repository_key=self.repository_key))
        error = write_error(self.session, ReviewOutcomeRow, run, repository_key=self.repository_key)
        if error is not None:
            raise error

    def reopen(self, run: RunId, finding_ids: Collection[str]) -> None:
        for row_type in (ReviewDispositionRow, ReviewOutcomeRow):
            reopened = sql.delete(row_type).where(
                row_type.repository_key == self.repository_key.root,
                row_type.run_id == run.root,
                row_type.finding_id.in_(finding_ids),
            )
            self.session.execute(reopened)


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteReviewRepository:
    session: Session
    repository_key: RepositoryKey
    tickets: SqliteTicketRepository
    decisions: SqliteDecisionRepository

    def _run_row(self, run: RunId) -> ReviewRunRow | None:
        return self.session.get(ReviewRunRow, (self.repository_key.root, run.root))

    def _started_run_row(self, run: RunId) -> ReviewRunRow:
        row = self._run_row(run)
        if row is None:
            raise RunNotFoundError(run)
        return row

    def run(self, run: RunId) -> ReviewRun | None:
        row = self._run_row(run)
        return None if row is None else run_of(row)

    def started_run(self, run: RunId) -> ReviewRun:
        return run_of(self._started_run_row(run))

    def latest_runs(self) -> Latest[ReviewRun]:
        query = (
            sql.select(ReviewRunRow)
            .where(ReviewRunRow.repository_key == self.repository_key.root)
            .order_by(ReviewRunRow.run_id.desc())
            .limit(RUNS_LISTED.fetched)
        )
        newest_first = [run_of(row) for row in self.session.scalars(query)]
        return RUNS_LISTED.latest(newest_first)

    def latest_run(self, slug: Slug) -> ReviewRun | None:
        query = (
            sql.select(ReviewRunRow)
            .where(
                ReviewRunRow.repository_key == self.repository_key.root,
                ReviewRunRow.slug == slug.root,
            )
            .order_by(ReviewRunRow.run_id.desc())
            .limit(1)
        )
        row = self.session.scalars(query).first()
        return None if row is None else run_of(row)

    def findings(self, run: RunId) -> list[Finding]:
        query = (
            sql.select(ReviewFindingRow)
            .where(
                ReviewFindingRow.repository_key == self.repository_key.root,
                ReviewFindingRow.run_id == run.root,
            )
            .order_by(sql.func.length(ReviewFindingRow.finding_id), ReviewFindingRow.finding_id)
            .limit(FINDINGS.fetched)
        )
        rows = list(self.session.scalars(query))
        if (error := FINDINGS.error(rows, owner=f'run {run}')) is not None:
            raise error
        return list(map(finding_of, rows))

    def record_run(self, run: ReviewRun) -> None:
        self.session.add(run_row_of(run, repository_key=self.repository_key))

    def record_models(self, run: RunId, models: Mapping[str, str | None]) -> None:
        self._started_run_row(run).models = dict(models)

    def record_findings(self, run: RunId, findings: Iterable[Finding]) -> list[Duplicate]:
        recorded = list(findings)
        for finding in recorded:
            self.session.merge(finding_row_of(run, finding, repository_key=self.repository_key))
        error = write_error(self.session, ReviewFindingRow, run, repository_key=self.repository_key)
        if error is not None:
            raise error
        similarity = SqliteSimilarityRepository(
            session=self.session, repository_key=self.repository_key
        )
        return similarity.record_all(written_finding(run, finding) for finding in recorded)


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteReviewStore:
    database: Database

    @contextmanager
    def transaction(self) -> Generator[SqliteReviewRepository]:
        with self.database.transaction() as session:
            repository_key = self.database.repository_key
            yield SqliteReviewRepository(
                session=session,
                repository_key=repository_key,
                tickets=SqliteTicketRepository(session=session, repository_key=repository_key),
                decisions=SqliteDecisionRepository(session=session, repository_key=repository_key),
            )


def review_store(database: Database) -> ReviewStore:
    return SqliteReviewStore(database=database)
