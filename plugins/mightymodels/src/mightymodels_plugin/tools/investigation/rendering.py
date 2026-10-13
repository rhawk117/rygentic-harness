"""The two texts of a ledger: its sections, and its knowns as a Markdown table.

Both show live entries only. The sections end with the next questions of the latest round, since
an earlier round's were either answered or dropped. The table says of each entry whether it was
stored at the HEAD the repository is at now, `current`, or at another, `lead`: a lead is checked
again before anyone relies on it.
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum, auto
from itertools import chain
from types import MappingProxyType

from mightymodels_plugin.head import short_head
from mightymodels_plugin.tools.investigation.ledger import Ledger
from mightymodels_plugin.tools.investigation.schema import EntryKind, KnownsFilter
from mightymodels_plugin.tools.investigation.store import LedgerRecord

SECTION_TITLES: Mapping[EntryKind, str] = MappingProxyType(
    {
        EntryKind.KNOWN: 'Knowns',
        EntryKind.OPEN: 'Open',
        EntryKind.DECISION: 'Decisions',
        EntryKind.RESOURCE: 'Resources',
    }
)
NEXT_TITLE = 'Next'
TABLE_HEADER = (
    '| entry | kind | claim | cite | source | round | status |',
    '|---|---|---|---|---|---|---|',
)


class EntryStatus(StrEnum):
    CURRENT = auto()
    LEAD = auto()


def entry_line(record: LedgerRecord) -> str:
    cite = '' if record.cite is None else f' [{record.cite}]'
    return f'- e{record.seq}: {record.text}{cite} ({record.source}, round {record.round})'


def section_lines(title: str, records: Iterable[LedgerRecord]) -> list[str]:
    return [f'### {title}', *map(entry_line, records), '']


def ledger_text(ledger: Ledger) -> str:
    target = ledger.target()
    latest = ledger.latest_round()
    next_questions = (
        record for record in ledger.live_of_kind(EntryKind.NEXT) if record.round == latest
    )
    sections = (
        section_lines(title, ledger.live_of_kind(kind)) for kind, title in SECTION_TITLES.items()
    )
    lines = [
        f'## Ledger, round {latest}',
        f'Target: {target.text} ({target.cite})',
        '',
        *chain.from_iterable(sections),
        *section_lines(NEXT_TITLE, next_questions),
    ]
    return '\n'.join(lines).rstrip() + '\n'


def table_cell(text: str | None) -> str:
    return ('' if text is None else text).replace('|', '\\|')


def entry_status(record: LedgerRecord, head: str | None) -> EntryStatus:
    stored_at_head = head is not None and record.head == head
    return EntryStatus.CURRENT if stored_at_head else EntryStatus.LEAD


def table_row(record: LedgerRecord, head: str | None) -> str:
    cells = (
        f'e{record.seq}',
        record.kind,
        table_cell(record.text),
        table_cell(record.cite),
        record.source,
        str(record.round),
        entry_status(record, head),
    )
    return '| ' + ' | '.join(cells) + ' |'


def knowns_table(ledger: Ledger, selection: KnownsFilter, head: str | None) -> str:
    rows = [record for record in ledger.live() if record.kind in selection.kinds]
    hidden = len(rows) - selection.limit
    lines = [
        f'## Knowns table, {ledger.investigation} at HEAD {short_head(head)}',
        *TABLE_HEADER,
        *(table_row(record, head) for record in rows[: selection.limit]),
        *([f'{hidden} more rows; ask again with a larger limit'] if hidden > 0 else []),
    ]
    return '\n'.join(lines) + '\n'
