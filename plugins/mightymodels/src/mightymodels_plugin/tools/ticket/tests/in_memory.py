"""The ticket store kept in memory: work units by slug, and the investigations that have a ledger.

A transaction works on a copy of the units and keeps it only when its block ends without an
error, as a database transaction does. A test names the investigations that have a ledger in
`recorded_investigations`, which the SQLite repository reads from the investigation ledgers.
"""

from collections.abc import Collection, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.ticket.repository import ClosedTicketError, NotStagedError
from mightymodels_plugin.tools.ticket.schema import TicketSection, TicketStatus, WorkUnit


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryTicketRepository:
    units: dict[Slug, WorkUnit]
    recorded_investigations: Collection[Slug]

    def ticket(self, slug: Slug) -> WorkUnit | None:
        return self.units.get(slug)

    def staged_ticket(self, slug: Slug) -> WorkUnit:
        unit = self.ticket(slug)
        if unit is None:
            raise NotStagedError(slug)
        return unit

    def unclosed_ticket(self, slug: Slug) -> WorkUnit:
        unit = self.staged_ticket(slug)
        if unit.status is TicketStatus.CLOSED:
            raise ClosedTicketError(slug)
        return unit

    def stage(self, slug: Slug, section: TicketSection, declared: Sequence[str]) -> WorkUnit:
        existing = self.ticket(slug)
        previous = () if existing is None else existing.investigations
        added = [investigation for investigation in declared if investigation not in previous]
        unit = WorkUnit(
            slug=slug,
            status=TicketStatus.STAGED if existing is None else existing.status,
            ticket=section,
            investigations=(*previous, *added),
        )
        self.units[slug] = unit
        return unit

    def unrecorded_investigations(self, linked: Collection[Slug]) -> list[Slug]:
        return [slug for slug in linked if slug not in self.recorded_investigations]

    def mark_in_progress(self, slug: Slug) -> None:
        unit = self.unclosed_ticket(slug)
        self.units[slug] = unit.model_copy(update={'status': TicketStatus.IN_PROGRESS})

    def mark_closed(self, slug: Slug) -> None:
        unit = self.staged_ticket(slug)
        self.units[slug] = unit.model_copy(update={'status': TicketStatus.CLOSED})

    def unclosed_on_branch(self, branch: str) -> Slug | None:
        on_branch = [
            unit.slug
            for unit in self.units.values()
            if unit.ticket.branch == branch and unit.status is not TicketStatus.CLOSED
        ]
        return on_branch[0] if len(on_branch) == 1 else None


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryTicketStore:
    units: dict[Slug, WorkUnit] = field(default_factory=dict)
    recorded_investigations: set[Slug] = field(default_factory=set)

    @contextmanager
    def transaction(self) -> Generator[InMemoryTicketRepository]:
        working = dict(self.units)
        yield InMemoryTicketRepository(
            units=working, recorded_investigations=self.recorded_investigations
        )
        self.units.clear()
        self.units.update(working)
