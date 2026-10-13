"""The investigation service: an append-only ledger per investigation, stored as rows.

`start` opens an investigation by storing its target as entry 1 and names it after the day and
the target. `add` appends a round's entries: the round may not go back, every entry is checked
against the rule of its kind, and one refused entry refuses the whole batch, so nothing of it is
stored. `render` and `knowns` return the ledger's two texts and `listing` names the
newest investigations with the latest round of each, and says so when older ones are left out.

The target and every entry's text and cite are redacted before they are stored, and the
investigation is named after the redacted target, so a secret reaches neither a row nor an id.
A text that redaction lengthens past its limit is refused, and in `add` it refuses the batch.

Each entry's text is also stored in the similarity table, and when it resembles a row stored
earlier, of any kind, the answer says so after its own line. The entry is stored all the same.

HEAD is read from git when an entry is stored and when the knowns are asked for. Outside a
repository, or with no git binary, it is absent and every entry reads as a lead.

The service holds its store and the git queries it asks, and never a session or a row.

Everything above the class reads no service state.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import count
from types import MappingProxyType

from mightymodels.clock import now
from mightymodels.core.declarative import PROSE_LIMIT
from mightymodels.core.errors import StateError
from mightymodels.core.slug import Slug
from mightymodels.core.workspace import GitQueries
from mightymodels.redaction import redact_within, redaction_within
from mightymodels.tools.investigation.errors import (
    CiteRequiredError,
    EmptyTextError,
    InvalidEntryError,
    RoundRegressionError,
    SourceNotAllowedError,
    UnknownSupersededError,
    WrittenByStartError,
)
from mightymodels.tools.investigation.ledger import Ledger, recorded_ledger
from mightymodels.tools.investigation.rendering import knowns_table, ledger_text
from mightymodels.tools.investigation.repository import INVESTIGATIONS_LISTED, TARGET_SEQ
from mightymodels.tools.investigation.schema import (
    EntryKind,
    InvestigationStart,
    InvestigationView,
    KnownsFilter,
    LedgerEntry,
    Source,
)
from mightymodels.tools.investigation.store import (
    InvestigationRepository,
    InvestigationStore,
    LedgerRecord,
)
from mightymodels.tools.similarity.rendering import duplicates_text

DAY_FORMAT = '%Y%m%d'
TARGET_NAME_LIMIT = 40
UNNAMED_TARGET = 'investigation'
OUTSIDE_A_NAME = re.compile(r'[^a-z0-9]+')
NO_INVESTIGATIONS = 'no investigations\n'
OLDER_LEFT_OUT = (
    f'older investigations are left out: these are the latest {INVESTIGATIONS_LISTED.rows}\n'
)


@dataclass(slots=True, kw_only=True, frozen=True)
class EntryRule:
    needs_cite: bool
    sources: frozenset[Source]


ANY_SOURCE = frozenset(Source)
ENTRY_RULES: Mapping[EntryKind, EntryRule] = MappingProxyType(
    {
        EntryKind.KNOWN: EntryRule(needs_cite=True, sources=ANY_SOURCE),
        EntryKind.OPEN: EntryRule(needs_cite=False, sources=ANY_SOURCE),
        EntryKind.DECISION: EntryRule(needs_cite=False, sources=frozenset({Source.USER})),
        EntryKind.RESOURCE: EntryRule(needs_cite=True, sources=ANY_SOURCE),
        EntryKind.NEXT: EntryRule(
            needs_cite=False,
            sources=frozenset({Source.CODE_SCOUT, Source.WEB_SCOUT, Source.USER}),
        ),
    }
)


@dataclass(slots=True, kw_only=True, frozen=True)
class EntryStamp:
    round: int
    at: str
    head: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class RedactedRecord:
    record: LedgerRecord
    hits: int


def target_name(target: str) -> str:
    name = OUTSIDE_A_NAME.sub('-', target.lower()).strip('-')
    if len(name) > TARGET_NAME_LIMIT:
        name = name[: TARGET_NAME_LIMIT + 1].rsplit('-', 1)[0]
    return name or UNNAMED_TARGET


def free_investigation(investigations: InvestigationRepository, stem: str) -> Slug:
    names = (stem if repeat == 1 else f'{stem}-{repeat}' for repeat in count(1))
    return next(name for name in map(Slug, names) if not investigations.has_entries(name))


def rule_error(index: int, entry: LedgerEntry) -> InvalidEntryError | None:
    rule = ENTRY_RULES.get(entry.kind)
    if rule is None:
        return WrittenByStartError(index, entry.kind)
    if rule.needs_cite and entry.cite is None:
        return CiteRequiredError(index, entry.kind)
    if entry.source not in rule.sources:
        return SourceNotAllowedError(index, entry.kind, entry.source)
    return None


def entry_error(ledger: Ledger, index: int, entry: LedgerEntry) -> InvalidEntryError | None:
    if not entry.text.strip():
        return EmptyTextError(index)
    if (broken_rule := rule_error(index, entry)) is not None:
        return broken_rule
    unknown = sorted(set(entry.supersedes) - ledger.supersedable())
    return UnknownSupersededError(index, unknown) if unknown else None


def batch_error(ledger: Ledger, given: int, entries: Sequence[LedgerEntry]) -> StateError | None:
    latest = ledger.latest_round()
    if given < latest:
        return RoundRegressionError(given, latest)
    errors = (entry_error(ledger, index, entry) for index, entry in enumerate(entries))
    return next((error for error in errors if error is not None), None)


def redacted_record(entry: LedgerEntry, seq: int, stamp: EntryStamp) -> RedactedRecord:
    text = redaction_within(entry.text, 'text', PROSE_LIMIT)
    cite = None if entry.cite is None else redaction_within(entry.cite, 'cite', PROSE_LIMIT)
    record = LedgerRecord(
        seq=seq,
        round=stamp.round,
        kind=entry.kind,
        text=text.text,
        source=entry.source,
        cite=None if cite is None else cite.text,
        supersedes=entry.supersedes,
        at=stamp.at,
        head=stamp.head,
    )
    return RedactedRecord(record=record, hits=text.hits + (0 if cite is None else cite.hits))


def saved_text(investigation: Slug, batch: Sequence[RedactedRecord]) -> str:
    saved = ' '.join(f'e{redacted.record.seq}' for redacted in batch)
    hits = sum(redacted.hits for redacted in batch)
    return f'saved {saved} to {investigation} ({hits} redacted)\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationService:
    store: InvestigationStore
    git: GitQueries

    def start(self, request: InvestigationStart, *, started: datetime) -> InvestigationView:
        target = redact_within(request.target, 'target', PROSE_LIMIT)
        record = LedgerRecord(
            seq=TARGET_SEQ,
            round=0,
            kind=EntryKind.TARGET,
            text=target,
            source=Source.USER,
            cite=request.kind,
            supersedes=(),
            at=started.isoformat(timespec='seconds'),
            head=self.git.resolve_head(),
        )
        stem = f'{started.strftime(DAY_FORMAT)}-{target_name(target)}'
        with self.store.transaction() as repository:
            investigation = free_investigation(repository, stem)
            duplicates = repository.append(investigation, [record])
        return InvestigationView(
            text=f'started {investigation}\n{duplicates_text(duplicates)}',
            investigation_id=investigation.root,
        )

    def add(
        self, investigation: Slug, round_number: int, entries: Sequence[LedgerEntry]
    ) -> InvestigationView:
        stamp = EntryStamp(round=round_number, at=now(), head=self.git.resolve_head())
        with self.store.transaction() as repository:
            ledger = recorded_ledger(repository, investigation)
            if (error := batch_error(ledger, round_number, entries)) is not None:
                raise error
            numbered = enumerate(entries, start=ledger.next_seq())
            batch = [redacted_record(entry, seq, stamp) for seq, entry in numbered]
            duplicates = repository.append(investigation, (redacted.record for redacted in batch))
        return InvestigationView(
            text=saved_text(investigation, batch) + duplicates_text(duplicates),
            investigation_id=investigation.root,
        )

    def render(self, investigation: Slug) -> InvestigationView:
        with self.store.transaction() as repository:
            ledger = recorded_ledger(repository, investigation)
        return InvestigationView(text=ledger_text(ledger), investigation_id=investigation.root)

    def knowns(self, investigation: Slug, selection: KnownsFilter) -> InvestigationView:
        head = self.git.resolve_head()
        with self.store.transaction() as repository:
            ledger = recorded_ledger(repository, investigation)
        text = knowns_table(ledger, selection, head)
        return InvestigationView(text=text, investigation_id=investigation.root)

    def listing(self) -> InvestigationView:
        with self.store.transaction() as repository:
            listed = repository.latest_rounds()
        lines = [f'{investigation}\tround {latest}\n' for investigation, latest in listed.rows]
        note = OLDER_LEFT_OUT if listed.older_left_out else ''
        return InvestigationView(text=(''.join(lines) or NO_INVESTIGATIONS) + note)
