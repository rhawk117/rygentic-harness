"""The similarity store kept in memory: the texts by kind and reference, and the scout reports.

It holds no index, no rank and no cap. A candidate is a stored text of the asked kind that shares
a content word with the query, scored by the same `overlap` the SQLite repository scores with, and
candidates come in the order their texts were first stored. A scout report's reference is its
place among the reports stored, as a row's id is in a database that holds one repository.

A transaction works on a copy and keeps it only when its block ends without an error. The stores
of the domains that write a text open this one's transaction inside their own, so a text and what
it belongs to are kept together or not at all.
"""

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field

from mightymodels_plugin.core.declarative import NAME_LIMIT, REPORT_LIMIT
from mightymodels_plugin.redaction import redact, redact_within
from mightymodels_plugin.tools.similarity.matching import content_words, overlap
from mightymodels_plugin.tools.similarity.repository import closest
from mightymodels_plugin.tools.similarity.schema import (
    Duplicate,
    Match,
    Scout,
    SimilarityKind,
    SpooledReport,
)
from mightymodels_plugin.tools.similarity.store import Written

type TextKey = tuple[SimilarityKind, str]


@dataclass(slots=True, kw_only=True, frozen=True)
class StoredReport:
    scout: Scout
    target: str
    report: str


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemorySimilarityRepository:
    texts: dict[TextKey, str]
    reports: list[StoredReport]

    def sharing_a_word(self, words: frozenset[str], kind: SimilarityKind | None) -> list[Match]:
        return [
            Match(
                kind=stored_kind,
                reference=reference,
                text=text,
                overlap=overlap(words, content_words(text)),
            )
            for (stored_kind, reference), text in self.texts.items()
            if kind in {None, stored_kind} and words & content_words(text)
        ]

    def search(self, query: str, *, kind: SimilarityKind | None) -> list[Match]:
        return self.sharing_a_word(content_words(query), kind)

    def record(self, written: Written) -> Duplicate | None:
        stored = redact_within(written.text, 'text', REPORT_LIMIT)
        key = (written.kind, written.reference)
        others = (
            match
            for match in self.sharing_a_word(content_words(stored), None)
            if (match.kind, match.reference) != key
        )
        earlier = closest(others)
        self.texts[key] = stored
        return None if earlier is None else Duplicate(written=written.reference, earlier=earlier)

    def record_all(self, writes: Iterable[Written]) -> list[Duplicate]:
        duplicates = [self.record(written) for written in writes]
        return [duplicate for duplicate in duplicates if duplicate is not None]

    def has_scout_report(self, report: SpooledReport) -> bool:
        target = redact(report.target)
        return any(
            stored.scout is report.scout and stored.target == target for stored in self.reports
        )

    def add_scout_report(self, report: SpooledReport) -> list[Duplicate]:
        stored = StoredReport(
            scout=report.scout,
            target=redact_within(report.target, 'target', NAME_LIMIT),
            report=redact_within(report.report, 'report', REPORT_LIMIT),
        )
        self.reports.append(stored)
        written = Written(
            kind=SimilarityKind.SCOUT_REPORT, reference=str(len(self.reports)), text=stored.report
        )
        return self.record_all([written])


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemorySimilarityStore:
    texts: dict[TextKey, str] = field(default_factory=dict)
    reports: list[StoredReport] = field(default_factory=list)

    @contextmanager
    def transaction(self) -> Generator[InMemorySimilarityRepository]:
        working = InMemorySimilarityRepository(texts=dict(self.texts), reports=list(self.reports))
        yield working
        self.texts.clear()
        self.texts.update(working.texts)
        self.reports[:] = working.reports
