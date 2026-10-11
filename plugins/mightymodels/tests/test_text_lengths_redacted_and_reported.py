from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

import pytest
import sqlalchemy as sql
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.declarative import NAME_LIMIT, PROSE_LIMIT
from mightymodels_plugin.redaction import RedactedTextTooLongError, redact_within
from mightymodels_plugin.tools.close.schema import Closing
from mightymodels_plugin.tools.close.tables import ClosingRow
from mightymodels_plugin.tools.crashout.schema import CrashoutEntry
from mightymodels_plugin.tools.crashout.tables import CrashoutRow
from mightymodels_plugin.tools.investigation.schema import InvestigationStart, LedgerEntry
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.review.errors import InvalidFieldError
from mightymodels_plugin.tools.review.schema import DisposePayload, Persona, StartPayload
from mightymodels_plugin.tools.review.service import REPORT_FILES, ReviewService
from mightymodels_plugin.tools.review.tables import ReviewFindingRow
from mightymodels_plugin.tools.task.schema import Status
from mightymodels_plugin.tools.task.tables import FailedFixRow, TaskRow
from mightymodels_plugin.tools.tests.support import StateServer, filled_row, table_of, text_of
from mightymodels_plugin.tools.tests.valid_requests import RUN, SLUG, TICKET, VALID, plain
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService

RUN_STARTED = datetime(2026, 9, 28, 12, tzinfo=UTC)
INVESTIGATION = '20260928-the-drain-loop'
CREDENTIALS = '://a:b@'
REDACTED_CREDENTIALS = '://[REDACTED:url-credentials]@'
GROWTH = len(REDACTED_CREDENTIALS) - len(CREDENTIALS)
REDACTED_ON_THE_WAY_TO_A_ROW = (
    ClosingRow,
    CrashoutRow,
    FailedFixRow,
    LedgerEntryRow,
    ReviewFindingRow,
)


REPORTED: Mapping[str, str] = MappingProxyType(
    {
        'title': 'README names a removed flag',
        'location': 'README.md:12',
        'cite': 'ruff.toml PLR0913 max-args=3',
        'fix': 'Replace the flag with the batch option.',
        'verify': 'run the docs check',
    }
)


def with_a_secret(length: int) -> str:
    return plain(length - len(CREDENTIALS)) + CREDENTIALS


def report_with(**given: str) -> str:
    texts = {**REPORTED, **given}
    return (
        '## Findings\n\n### Low\n\n'
        f'#### MV-1 | docs | {texts["title"]}\n\n'
        f'- Evidence: {texts["location"]}\n'
        f'- Evidence (metric): {texts["cite"]}\n'
        f'- Fix: {texts["fix"]}\n'
        f'- Verify: {texts["verify"]}\n'
    )


def started_run_with(reviews: ReviewService, report: str) -> None:
    reviews.start(StartPayload.model_validate(VALID[StartPayload]), started=RUN_STARTED)
    directory = reviews.workspace.review_directory(None, RUN)
    directory.joinpath(REPORT_FILES[Persona.MERGE_VADER]).write_text(report, encoding='utf-8')


def rows_held(database: Database) -> dict[str, int]:
    with database.transaction() as session:
        return {
            row_type.__tablename__: len(session.scalars(sql.select(row_type)).all())
            for row_type in REDACTED_ON_THE_WAY_TO_A_ROW
        }


def closing_with(**given: object) -> dict[str, object]:
    return {'action': 'close', 'slug': SLUG, 'closing': VALID[Closing] | given}


def crashout_with(**given: object) -> dict[str, object]:
    return {'action': 'add', 'entry': VALID[CrashoutEntry] | given}


def target_of(target: str) -> dict[str, object]:
    return {'action': 'start', 'payload': {'request': {'target': target, 'kind': 'behavior'}}}


