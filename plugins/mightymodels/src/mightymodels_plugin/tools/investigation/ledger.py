"""A ledger as it is read back: every entry of one investigation, in the order it was stored.

Nothing rewrites an entry. One is retired by a later entry that names it in `supersedes`, and
`Ledger.live` is what remains. The target is entry 1 and no entry may retire it.

A snapshot and a closing read the ledgers a ticket links, so `ledger_of` takes the repository of
whoever holds the transaction. It answers `None` for an investigation with no entry, and
`recorded_ledger` is the guard for a caller that needs the ledger to exist. `linked_ledgers` reads
every ledger a ticket links, in the order the ticket links them, and names the links with none.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.investigation.errors import UnknownInvestigationError
from mightymodels_plugin.tools.investigation.repository import (
    InvestigationRepository,
    LedgerRecord,
)
from mightymodels_plugin.tools.investigation.schema import EntryKind, Source
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow


@dataclass(slots=True, kw_only=True, frozen=True)
class Ledger:
    investigation: Slug
    records: tuple[LedgerRecord, ...]

    def target(self) -> LedgerRecord:
        return self.records[0]

    def next_seq(self) -> int:
        return len(self.records) + 1

    def latest_round(self) -> int:
        return max(record.round for record in self.records)

    def live(self) -> list[LedgerRecord]:
        retired = {seq for record in self.records for seq in record.supersedes}
        return [record for record in self.records if record.seq not in retired]

    def live_of_kind(self, kind: EntryKind) -> list[LedgerRecord]:
        return [record for record in self.live() if record.kind is kind]

    def supersedable(self) -> set[int]:
        return {record.seq for record in self.records if record.kind is not EntryKind.TARGET}

    def origin_of(self, record: LedgerRecord) -> str:
        return f'{self.investigation} e{record.seq}'


@dataclass(slots=True, kw_only=True, frozen=True)
class LinkedLedgers:
    ledgers: tuple[Ledger, ...]
    missing: tuple[Slug, ...]


def record_of(row: LedgerEntryRow) -> LedgerRecord:
    return LedgerRecord(
        seq=row.seq,
        round=row.round,
        kind=EntryKind(row.kind),
        text=row.text,
        source=Source(row.source),
        cite=row.cite,
        supersedes=tuple(row.supersedes),
        at=row.at,
        head=row.head,
    )


def ledger_of(investigations: InvestigationRepository, investigation: Slug) -> Ledger | None:
    rows = investigations.entry_rows(investigation)
    if not rows:
        return None
    return Ledger(investigation=investigation, records=tuple(map(record_of, rows)))


def linked_ledgers(investigations: InvestigationRepository, linked: Iterable[str]) -> LinkedLedgers:
    read = {name: ledger_of(investigations, Slug(name)) for name in linked}
    return LinkedLedgers(
        ledgers=tuple(ledger for ledger in read.values() if ledger is not None),
        missing=tuple(Slug(name) for name, ledger in read.items() if ledger is None),
    )


def recorded_ledger(investigations: InvestigationRepository, investigation: Slug) -> Ledger:
    ledger = ledger_of(investigations, investigation)
    if ledger is None:
        raise UnknownInvestigationError(investigation)
    return ledger
