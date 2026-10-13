"""Text a caller writes is held to the length of the column it is stored in.

Every string field of every request model is listed here once, beside the column that stores it or
the ceiling it is held to when no column of its own does, so a field a request model gains fails
the listing until it is given a maximum.

Redaction runs after a request is validated, and a marker can be longer than the secret it
replaces. So every text that is redacted on its way to a column is also sent at its limit with a
secret in it: the tool refuses it by name and writes no row. The secret is the one whose marker
lengthens text the most, credentials in a URL.

A review report is read into the same request models, so text over its length in a report is
refused by an error naming the finding and the field.
"""

from types import MappingProxyType

import pytest
import sqlalchemy as sql
from mightymodels.clock import now
from mightymodels.core.database import Database
from mightymodels.core.declarative import NAME_LIMIT, PROSE_LIMIT
from mightymodels.core.routing import Depth
from mightymodels.tools.contract.schema import ContractCommand
from mightymodels.tools.contract.service import ContractService
from mightymodels.tools.contract.tables import CommandRow
from mightymodels.tools.crashout.schema import CrashoutEntry
from mightymodels.tools.crashout.service import CrashoutService
from mightymodels.tools.review.repository import review_store
from mightymodels.tools.review.schema import (
    FINDING_ID_LIMIT,
    Decision,
    Emphasis,
    Evidence,
    EvidenceKind,
    Finding,
    Kind,
    Persona,
    ReviewRun,
    ReviewScope,
    Severity,
    Shape,
    StartPayload,
)
from mightymodels.tools.review.service import ReviewService
from mightymodels.tools.review.store import DecidedFinding
from mightymodels.tools.tests.support import (
    ActivityKind,
    DatabaseActivity,
    StateServer,
    text_of,
)
from mightymodels.tools.tests.valid_requests import (
    RUN,
    SLUG,
    TICKET,
    VALID,
    finding_id,
    plain,
)
from mightymodels.tools.ticket.schema import TicketAnswers

STARTED = ReviewRun(
    run_id=RUN,
    slug=None,
    scope=ReviewScope.CODEBASE,
    base=None,
    head=None,
    depth=Depth.DEEP,
    emphasis=Emphasis.BALANCED,
    weights=dict.fromkeys(Persona, 0.5),
    personas=tuple(Persona),
    models={},
    created_at='2026-09-28T12:00:00+00:00',
)
FINDING = Finding(
    id='F1',
    sources=('MV-1',),
    severity=Severity.HIGH,
    kind=Kind.DEFECT,
    security=False,
    title='the drain loop sleeps between batches',
    location='src/queue.py:12',
    fix='drain in one pass',
    verify='run the drain test',
)


