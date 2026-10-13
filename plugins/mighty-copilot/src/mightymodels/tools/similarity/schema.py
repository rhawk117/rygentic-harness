"""Arguments, results and the spool file of the `similarity` tool.

`SimilarityKind` is the type column of the similarity table: the four kinds of text the plugin can
tell apart from one another. `SpooledReport` is the content of one file in the scout-report spool,
parsed as a request model because the file is written by a process the server does not control.
`Match` is a stored row as a text resembles it, and `Duplicate` pairs a text just written with the
earlier row it resembles.
"""

from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from mightymodels.core.declarative import REPORT_LIMIT
from mightymodels.core.repository_key import RepositoryKey
from mightymodels.tools.request import NameText, ProseText, RequestModel

type ReportText = Annotated[str, StringConstraints(pattern=r'\S', max_length=REPORT_LIMIT)]


class SimilarityAction(StrEnum):
    SEARCH = auto()


class SimilarityKind(StrEnum):
    LEDGER_ENTRY = 'ledger-entry'
    SCOUT_REPORT = 'scout-report'
    REVIEW_FINDING = 'review-finding'
    CRASHOUT = auto()


class SimilarityRequest(RequestModel):
    action: Literal[SimilarityAction.SEARCH]
    query: ProseText
    kind: SimilarityKind | None = None


class Scout(StrEnum):
    CODE_SCOUT = 'code-scout'
    WEB_SCOUT = 'web-scout'


class SpooledReport(RequestModel):
    repository_key: RepositoryKey
    scout: Scout
    target: NameText
    report: ReportText


class Match(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: SimilarityKind
    reference: str
    text: str
    overlap: float


@dataclass(slots=True, kw_only=True, frozen=True)
class Duplicate:
    written: str
    earlier: Match


class SimilarityView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    matches: tuple[Match, ...] = ()
