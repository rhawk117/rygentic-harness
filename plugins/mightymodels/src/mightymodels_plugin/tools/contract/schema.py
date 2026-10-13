"""Arguments and results of the `contract` tool, and what `verify run` executes and records.

`ApprovedCommand` is a command as the contract holds it, the only thing `verify run` executes, and
`Receipt` is the record of one run of it.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from mightymodels_plugin.core.declarative import NAME_LIMIT
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.request import NameText, ProseText, RequestModel

COMMAND_ID_PATTERN = r'^[A-Za-z0-9._-]+$'
DEFAULT_TIMEOUT = 300
MAX_TIMEOUT = 3600
USER_APPROVER = 'user'


class ShellStringError(ValueError):
    def __init__(self) -> None:
        super().__init__('argv must be a non-empty list of strings; no shell string')


def checked_argv(value: object) -> object:
    is_list = isinstance(value, (list, tuple)) and bool(value)
    if not is_list or not all(isinstance(argument, str) for argument in value):
        raise ShellStringError
    return value


type CommandId = Annotated[
    str, StringConstraints(pattern=COMMAND_ID_PATTERN, max_length=NAME_LIMIT)
]
type Argv = Annotated[tuple[ProseText, ...], BeforeValidator(checked_argv)]
type Timeout = Annotated[int, Field(ge=1, le=MAX_TIMEOUT)]


class ContractAction(StrEnum):
    APPROVE = 'approve'
    STATUS = 'status'


class ApprovalChoice(StrEnum):
    APPROVE = 'approve'
    REMOVE = 'remove'
    EDIT = 'edit'


class Phase(StrEnum):
    PLANNING = 'planning'
    TASK = 'task'
    REVIEW = 'review'
    LANDING = 'landing'


class Outcome(StrEnum):
    PASSED = 'pass'
    FAILED = 'fail'
    TIMEOUT = 'timeout'
    NOT_FOUND = 'not-found'
    REFUSED = 'refused'
    UNDECODABLE = 'undecodable'


class ContractCommand(RequestModel):
    id: CommandId
    argv: Argv
    expect_exit: int = 0
    timeout: Timeout = DEFAULT_TIMEOUT
    approved_by: NameText = ''


class ApproveContract(RequestModel):
    action: Literal[ContractAction.APPROVE]
    slug: Slug
    commands: list[ContractCommand]


class StatusContract(RequestModel):
    action: Literal[ContractAction.STATUS]
    slug: Slug


type ContractRequest = Annotated[ApproveContract | StatusContract, Field(discriminator='action')]


class CommandState(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    argv: tuple[str, ...]
    state: str


class ContractView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    passing: bool
    commands: tuple[CommandState, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovedCommand:
    id: str
    argv: tuple[str, ...]
    expect_exit: int
    timeout: int


@dataclass(slots=True, kw_only=True, frozen=True)
class Receipt:
    id: str
    argv: tuple[str, ...]
    outcome: Outcome
    exit: int | None
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    digest: str
    head: str | None
    phase: Phase
    at: str
