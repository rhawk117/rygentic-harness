"""The similarity service: search over everything the plugin has stored, and the scout-report spool.

`search` answers the stored rows that share a content word with a query, best BM25 rank first, at
most `CANDIDATE_CAP` of them, each with its overlap with the query, and it can be held to one kind.
It applies no threshold: a query is usually a part of what it looks for.

`take_in_spool` stores the scout reports waiting in the spool for this repository, each with its
similarity row in one transaction, and removes the file. Only the files named with this
repository's digest are listed, so a file for another repository is never opened. A file that is
not a report, that names another repository, or that redaction lengthens past its column, is set
aside and the call goes on. A scout's closing text is dropped when the report of that scout and
target is already stored, so a handed-back report wins. The spool and its file format are in
`spool.py`.

The service reads and writes its store and the spool and nothing else. It is built with the key of
the repository it serves, which names the spool files it takes in.
"""

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from mightymodels_plugin.core.repository_key import RepositoryKey, spool_file_prefix
from mightymodels_plugin.redaction import RedactedTextTooLongError
from mightymodels_plugin.tools.similarity.rendering import matches_text
from mightymodels_plugin.tools.similarity.schema import (
    SimilarityKind,
    SimilarityView,
    SpooledReport,
)
from mightymodels_plugin.tools.similarity.spool import (
    is_closing_text,
    set_aside,
    spooled_report,
    waiting_files,
)
from mightymodels_plugin.tools.similarity.store import SimilarityStore


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityService:
    store: SimilarityStore
    spool: Path
    repository_key: RepositoryKey

    def search(self, query: str, kind: SimilarityKind | None) -> SimilarityView:
        with self.store.transaction() as repository:
            matches = tuple(repository.search(query, kind=kind))
        return SimilarityView(text=matches_text(matches), matches=matches)

    def store_report(self, report: SpooledReport) -> RedactedTextTooLongError | None:
        try:
            with self.store.transaction() as repository:
                repository.add_scout_report(report)
        except RedactedTextTooLongError as error:
            return error
        return None

    def has_report_of(self, report: SpooledReport) -> bool:
        with self.store.transaction() as repository:
            return repository.has_scout_report(report)

    def take_in(self, file: Path) -> None:
        report = spooled_report(file)
        if report is None or report.repository_key != self.repository_key:
            set_aside(file, self.spool)
            return
        prefix = spool_file_prefix(self.repository_key)
        if is_closing_text(file, prefix) and self.has_report_of(report):
            file.unlink()
            return
        if self.store_report(report) is not None:
            set_aside(file, self.spool)
            return
        file.unlink()

    def take_in_spool(self) -> None:
        for file in waiting_files(self.spool, spool_file_prefix(self.repository_key)):
            with suppress(FileNotFoundError):
                self.take_in(file)
