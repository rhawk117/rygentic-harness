"""The seam under the ticket service: a store whose transaction hands out the ticket repository.

`TicketStore.transaction` is a context manager, and what it yields is a `TicketRepository` that
lives for that one transaction. The SQLite store in `repository.py` wraps the database, and a
store in test support holds work units in memory, so the ticket service runs on either.

A repository hands out `WorkUnit` and `Slug`, the frozen types the domain already has, and never a
row. `staged_ticket` refuses a ticket that was never staged and `unclosed_ticket` refuses a closed
one as well. `unclosed_on_branch` is the one ticket, not closed, whose branch is the one named,
and no ticket when none or more than one is.
"""

from collections.abc import Collection, Sequence
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.ticket.schema import TicketSection, WorkUnit


@runtime_checkable
class TicketRepository(Protocol):
    def ticket(self, slug: Slug) -> WorkUnit | None: ...

    def staged_ticket(self, slug: Slug) -> WorkUnit: ...

    def unclosed_ticket(self, slug: Slug) -> WorkUnit: ...

    def stage(self, slug: Slug, section: TicketSection, declared: Sequence[str]) -> WorkUnit: ...

    def unrecorded_investigations(self, linked: Collection[Slug]) -> list[Slug]: ...

    def mark_in_progress(self, slug: Slug) -> None: ...

    def mark_closed(self, slug: Slug) -> None: ...

    def unclosed_on_branch(self, branch: str) -> Slug | None: ...


@runtime_checkable
class TicketStore(Protocol):
    def transaction(self) -> AbstractContextManager[TicketRepository]: ...
