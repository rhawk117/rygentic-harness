"""Whether a contract command's latest receipt counts at the current HEAD.

`verify status`, the snapshot and the task gate judge a receipt here and nowhere else, so the
three cannot disagree. A command has never run, or its latest receipt is stale, or it is at HEAD.
A receipt is at HEAD only when HEAD is known and is the head the receipt was taken at. While there
is no HEAD, in a repository before its first commit, no receipt is at it: every receipt is stale,
and one taken with no HEAD reads as taken at `unknown`.

The assessment holds plain values, a receipt's outcome and head and the current HEAD, and no row,
so it judges a receipt whatever the caller read it from.
"""

from dataclasses import dataclass
from enum import StrEnum, auto

from mightymodels.head import short_head

NEVER_RUN = 'never-run'


class ReceiptState(StrEnum):
    NEVER_RUN = auto()
    STALE = auto()
    AT_HEAD = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class Taken:
    outcome: str
    head: str | None


def is_at_head(taken_at: str | None, head: str | None) -> bool:
    return head is not None and taken_at == head


@dataclass(slots=True, kw_only=True, frozen=True)
class Assessment:
    taken: Taken | None
    head: str | None

    @property
    def state(self) -> ReceiptState:
        if self.taken is None:
            return ReceiptState.NEVER_RUN
        at_head = is_at_head(self.taken.head, self.head)
        return ReceiptState.AT_HEAD if at_head else ReceiptState.STALE

    @property
    def outcome_at_head(self) -> str | None:
        if self.taken is None or self.state is not ReceiptState.AT_HEAD:
            return None
        return self.taken.outcome

    @property
    def text(self) -> str:
        if self.taken is None:
            return NEVER_RUN
        if self.state is ReceiptState.STALE:
            return f'stale ({self.taken.outcome} at {short_head(self.taken.head)})'
        return self.taken.outcome
