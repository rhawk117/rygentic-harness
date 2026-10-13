"""Arguments and results of the `crashout` tool.

`CrashoutEntry` is one crashout as the caller reports it and `JournaledCrashout` is one as the
journal holds it, with the time it was journaled first. Both keep one field order, which is the
order the journal's text reads in.
"""

from enum import StrEnum, auto
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels_plugin.core.declarative import PROSE_LIMIT
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.request import NameText, RequestModel

type NotBlank = Annotated[str, StringConstraints(pattern=r'\S', max_length=PROSE_LIMIT)]
type Stripped = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PROSE_LIMIT)
]
type Failures = Annotated[tuple[NotBlank, ...], Field(min_length=1)]


class CrashoutAction(StrEnum):
    ADD = auto()
    STATS = auto()
    LAST = auto()


class Severity(StrEnum):
    MILD_TILT = 'mild-tilt'
    HEATED = 'heated'
    CRASHOUT = 'crashout'
    FULL_MELTDOWN = 'full-meltdown'


class Verdict(StrEnum):
    DESERVED = auto()
    SPLIT = auto()
    UNREASONABLE = auto()


class CrashoutEntry(RequestModel):
    ticket: Slug | None = None
    branch: NameText | None = None
    severity: Severity
    verdict: Verdict
    rant: NotBlank
    failures: Failures
    root_cause: Stripped
    corrective_action: Stripped
    barked_back: bool


class AddCrashout(RequestModel):
    action: Literal[CrashoutAction.ADD]
    entry: CrashoutEntry


class StatsCrashout(RequestModel):
    action: Literal[CrashoutAction.STATS]


class LastCrashout(RequestModel):
    action: Literal[CrashoutAction.LAST]


type CrashoutRequest = Annotated[
    AddCrashout | StatsCrashout | LastCrashout, Field(discriminator='action')
]


class JournaledCrashout(BaseModel):
    model_config = ConfigDict(frozen=True)

    at: str
    ticket: str | None
    branch: str | None
    severity: Severity
    verdict: Verdict
    rant: str
    failures: tuple[str, ...]
    root_cause: str
    corrective_action: str
    barked_back: bool


class CrashoutView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    entry: JournaledCrashout | None = None
