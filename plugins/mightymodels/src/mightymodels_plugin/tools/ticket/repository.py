"""The ticket rows, reached only through a repository that holds one transaction's session.

`ticket_transaction` opens a transaction on the database and hands out the repository, so the
ticket service never sees a session. A domain that reads ticket rows inside its own transaction
builds a `TicketRepository` on that transaction's session. The repository holds the key of the
git repository the database was opened for, and reads and writes rows under that key only.

A closed ticket is final. `unclosed_row` hands out the row of a ticket that still takes work and
refuses a closed one, and `mark_in_progress` writes through it, so no closed ticket reads in
progress again.

A ticket links investigations by id, and `unrecorded_investigations` says which of them have no
ledger, read through the investigation repository on the same session.
"""

from collections.abc import Collection, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.investigation.repository import InvestigationRepository
from mightymodels_plugin.tools.ticket.schema import TicketSection, TicketStatus
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


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketRepository:
    session: Session
    repository_key: RepositoryKey

    def row(self, slug: Slug) -> TicketRow | None:
        return self.session.get(TicketRow, (self.repository_key.root, slug.root))

    def staged_row(self, slug: Slug) -> TicketRow:
        row = self.row(slug)
        if row is None:
            raise NotStagedError(slug)
        return row

    def unclosed_row(self, slug: Slug) -> TicketRow:
        row = self.staged_row(slug)
        if row.status == TicketStatus.CLOSED:
            raise ClosedTicketError(slug)
        return row

    def stage(self, slug: Slug, section: TicketSection, declared: Sequence[str]) -> TicketRow:
        existing = self.row(slug)
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
        return self.session.merge(row)

    def unrecorded_investigations(self, linked: Collection[Slug]) -> list[Slug]:
        investigations = InvestigationRepository(
            session=self.session, repository_key=self.repository_key
        )
        return investigations.unrecorded(linked)

    def mark_in_progress(self, slug: Slug) -> None:
        self.unclosed_row(slug).status = TicketStatus.IN_PROGRESS

    def mark_closed(self, slug: Slug) -> None:
        self.staged_row(slug).status = TicketStatus.CLOSED


@contextmanager
def ticket_transaction(database: Database) -> Generator[TicketRepository]:
    with database.transaction() as session:
        yield TicketRepository(session=session, repository_key=database.repository_key)
