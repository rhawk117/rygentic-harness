"""The ticket rows, reached only through a repository that holds one transaction's session.

`SqliteTicketStore` is the ticket store over the database: its `transaction` opens one and hands
out the repository, so the ticket service never sees a session, and `ticket_store` builds it as
the `TicketStore` a service holds. A domain that reads tickets inside its own transaction builds a
`SqliteTicketRepository` on that transaction's session. The repository holds the key of the git
repository the database was opened for, and reads and writes rows under that key only.

No row leaves the repository: a read hands out the `WorkUnit` that `unit_of` maps a row to.

A closed ticket is final. `unclosed_ticket` hands out a ticket that still takes work and refuses a
closed one, and `mark_in_progress` writes through the same check, so no closed ticket reads in
progress again.

A ticket links investigations by id, and `unrecorded_investigations` says which of them have no
ledger, read through the investigation repository on the same session.
"""

from collections.abc import Collection, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

import sqlalchemy as sql
from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.core.routing import Scope
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.investigation.repository import SqliteInvestigationRepository
from mightymodels_plugin.tools.ticket.schema import TicketSection, TicketStatus, Tracker, WorkUnit
from mightymodels_plugin.tools.ticket.store import TicketStore
from mightymodels_plugin.tools.ticket.tables import TicketRow


class NotStagedError(StateError):
    def __init__(self, slug: Slug) -> None:
        super().__init__(f'{slug} is not staged; stage the ticket with open-ticket first')
        self.slug = slug


class ClosedTicketError(StateError):
    def __init__(self, slug: Slug) -> None:
        super().__init__(
            f'{slug} is {TicketStatus.CLOSED}, and a closed ticket is final; '
            'new work needs a new ticket, staged with open-ticket'
        )
        self.slug = slug


def unit_of(row: TicketRow) -> WorkUnit:
    section = TicketSection(
        ticket=row.ticket,
        summary=row.summary,
        branch=row.branch,
        scope=Scope(row.scope),
        plan_first=row.plan_first,
        models=row.models,
        tracker=Tracker(issue=row.issue, jira=row.jira),
        context=tuple(row.context),
        validated_at=row.validated_at,
    )
    return WorkUnit(
        slug=Slug(row.slug),
        status=TicketStatus(row.status),
        ticket=section,
        investigations=tuple(row.investigations),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteTicketRepository:
    session: Session
    repository_key: RepositoryKey

    def _row(self, slug: Slug) -> TicketRow | None:
        return self.session.get(TicketRow, (self.repository_key.root, slug.root))

    def _staged_row(self, slug: Slug) -> TicketRow:
        row = self._row(slug)
        if row is None:
            raise NotStagedError(slug)
        return row

    def _unclosed_row(self, slug: Slug) -> TicketRow:
        row = self._staged_row(slug)
        if row.status == TicketStatus.CLOSED:
            raise ClosedTicketError(slug)
        return row

    def ticket(self, slug: Slug) -> WorkUnit | None:
        row = self._row(slug)
        return None if row is None else unit_of(row)

    def staged_ticket(self, slug: Slug) -> WorkUnit:
        return unit_of(self._staged_row(slug))

    def unclosed_ticket(self, slug: Slug) -> WorkUnit:
        return unit_of(self._unclosed_row(slug))

    def stage(self, slug: Slug, section: TicketSection, declared: Sequence[str]) -> WorkUnit:
        existing = self._row(slug)
        previous = [] if existing is None else existing.investigations
        added = [investigation for investigation in declared if investigation not in previous]
        row = TicketRow(
            repository_key=self.repository_key.root,
            slug=slug.root,
            status=TicketStatus.STAGED if existing is None else existing.status,
            ticket=section.ticket,
            summary=section.summary,
            branch=section.branch,
            scope=section.scope,
            plan_first=section.plan_first,
            issue=section.tracker.issue,
            jira=section.tracker.jira,
            models=section.models,
            context=list(section.context),
            investigations=[*previous, *added],
            validated_at=section.validated_at,
        )
        return unit_of(self.session.merge(row))

    def unrecorded_investigations(self, linked: Collection[Slug]) -> list[Slug]:
        investigations = SqliteInvestigationRepository(
            session=self.session, repository_key=self.repository_key
        )
        return investigations.unrecorded(linked)

    def mark_in_progress(self, slug: Slug) -> None:
        self._unclosed_row(slug).status = TicketStatus.IN_PROGRESS

    def mark_closed(self, slug: Slug) -> None:
        self._staged_row(slug).status = TicketStatus.CLOSED

    def unclosed_on_branch(self, branch: str) -> Slug | None:
        query = (
            sql.select(TicketRow.slug)
            .where(
                TicketRow.repository_key == self.repository_key.root,
                TicketRow.branch == branch,
                TicketRow.status != TicketStatus.CLOSED,
            )
            .limit(2)
        )
        slugs = list(self.session.scalars(query))
        return Slug(slugs[0]) if len(slugs) == 1 else None

    def all_unclosed_on_branch(self, branch: str) -> list[Slug]:
        query = (
            sql.select(TicketRow.slug)
            .where(
                TicketRow.repository_key == self.repository_key.root,
                TicketRow.branch == branch,
                TicketRow.status != TicketStatus.CLOSED,
            )
            .order_by(TicketRow.slug)
        )
        return list(map(Slug, self.session.scalars(query)))


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteTicketStore:
    database: Database

    @contextmanager
    def transaction(self) -> Generator[SqliteTicketRepository]:
        with self.database.transaction() as session:
            yield SqliteTicketRepository(
                session=session, repository_key=self.database.repository_key
            )


def ticket_store(database: Database) -> TicketStore:
    return SqliteTicketStore(database=database)
