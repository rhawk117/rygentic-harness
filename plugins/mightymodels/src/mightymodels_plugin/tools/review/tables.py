"""The `review_runs`, `review_findings`, `review_dispositions` and `review_outcomes` tables.

A run, the findings recorded for it, the user's decision per finding and the outcome of each fix.
A finding belongs to its run, a decision to its finding, and an outcome to the decision that chose
the finding for fixing. A run may name a ticket by a slug that is not staged, so no ticket row
stands behind it.

A finding's id is `F` and a number the server counts up, so `FINDING_ID_LIMIT` holds any count.
"""

from typing import Annotated

import sqlalchemy as sql
from sqlalchemy.orm import Mapped, mapped_column

from mightymodels_plugin.core.declarative import (
    NAME_LIMIT,
    PROSE_LIMIT,
    WORD_LIMIT,
    Base,
    Models,
    Name,
    Prose,
    RepositoryKeyPart,
    Sha,
    SlugName,
    Texts,
    Timestamp,
    Weights,
    Word,
    child_of,
)
from mightymodels_plugin.tools.review.schema import FINDING_ID_LIMIT, Kind

RUN_ID_LIMIT = 15

type RunKeyPart = Annotated[str, mapped_column(sql.String(RUN_ID_LIMIT), primary_key=True)]
type FindingKeyPart = Annotated[str, mapped_column(sql.String(FINDING_ID_LIMIT), primary_key=True)]
type DefectAtFirst = Annotated[
    str, mapped_column(sql.String(WORD_LIMIT), server_default=Kind.DEFECT)
]
type FalseAtFirst = Annotated[bool, mapped_column(server_default=sql.false())]
type ProseIfAny = Annotated[str, mapped_column(sql.String(PROSE_LIMIT), server_default='')]
type NameIfAny = Annotated[str, mapped_column(sql.String(NAME_LIMIT), server_default='')]


class ReviewRunRow(Base):
    __tablename__ = 'review_runs'
    __table_args__ = (sql.Index('ix_review_runs_slug', 'repository_key', 'slug', 'run_id'),)

    repository_key: Mapped[RepositoryKeyPart]
    run_id: Mapped[RunKeyPart]
    slug: Mapped[SlugName | None]
    scope: Mapped[Word]
    base: Mapped[Name | None]
    head: Mapped[Sha | None]
    depth: Mapped[Word]
    emphasis: Mapped[Word]
    weights: Mapped[Weights]
    personas: Mapped[Texts]
    models: Mapped[Models]
    created_at: Mapped[Timestamp]


class ReviewFindingRow(Base):
    __tablename__ = 'review_findings'
    __table_args__ = (child_of(ReviewRunRow),)

    repository_key: Mapped[RepositoryKeyPart]
    run_id: Mapped[RunKeyPart]
    finding_id: Mapped[FindingKeyPart]
    sources: Mapped[Texts]
    severity: Mapped[Word]
    kind: Mapped[DefectAtFirst]
    security: Mapped[FalseAtFirst]
    title: Mapped[Prose]
    location: Mapped[Prose]
    fix: Mapped[Prose]
    verify: Mapped[Prose]
    evidence_kind: Mapped[Word | None]
    evidence_cite: Mapped[Prose | None]
    conflict: Mapped[Prose | None]


class ReviewDispositionRow(Base):
    __tablename__ = 'review_dispositions'
    __table_args__ = (child_of(ReviewFindingRow),)

    repository_key: Mapped[RepositoryKeyPart]
    run_id: Mapped[RunKeyPart]
    finding_id: Mapped[FindingKeyPart]
    decision: Mapped[Word]
    reason: Mapped[ProseIfAny]
    by: Mapped[Name]
    at: Mapped[Timestamp]


class ReviewOutcomeRow(Base):
    __tablename__ = 'review_outcomes'
    __table_args__ = (child_of(ReviewDispositionRow),)

    repository_key: Mapped[RepositoryKeyPart]
    run_id: Mapped[RunKeyPart]
    finding_id: Mapped[FindingKeyPart]
    result: Mapped[Word]
    commit: Mapped[NameIfAny]
    reason: Mapped[ProseIfAny]
    at: Mapped[Timestamp]
