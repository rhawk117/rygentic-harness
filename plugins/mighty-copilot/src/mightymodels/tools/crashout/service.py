"""The crashout service: an append-only journal of crashouts, stored as rows.

`add` journals one crashout with the time the server received it. The rant keeps its words: its
line endings become newlines, the whitespace ending each line goes, and so do the blank lines
around it. Every free-text field is redacted before it is stored, and one that redaction
lengthens past its limit refuses the crashout. `stats` reports the recurring
patterns of the journal's latest crashouts, and says so when older ones are left out. `last`
returns the newest crashout, as fields and as text.

When the root cause resembles a row stored earlier, of any kind, the answer says so after its own
line. The crashout is journaled all the same.

The service reads and writes its store and nothing else: no file, and nothing in git.

Everything above the class reads no service state.
"""

from dataclasses import dataclass

from mightymodels.clock import now
from mightymodels.core.declarative import NAME_LIMIT, PROSE_LIMIT
from mightymodels.redaction import redact_within
from mightymodels.tools.crashout.rendering import crashout_text, patterns_text
from mightymodels.tools.crashout.repository import JOURNAL_WINDOW
from mightymodels.tools.crashout.schema import (
    CrashoutEntry,
    CrashoutView,
    JournaledCrashout,
)
from mightymodels.tools.crashout.store import CrashoutStore
from mightymodels.tools.similarity.rendering import duplicates_text

NOTHING_JOURNALED = 'no crashouts recorded yet.'
SERENITY = f'{NOTHING_JOURNALED} serenity.'
OLDER_LEFT_OUT = f'older crashouts are left out: these are the latest {JOURNAL_WINDOW.rows}\n'


def normalized_rant(rant: str) -> str:
    lines = rant.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    return '\n'.join(line.rstrip() for line in lines).strip('\n')


def journaled(entry: CrashoutEntry, *, at: str) -> JournaledCrashout:
    return JournaledCrashout(
        at=at,
        ticket=None if entry.ticket is None else entry.ticket.root,
        branch=None if entry.branch is None else redact_within(entry.branch, 'branch', NAME_LIMIT),
        severity=entry.severity,
        verdict=entry.verdict,
        rant=redact_within(normalized_rant(entry.rant), 'rant', PROSE_LIMIT),
        failures=tuple(
            redact_within(failure, 'failures', PROSE_LIMIT) for failure in entry.failures
        ),
        root_cause=redact_within(entry.root_cause, 'root_cause', PROSE_LIMIT),
        corrective_action=redact_within(entry.corrective_action, 'corrective_action', PROSE_LIMIT),
        barked_back=entry.barked_back,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutService:
    store: CrashoutStore

    def add(self, entry: CrashoutEntry) -> CrashoutView:
        crashout = journaled(entry, at=now())
        with self.store.transaction() as repository:
            journaled_crashout = repository.journal(crashout)
        number = journaled_crashout.number
        text = f'journaled crashout #{number}\n{duplicates_text(journaled_crashout.duplicates)}'
        return CrashoutView(text=text)

    def stats(self) -> CrashoutView:
        with self.store.transaction() as repository:
            latest = repository.latest_crashouts()
        if not latest.rows:
            return CrashoutView(text=f'{SERENITY}\n')
        note = OLDER_LEFT_OUT if latest.older_left_out else ''
        return CrashoutView(text=patterns_text(latest.rows) + note)

    def last(self) -> CrashoutView:
        with self.store.transaction() as repository:
            crashout = repository.latest_crashout()
        if crashout is None:
            return CrashoutView(text=f'{NOTHING_JOURNALED}\n')
        return CrashoutView(text=crashout_text(crashout), entry=crashout)
