"""The `tasks`, `task_attempts`, `task_failed_fixes` and `task_transitions` tables.

A task, who tried it, each fix that failed with the hypothesis it tested, each move.

A task belongs to a staged ticket, and an attempt, a failed fix and a transition belong to a task.
"""

from typing import Annotated

import sqlalchemy as sql
from sqlalchemy.orm import Mapped, mapped_column

from mightymodels_plugin.core.declarative import (
    TASK_ID_LIMIT,
    Base,
    Name,
    Prose,
    RepositoryKeyPart,
    RepositoryName,
    Serial,
    Sha,
    SlugKeyPart,
    SlugName,
    TaskName,
    Texts,
    TextsIfAny,
    Timestamp,
    Word,
    child_of,
)
from mightymodels_plugin.tools.ticket.tables import TicketRow

type TaskKeyPart = Annotated[str, mapped_column(sql.String(TASK_ID_LIMIT), primary_key=True)]


class TaskRow(Base):
    __tablename__ = 'tasks'
    __table_args__ = (child_of(TicketRow),)

    repository_key: Mapped[RepositoryKeyPart]
    slug: Mapped[SlugKeyPart]
    task_id: Mapped[TaskKeyPart]
    status: Mapped[Word]
    owned: Mapped[Texts]
    base: Mapped[Sha | None]
    commit: Mapped[Name | None]
    reasons: Mapped[TextsIfAny]
    updated_at: Mapped[Timestamp]


class AttemptRow(Base):
    __tablename__ = 'task_attempts'
    __table_args__ = (
        child_of(TaskRow),
        sql.Index('ix_task_attempts_task_mode', 'repository_key', 'slug', 'task_id', 'mode'),
    )

    id: Mapped[Serial]
    repository_key: Mapped[RepositoryName]
    slug: Mapped[SlugName]
    task_id: Mapped[TaskName]
    worker: Mapped[Word]
    mode: Mapped[Word | None]
    at: Mapped[Timestamp]


class FailedFixRow(Base):
    __tablename__ = 'task_failed_fixes'
    __table_args__ = (
        child_of(TaskRow),
        sql.Index('ix_task_failed_fixes_task', 'repository_key', 'slug', 'task_id'),
    )

    id: Mapped[Serial]
    repository_key: Mapped[RepositoryName]
    slug: Mapped[SlugName]
    task_id: Mapped[TaskName]
    hypothesis: Mapped[Prose]
    at: Mapped[Timestamp]


class TransitionRow(Base):
    __tablename__ = 'task_transitions'
    __table_args__ = (
        child_of(TaskRow),
        sql.Index('ix_task_transitions_after', 'repository_key', 'slug', 'after'),
    )

    id: Mapped[Serial]
    repository_key: Mapped[RepositoryName]
    slug: Mapped[SlugName]
    task_id: Mapped[TaskName]
    before: Mapped[Word]
    after: Mapped[Word]
    reasons: Mapped[Texts]
    head: Mapped[Sha | None]
    at: Mapped[Timestamp]
