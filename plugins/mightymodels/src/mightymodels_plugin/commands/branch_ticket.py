"""The ticket whose branch is checked out: the one a hook acts for.

A hook's ticket is the one ticket of this repository, not closed, whose `branch` is the checked-out
branch. A detached HEAD, no match and more than one match mean no ticket, and the hook does nothing.
"""

from sqlalchemy import select

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.ticket.schema import TicketStatus
from mightymodels_plugin.tools.ticket.tables import TicketRow


def ticket_on_branch(database: Database, branch: str | None) -> Slug | None:
    if branch is None:
        return None
    query = (
        select(TicketRow.slug)
        .where(
            TicketRow.repository_key == database.repository_key.root,
            TicketRow.branch == branch,
            TicketRow.status != TicketStatus.CLOSED,
        )
        .limit(2)
    )
    with database.transaction() as session:
        slugs = list(session.scalars(query))
    return Slug(slugs[0]) if len(slugs) == 1 else None