def entry_with(**given: object) -> dict[str, object]:
    return {
        'action': 'add',
        'investigation_id': INVESTIGATION,
        'payload': {'entries': [VALID[LedgerEntry] | given], 'request': {'round': 1}},
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class RedactedCall:
    tool: str
    arguments: dict[str, object]
    field: str
    limit: int = PROSE_LIMIT
    report: str = report_with()
    findings: int = 0
    chosen: bool = False

    def refusal(self) -> str:
        redacted = self.limit + GROWTH
        return str(RedactedTextTooLongError(self.field, limit=self.limit, length=redacted))


def reported(field: str, **given: str) -> RedactedCall:
    added = {'action': 'add', 'run_id': RUN.root, 'payload': {'persona': 'merge-vader'}}
    return RedactedCall(tool='review', arguments=added, field=field, report=report_with(**given))


def decided(
    field: str,
    payload: dict[str, object],
    *,
    action: str = 'dispose',
    limit: int = PROSE_LIMIT,
    chosen: bool = False,
) -> RedactedCall:
    arguments = {'action': action, 'run_id': RUN.root, 'payload': payload}
    return RedactedCall(
        tool='review',
        arguments=arguments,
        field=field,
        limit=limit,
        findings=1,
        chosen=chosen,
    )


class TestRedactionWithinALimit:
    LIMIT = 64
    KEPT = plain(LIMIT - len(REDACTED_CREDENTIALS)) + REDACTED_CREDENTIALS
    ONE_OVER = with_a_secret(LIMIT - GROWTH + 1)

    def test_keeps_text_that_redaction_brings_to_the_limit(self) -> None:
        assert redact_within(with_a_secret(self.LIMIT - GROWTH), 'rant', self.LIMIT) == self.KEPT

    def test_refuses_text_that_redaction_takes_one_past_it(self) -> None:
        with pytest.raises(RedactedTextTooLongError) as refused:
            redact_within(self.ONE_OVER, 'rant', self.LIMIT)

        named = (refused.value.field, refused.value.limit, refused.value.length)
        assert named == ('rant', self.LIMIT, self.LIMIT + 1)


class TestTextRedactionLengthensPastItsLimit:
    PROSE = with_a_secret(PROSE_LIMIT)
    NAME = with_a_secret(NAME_LIMIT)
    ARRANGED = MappingProxyType(
        {
            'closings': 0,
            'crashouts': 0,
            'task_failed_fixes': 0,
            'ledger_entries': 1,
            'review_findings': 0,
        }
    )
    CALLS = (
        RedactedCall(tool='close', arguments=closing_with(shipped=PROSE), field='shipped'),
        RedactedCall(tool='close', arguments=closing_with(pr=PROSE), field='pr'),
        RedactedCall(tool='close', arguments=closing_with(gotchas=[PROSE]), field='gotchas'),
        RedactedCall(
            tool='crashout', arguments=crashout_with(branch=NAME), field='branch', limit=NAME_LIMIT
        ),
        RedactedCall(tool='crashout', arguments=crashout_with(rant=PROSE), field='rant'),
        RedactedCall(tool='crashout', arguments=crashout_with(failures=[PROSE]), field='failures'),
        RedactedCall(
            tool='crashout', arguments=crashout_with(root_cause=PROSE), field='root_cause'
        ),
        RedactedCall(
            tool='crashout',
            arguments=crashout_with(corrective_action=PROSE),
            field='corrective_action',
        ),
        RedactedCall(
            tool='failed_fix',
            arguments={
                'action': 'record',
                'slug': SLUG,
                'payload': {'task_id': 'T1', 'change': {'hypothesis': PROSE}},
            },
            field='hypothesis',
        ),
        RedactedCall(tool='investigation', arguments=target_of(PROSE), field='target'),
        RedactedCall(tool='investigation', arguments=entry_with(text=PROSE), field='text'),
        RedactedCall(tool='investigation', arguments=entry_with(cite=PROSE), field='cite'),
        reported('title', title=PROSE),
        reported('location', location=PROSE),
        reported('fix', fix=PROSE),
        reported('verify', verify=PROSE),
        reported('evidence cite', cite=PROSE),
        decided(
            'reason',
            {'by': 'user', 'decisions': {'F1': {'decision': 'fix', 'reason': PROSE}}},
        ),
        decided('by', {'by': NAME, 'decisions': {'F1': {'decision': 'fix'}}}, limit=NAME_LIMIT),
        decided(
            'reason',
            {'finding': 'F1', 'result': 'failed', 'reason': PROSE},
            action='resolve',
            chosen=True,
        ),
    )
    EACH_CALL = tuple(
        pytest.param(
            call, id=f'{call.tool}-{call.arguments["action"]}-{call.field.replace(" ", "-")}'
        )
        for call in CALLS
    )

    @pytest.fixture
    def closable_ticket(self, ticket_service: TicketService, repository_database: Database) -> None:
        ticket_service.write(TICKET, TicketAnswers.model_validate(VALID[TicketAnswers]))
        ticket_service.validate(TICKET)
        verified = filled_row(
            TaskRow,
            repository_key=repository_database.repository_key.root,
            slug=SLUG,
            task_id='T1',
            status=Status.VERIFIED,
        )
        with repository_database.transaction() as session:
            session.execute(sql.insert(table_of(TaskRow)).values(verified))

    @pytest.fixture
    def started_investigation(self, investigation_service: InvestigationService) -> None:
        target = InvestigationStart.model_validate(VALID[InvestigationStart])
        investigation_service.start(target, started=RUN_STARTED)

    @pytest.fixture
    def run_with_the_report(self, call: RedactedCall, review_service: ReviewService) -> None:
        started_run_with(review_service, call.report)
        if call.findings:
            review_service.add(RUN, Persona.MERGE_VADER)
        if call.chosen:
            review_service.dispose(RUN, DisposePayload.model_validate(VALID[DisposePayload]))

    @pytest.mark.parametrize('call', EACH_CALL)
    @pytest.mark.usefixtures('closable_ticket', 'started_investigation', 'run_with_the_report')
    def test_is_refused_by_the_tool_by_name_and_no_row_is_written(
        self, call: RedactedCall, connected_server: StateServer, repository_database: Database
    ) -> None:
        (result,) = connected_server.call((call.tool, {'request': call.arguments}))

        assert result.is_error
        assert call.refusal() in text_of(result)
        assert 'validation error' not in text_of(result)
        assert rows_held(repository_database) == {
            **self.ARRANGED,
            'review_findings': call.findings,
        }


class TestAReviewReportWithTextOverItsLength:
    OVER = plain(PROSE_LIMIT + 1)
    EACH_FIELD = tuple(pytest.param(field, id=field) for field in REPORTED)

    @pytest.fixture
    def refusal(self, field: str, review_service: ReviewService) -> InvalidFieldError:
        started_run_with(review_service, report_with(**{field: self.OVER}))
        with pytest.raises(InvalidFieldError) as refused:
            review_service.add(RUN, Persona.MERGE_VADER)
        return refused.value

    @pytest.mark.parametrize('field', EACH_FIELD)
    def test_is_refused_by_an_error_naming_the_finding_and_the_field(
        self, field: str, refusal: InvalidFieldError
    ) -> None:
        assert (refusal.index, refusal.sources, refusal.field) == (0, ('MV-1',), field)
        assert str(refusal) == (
            f'finding 0: {field}: String should have at most {PROSE_LIMIT} characters (MV-1); '
            'nothing was written'
        )

    @pytest.mark.parametrize('field', EACH_FIELD)
    @pytest.mark.usefixtures('refusal')
    def test_stores_no_finding(self, repository_database: Database) -> None:
        assert rows_held(repository_database)['review_findings'] == 0
