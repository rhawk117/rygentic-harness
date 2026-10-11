"""Arguments and results of the `task` tool."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.task_id import TASK_ID_PATTERN
from mightymodels_plugin.tools.request import NameText, ProseText, RequestModel

type TaskId = Annotated[str, StringConstraints(pattern=TASK_ID_PATTERN)]
type OwnedFiles = Annotated[tuple[ProseText, ...], Field(min_length=1)]
type Assertions = dict[ProseText, ProseText]


class TaskAction(StrEnum):
    START = 'start'
    VERIFY = 'verify'
    MARK = 'mark'
    SHOW = 'show'
    READY = 'ready'


class Status(StrEnum):
    PENDING = 'pending'
    IN_PROGRESS = 'in-progress'
    VERIFIED = 'verified'
    FAILED = 'failed'
    BLOCKED = 'blocked'
    SUPERSEDED = 'superseded'


class Implementer(StrEnum):
    ENGINEER = 'engineer'
    ARCHITECT = 'architect'


class ArchitectMode(StrEnum):
    RECOVERY_IMPLEMENTATION = 'recovery-implementation'
    SYSTEMIC_REFACTOR = 'systemic-refactor'
    DIAGNOSE_REPLAN = 'diagnose-replan'


type Markable = Literal[Status.FAILED, Status.BLOCKED, Status.SUPERSEDED]


class TaskStart(RequestModel):
    by: Implementer
    owned: OwnedFiles
    mode: ArchitectMode | None = None


class TaskVerification(RequestModel):
    commit: NameText
    assertions: Assertions = Field(default_factory=dict)


class TaskMark(RequestModel):
    to: Markable
    reason: ProseText


class StartTaskPayload(RequestModel):
    task_id: TaskId
    change: TaskStart


class VerifyTaskPayload(RequestModel):
    task_id: TaskId
    change: TaskVerification


class MarkTaskPayload(RequestModel):
    task_id: TaskId
    change: TaskMark


class StartTask(RequestModel):
    action: Literal[TaskAction.START]
    slug: Slug
    payload: StartTaskPayload


class VerifyTask(RequestModel):
    action: Literal[TaskAction.VERIFY]
    slug: Slug
    payload: VerifyTaskPayload


class MarkTask(RequestModel):
    action: Literal[TaskAction.MARK]
    slug: Slug
    payload: MarkTaskPayload


class ShowTask(RequestModel):
    action: Literal[TaskAction.SHOW]
    slug: Slug


class ReadyTask(RequestModel):
    action: Literal[TaskAction.READY]
    slug: Slug


type TaskRequest = Annotated[
    StartTask | VerifyTask | MarkTask | ShowTask | ReadyTask, Field(discriminator='action')
]


class TaskRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: Status
    owned: tuple[str, ...] = ()
    base: str | None = None
    commit: str | None = None
    attempts: dict[str, int] = Field(default_factory=dict)
    reasons: tuple[str, ...] = ()


class TaskView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    advanced: bool
    tasks: tuple[TaskRecord, ...] = ()
