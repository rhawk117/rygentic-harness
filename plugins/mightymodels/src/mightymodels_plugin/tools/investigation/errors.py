"""Every failure the investigation service reports, one class each."""

from collections.abc import Sequence

from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.investigation.schema import EntryKind, Source


class UnknownInvestigationError(StateError):
    def __init__(self, investigation: Slug) -> None:
        super().__init__(f'no investigation named {investigation.root!r}; run list')
        self.investigation = investigation


class RoundRegressionError(StateError):
    def __init__(self, given: int, latest: int) -> None:
        super().__init__(f'round {given} is earlier than the latest round {latest}')
        self.given = given
        self.latest = latest


class InvalidEntryError(StateError):
    def __init__(self, index: int, reason: str) -> None:
        super().__init__(f'entry {index}: {reason}')
        self.index = index
        self.reason = reason


class EmptyTextError(InvalidEntryError):
    def __init__(self, index: int) -> None:
        super().__init__(index, 'text is empty')


class WrittenByStartError(InvalidEntryError):
    def __init__(self, index: int, kind: EntryKind) -> None:
        super().__init__(index, f'kind {kind} cannot be added; it is written by start')
        self.kind = kind


class CiteRequiredError(InvalidEntryError):
    def __init__(self, index: int, kind: EntryKind) -> None:
        super().__init__(index, f'a {kind} entry needs a cite (file:line, URL#heading, or path)')
        self.kind = kind


class SourceNotAllowedError(InvalidEntryError):
    def __init__(self, index: int, kind: EntryKind, source: Source) -> None:
        super().__init__(index, f'a {kind} entry cannot come from {source}')
        self.kind = kind
        self.source = source


class UnknownSupersededError(InvalidEntryError):
    def __init__(self, index: int, unknown: Sequence[int]) -> None:
        super().__init__(index, f'supersedes unknown entries {list(unknown)}')
        self.unknown = unknown
