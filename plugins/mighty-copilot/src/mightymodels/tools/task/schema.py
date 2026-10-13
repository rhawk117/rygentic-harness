"""Arguments and results of the `task` tool.

A start names the task's acceptance criteria beside its owned files, so that both can be counted.
It is one of two shapes, told apart by `TOO_LARGE_APPROVAL`. `TaskStart` holds a task to
`ACCEPTANCE_BOUND` and `OWNED_BOUND`, and a start over either is refused with the name of
`SPLITTING_SKILL`, the skill that splits the task and puts the split to the user.
`TooLargeTaskStart` is the start of a task the user chose to keep whole: it names that approval
and has no upper bound.
"""

from collections.abc import Mapping, Sized
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    StringConstraints,
    Tag,
)

from mightymodels.core.slug import Slug
from mightymodels.core.task_id import TASK_ID_PATTERN
from mightymodels.tools.request import NameText, ProseText, RequestModel

SPLITTING_SKILL = 'break-it-down'
TOO_LARGE_APPROVAL = 'too_large_approved_by'


class TaskTooLargeError(ValueError):
    def __init__(self, counted: str, count: int, limit: int) -> None:
        super().__init__(
            f'{count} {counted} is over the {limit} one task may have; split the task with '
            f'{SPLITTING_SKILL}, which puts the split to the user'
        )
        self.counted = counted
        self.count = count
        self.limit = limit


@dataclass(slots=True, kw_only=True, frozen=True)
class SizeBound:
    counted: str
    limit: int

    def error(self, listed: Sized) -> TaskTooLargeError | None:
        if len(listed) <= self.limit:
            return None
        return TaskTooLargeError(self.counted, len(listed), self.limit)

    def __call__(self, listed: tuple[str, ...]) -> tuple[str, ...]:
        if (error := self.error(listed)) is not None:
            raise error
        return listed


ACCEPTANCE_BOUND = SizeBound(counted='acceptance criteria', limit=4)
OWNED_BOUND = SizeBound(counted='owned files', limit=10)

type TaskId = Annotated[str, StringConstraints(pattern=TASK_ID_PATTERN)]
type OwnedFiles = Annotated[tuple[ProseText, ...], Field(min_length=1)]
type AcceptanceCriteria = Annotated[tuple[ProseText, ...], Field(min_length=1)]
type BoundedOwnedFiles = Annotated[
    tuple[ProseText, ...],
    Field(min_length=1, json_schema_extra={'maxItems': OWNED_BOUND.limit}),
    AfterValidator(OWNED_BOUND),
]
type BoundedAcceptanceCriteria = Annotated[
    tuple[ProseText, ...],
    Field(min_length=1, json_schema_extra={'maxItems': ACCEPTANCE_BOUND.limit}),
    AfterValidator(ACCEPTANCE_BOUND),
]
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
    INTERN = 'intern'


class ArchitectMode(StrEnum):
    RECOVERY_IMPLEMENTATION = 'recovery-implementation'
    SYSTEMIC_REFACTOR = 'systemic-refactor'
    DIAGNOSE_REPLAN = 'diagnose-replan'


class StartShape(StrEnum):
    BOUNDED = 'bounded'
    TOO_LARGE = 'too-large'


type Markable = Literal[Status.FAILED, Status.BLOCKED, Status.SUPERSEDED]


class TaskStart(RequestModel):
    by: Implementer
    owned: BoundedOwnedFiles
    acceptance: BoundedAcceptanceCriteria
    mode: ArchitectMode | None = None


class TooLargeTaskStart(RequestModel):
    by: Implementer
    owned: OwnedFiles
    acceptance: AcceptanceCriteria
    mode: ArchitectMode | None = None
    too_large_approved_by: Literal['user']


def start_shape(change: object) -> StartShape:
    if isinstance(change, Mapping):
        return StartShape.TOO_LARGE if TOO_LARGE_APPROVAL in change else StartShape.BOUNDED
    return StartShape.TOO_LARGE if hasattr(change, TOO_LARGE_APPROVAL) else StartShape.BOUNDED


type AnyTaskStart = Annotated[
    Annotated[TaskStart, Tag(StartShape.BOUNDED)]
    | Annotated[TooLargeTaskStart, Tag(StartShape.TOO_LARGE)],
    Discriminator(start_shape),
]


class TaskVerification(RequestModel):
    commit: NameText
    assertions: Assertions = Field(default_factory=dict)


class TaskMark(RequestModel):
    to: Markable
    reason: ProseText


class StartTaskPayload(RequestModel):
    task_id: TaskId
    change: AnyTaskStart


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
