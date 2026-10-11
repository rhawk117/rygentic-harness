"""The ticket whose branch is checked out: the one a hook acts for.

A hook's ticket is the one ticket of this repository, not closed, whose `branch` is the checked-out
branch. A detached HEAD, no match and more than one match mean no ticket, and the hook does nothing.
"""

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.ticket.store import TicketStore


def ticket_on_branch(tickets: TicketStore, branch: str | None) -> Slug | None:
    if branch is None:
        return None
    with tickets.transaction() as repository:
        return repository.unclosed_on_branch(branch)
