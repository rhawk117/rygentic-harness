"""Every row type the state database holds a table for, in the order their tables are created.

`core` imports nothing outside itself, so it cannot name a domain's rows. Whoever opens state, the
server or a hook command, hands `ROW_TYPES` to `open_state`, which hands it to `open_database`.
A domain's `tables.py` adds a table only by adding its row type here.
"""

from mightymodels_plugin.core.database import RowTypes
from mightymodels_plugin.tools.close.tables import ClosingRow
from mightymodels_plugin.tools.contract.tables import CommandRow, ReceiptRow
from mightymodels_plugin.tools.crashout.tables import CrashoutRow
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.review.tables import (
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow, SimilarityRow
from mightymodels_plugin.tools.task.tables import AttemptRow, FailedFixRow, TaskRow, TransitionRow
from mightymodels_plugin.tools.ticket.tables import TicketRow

ROW_TYPES: RowTypes = (
    TicketRow,
    TaskRow,
    AttemptRow,
    FailedFixRow,
    TransitionRow,
    CommandRow,
    ReceiptRow,
    ReviewRunRow,
    ReviewFindingRow,
    ReviewDispositionRow,
    ReviewOutcomeRow,
    ClosingRow,
    LedgerEntryRow,
    CrashoutRow,
    SimilarityRow,
    ScoutReportRow,
)
