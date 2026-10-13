"""Arguments of the `failed_fix` tool, the one tool an engineer is allowed to call."""

from enum import StrEnum, auto
from typing import Literal

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.request import ProseText, RequestModel
from mightymodels_plugin.tools.task.schema import TaskId


class FailedFixAction(StrEnum):
    RECORD = auto()


class TaskFailedFix(RequestModel):
    hypothesis: ProseText


class FailedFixPayload(RequestModel):
    task_id: TaskId
    change: TaskFailedFix


class FailedFixRequest(RequestModel):
    action: Literal[FailedFixAction.RECORD]
    slug: Slug
    payload: FailedFixPayload