class TestATextOneCharacterTooLong:
    ENTRY = MappingProxyType(VALID[CrashoutEntry])
    CALLS = (
        pytest.param(
            'close',
            {'action': 'close', 'slug': SLUG, 'closing': {'shipped': plain(PROSE_LIMIT + 1)}},
            PROSE_LIMIT,
            id='close',
        ),
        pytest.param(
            'contract',
            {
                'action': 'approve',
                'slug': SLUG,
                'commands': [{**VALID[ContractCommand], 'approved_by': plain(NAME_LIMIT + 1)}],
            },
            NAME_LIMIT,
            id='contract',
        ),
        pytest.param(
            'crashout',
            {'action': 'add', 'entry': {**ENTRY, 'rant': plain(PROSE_LIMIT + 1)}},
            PROSE_LIMIT,
            id='crashout',
        ),
        pytest.param(
            'investigation',
            {
                'action': 'start',
                'payload': {'request': {'target': plain(PROSE_LIMIT + 1), 'kind': 'behavior'}},
            },
            PROSE_LIMIT,
            id='investigation',
        ),
        pytest.param(
            'review',
            {'action': 'start', 'payload': {**VALID[StartPayload], 'base': plain(NAME_LIMIT + 1)}},
            NAME_LIMIT,
            id='review',
        ),
        pytest.param(
            'review',
            {
                'action': 'dispose',
                'run_id': RUN.root,
                'payload': {
                    'by': 'user',
                    'decisions': {finding_id(FINDING_ID_LIMIT + 1): {'decision': 'fix'}},
                },
            },
            FINDING_ID_LIMIT,
            id='review-finding-id',
        ),
        pytest.param(
            'task',
            {
                'action': 'start',
                'slug': SLUG,
                'payload': {
                    'task_id': 'T1',
                    'change': {
                        'by': 'engineer',
                        'owned': [plain(PROSE_LIMIT + 1)],
                        'acceptance': ['AC-1'],
                    },
                },
            },
            PROSE_LIMIT,
            id='task',
        ),
        pytest.param(
            'ticket',
            {
                'action': 'write',
                'slug': SLUG,
                'fields': {**VALID[TicketAnswers], 'branch': plain(NAME_LIMIT + 1)},
            },
            NAME_LIMIT,
            id='ticket',
        ),
    )

    @pytest.mark.parametrize(('name', 'arguments', 'limit'), CALLS)
    def test_is_refused_by_the_tool_before_any_row_is_written(
        self,
        name: str,
        arguments: dict[str, object],
        limit: int,
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (result,) = connected_server.call((name, {'request': arguments}))

        assert result.is_error
        assert f'String should have at most {limit} characters' in text_of(result)
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert connected_server.files_on_disk() == tree_after_the_connect


class TestATextAtTheLengthOfItsColumn:
    RANT = plain(PROSE_LIMIT)
    COMMAND = plain(NAME_LIMIT)
    APPROVER = plain(NAME_LIMIT)

    @pytest.fixture
    def journaled_rant(self, crashout_service: CrashoutService) -> str | None:
        crashout_service.add(
            CrashoutEntry.model_validate(VALID[CrashoutEntry] | {'rant': self.RANT})
        )
        journaled = crashout_service.last().entry
        return None if journaled is None else journaled.rant

    @pytest.fixture
    def approved_command(
        self, contract_service: ContractService, repository_database: Database
    ) -> tuple[str, str]:
        command = ContractCommand(id=self.COMMAND, argv=('true',), approved_by=self.APPROVER)
        contract_service.approve(TICKET, [command])
        with repository_database.transaction() as session:
            row = session.scalars(sql.select(CommandRow)).one()
            return row.command_id, row.approved_by

    def test_is_stored_whole_in_a_prose_column(self, journaled_rant: str | None) -> None:
        assert journaled_rant == self.RANT

    def test_is_stored_whole_in_a_name_column(self, approved_command: tuple[str, str]) -> None:
        assert approved_command == (self.COMMAND, self.APPROVER)


class TestTextStoredLongerThanARequestMayCarry:
    CITE = plain(PROSE_LIMIT + 1)
    REASON = 'r' * (PROSE_LIMIT + 1)

    @pytest.fixture
    def report_of_a_run_holding_it(
        self, review_service: ReviewService, repository_database: Database
    ) -> str:
        evidence = Evidence.model_construct(kind=EvidenceKind.METRIC, cite=self.CITE)
        finding = FINDING.model_copy(update={'evidence': evidence})
        decided = DecidedFinding(
            finding_id=finding.id, decision=Decision.DEFER, reason=self.REASON, by='user', at=now()
        )
        with review_store(repository_database).transaction() as repository:
            repository.record_run(STARTED)
            repository.record_findings(RUN, [finding])
            repository.decisions.record_dispositions(RUN, [decided])
        return review_service.report(RUN, Shape.FULL).text

    def test_is_read_back_whole_and_leaves_its_run_readable(
        self, report_of_a_run_holding_it: str
    ) -> None:
        assert self.CITE in report_of_a_run_holding_it
        assert self.REASON in report_of_a_run_holding_it
