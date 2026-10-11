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

from collections.abc import Callable, Collection, Generator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TypeAliasType, get_args

import pytest
import sqlalchemy as sql
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.declarative import NAME_LIMIT, PROSE_LIMIT, Base
from mightymodels_plugin.core.routing import Depth
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import SLUG_LIMIT, Slug
from mightymodels_plugin.redaction import RedactedTextTooLongError, redact_within
from mightymodels_plugin.tools.close.schema import Closing
from mightymodels_plugin.tools.close.tables import ClosingRow
from mightymodels_plugin.tools.contract.schema import ContractCommand
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.contract.tables import CommandRow
from mightymodels_plugin.tools.crashout.schema import CrashoutEntry
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.crashout.tables import CrashoutRow
from mightymodels_plugin.tools.failed_fix.schema import FailedFixPayload, TaskFailedFix
from mightymodels_plugin.tools.investigation.schema import (
    InvestigationStart,
    InvestigationStartRequest,
    LedgerEntry,
)
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.request import RequestModel
from mightymodels_plugin.tools.review.errors import InvalidFieldError
from mightymodels_plugin.tools.review.repository import DecidedFinding, review_transaction
from mightymodels_plugin.tools.review.schema import (
    FINDING_ID_LIMIT,
    Decision,
    DisposePayload,
    DisposeRequest,
    Disposition,
    Emphasis,
    Evidence,
    EvidenceKind,
    Finding,
    FindingInput,
    Kind,
    Persona,
    ResolvePayload,
    ReviewRun,
    ReviewScope,
    Severity,
    Shape,
    StartPayload,
    StartRequest,
)
from mightymodels_plugin.tools.review.service import REPORT_FILES, ReviewService
from mightymodels_plugin.tools.review.tables import (
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels_plugin.tools.similarity.schema import SpooledReport
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow
from mightymodels_plugin.tools.task.schema import (
    Status,
    TaskMark,
    TaskPayload,
    TaskStart,
    TaskVerification,
)
from mightymodels_plugin.tools.task.tables import FailedFixRow, TaskRow
from mightymodels_plugin.tools.tests.support import (
    ActivityKind,
    DatabaseActivity,
    StateServer,
    filled_row,
    table_of,
    text_of,
)
from mightymodels_plugin.tools.ticket.schema import TicketAnswers, TicketContext, TicketRequest
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.tools.ticket.tables import TicketRow
from pydantic import ValidationError

type Placed = Callable[[str], object]
type Spelled = Callable[[int], str]
type StringSchema = Collection[object]

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
RUN = RunId('20260928-120000')
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
TOO_LONG = 'string_too_long'
OFF_THE_PATTERN = 'string_pattern_mismatch'
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
VALID: Mapping[type[RequestModel], dict[str, object]] = MappingProxyType(
    {
        Closing: {'shipped': 'the drain runs in one pass'},
        ContractCommand: {'id': 'T1.AC-1', 'argv': ['true'], 'approved_by': 'user'},
        CrashoutEntry: {
            'severity': 'heated',
            'verdict': 'deserved',
            'rant': 'why did you skip the tests',
            'failures': ['skipped the tests'],
            'root_cause': 'optimised for speed',
            'corrective_action': 'run the gate before reporting',
            'barked_back': False,
        },
        LedgerEntry: {'kind': 'open', 'text': 'why is the drain slow', 'source': 'user'},
        InvestigationStart: {'target': 'the drain loop', 'kind': 'behavior'},
        InvestigationStartRequest: {'target': 'the drain loop', 'kind': 'behavior'},
        Evidence: {'kind': 'metric', 'cite': 'cyclomatic complexity 14'},
        FindingInput: {
            'sources': ['MV-1'],
            'severity': 'High',
            'title': 'the drain loop sleeps between batches',
            'location': 'src/queue.py:12',
            'fix': 'drain in one pass',
            'verify': 'run the drain test',
        },
        SpooledReport: {
            'repository_key': 'acme/widgets',
            'scout': 'code-scout',
            'target': 'the drain loop',
            'report': 'the drain loop sleeps between batches',
        },
        StartPayload: {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'},
        StartRequest: {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'},
        Disposition: {'decision': 'fix'},
        DisposePayload: {'by': 'user', 'decisions': {'F1': {'decision': 'fix'}}},
        DisposeRequest: {'by': 'user', 'decisions': {'F1': {'decision': 'fix'}}},
        ResolvePayload: {'finding': 'F1', 'result': 'fixed'},
        TaskStart: {'by': 'engineer', 'owned': ['src/queue.py']},
        TaskVerification: {'commit': 'abc1234'},
        TaskMark: {'to': 'failed', 'reason': 'the drain test fails'},
        FailedFixPayload: {'task_id': 'T1', 'change': {'hypothesis': 'the drain loop sleeps'}},
        TaskFailedFix: {'hypothesis': 'the drain loop sleeps between batches'},
        TaskPayload: {},
        TicketAnswers: {
            'summary': 'Retry queue drains slowly',
            'scope': 'large',
            'compaction': True,
            'branch': 'fix/retry-queue',
            'context': ['drain loop sleeps between batches'],
        },
        TicketRequest: {
            'summary': 'Retry queue drains slowly',
            'scope': 'large',
            'compaction': True,
            'branch': 'fix/retry-queue',
            'context': ['drain loop sleeps between batches'],
        },
        TicketContext: {'context': ['drain loop sleeps between batches']},
    }
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


def length_of(row_type: type[Base], column: str) -> int:
    declared = table_of(row_type).columns[column].type
    assert isinstance(declared, sql.String)
    assert declared.length is not None
    return declared.length


def alone(text: str) -> object:
    return text


def in_a_list(text: str) -> object:
    return [text]


def naming_a_decision(text: str) -> object:
    return {text: {'decision': 'fix'}}


def naming_an_assertion(text: str) -> object:
    return {text: 'the drain test passes'}


def as_an_assertion(text: str) -> object:
    return {'T1.AC-1': text}


def plain(length: int) -> str:
    return 'x' * length


def finding_id(length: int) -> str:
    return 'F' + '1' * (length - 1)


def source_id(length: int) -> str:
    return 'MV-' + '1' * (length - 3)


def task_id(length: int) -> str:
    return 'T' + '1' * (length - 1)


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
class CallerText:
    model: type[RequestModel]
    field: str
    limit: int
    part: str = 'whole'
    placed: Placed = alone
    spelled: Spelled = plain
    refused_as: str = TOO_LONG

    def refusals(self, length: int) -> list[str]:
        request = VALID[self.model] | {self.field: self.placed(self.spelled(length))}
        try:
            self.model.model_validate(request)
        except ValidationError as refused:
            return [error['type'] for error in refused.errors()]
        return []


def stored(model: type[RequestModel], field: str, row_type: type[Base], column: str) -> CallerText:
    return CallerText(model=model, field=field, limit=length_of(row_type, column))


def carries_text(annotation: object) -> bool:
    if isinstance(annotation, TypeAliasType):
        return carries_text(annotation.__value__)
    return annotation is str or any(map(carries_text, get_args(annotation)))


def strings_in(node: object) -> Generator[StringSchema]:
    if isinstance(node, dict):
        if node.get('type') == 'string':
            yield node
        yield from strings_in(list(node.values()))
    if isinstance(node, list):
        for child in node:
            yield from strings_in(child)


def text_fields() -> set[tuple[str, str]]:
    return {
        (model.__name__, name)
        for model in RequestModel.__subclasses__()
        for name, field in model.model_fields.items()
        if carries_text(field.annotation)
    }


class TestEveryStringOfARequestModel:
    IN_A_COLUMN = (
        stored(Closing, 'shipped', ClosingRow, 'shipped'),
        stored(Closing, 'pr', ClosingRow, 'pr'),
        stored(ContractCommand, 'id', CommandRow, 'command_id'),
        stored(ContractCommand, 'approved_by', CommandRow, 'approved_by'),
        stored(CrashoutEntry, 'branch', CrashoutRow, 'branch'),
        stored(CrashoutEntry, 'rant', CrashoutRow, 'rant'),
        stored(CrashoutEntry, 'root_cause', CrashoutRow, 'root_cause'),
        stored(CrashoutEntry, 'corrective_action', CrashoutRow, 'corrective_action'),
        stored(LedgerEntry, 'text', LedgerEntryRow, 'text'),
        stored(LedgerEntry, 'cite', LedgerEntryRow, 'cite'),
        stored(InvestigationStartRequest, 'target', LedgerEntryRow, 'text'),
        stored(Evidence, 'cite', ReviewFindingRow, 'evidence_cite'),
        stored(FindingInput, 'title', ReviewFindingRow, 'title'),
        stored(FindingInput, 'location', ReviewFindingRow, 'location'),
        stored(FindingInput, 'fix', ReviewFindingRow, 'fix'),
        stored(FindingInput, 'verify', ReviewFindingRow, 'verify'),
        stored(SpooledReport, 'target', ScoutReportRow, 'target'),
        stored(SpooledReport, 'report', ScoutReportRow, 'report'),
        stored(StartRequest, 'base', ReviewRunRow, 'base'),
        stored(Disposition, 'reason', ReviewDispositionRow, 'reason'),
        stored(DisposeRequest, 'by', ReviewDispositionRow, 'by'),
        CallerText(
            model=DisposeRequest,
            field='decisions',
            limit=length_of(ReviewDispositionRow, 'finding_id'),
            part='key',
            placed=naming_a_decision,
            spelled=finding_id,
        ),
        CallerText(
            model=DisposeRequest,
            field='finding',
            limit=length_of(ReviewDispositionRow, 'finding_id'),
            spelled=finding_id,
        ),
        CallerText(
            model=ResolvePayload,
            field='finding',
            limit=length_of(ReviewOutcomeRow, 'finding_id'),
            spelled=finding_id,
        ),
        stored(ResolvePayload, 'commit', ReviewOutcomeRow, 'commit'),
        stored(ResolvePayload, 'reason', ReviewOutcomeRow, 'reason'),
        stored(TaskVerification, 'commit', TaskRow, 'commit'),
        stored(TicketRequest, 'summary', TicketRow, 'summary'),
        stored(TicketRequest, 'branch', TicketRow, 'branch'),
        stored(TicketRequest, 'jira', TicketRow, 'jira'),
        CallerText(
            model=TaskPayload,
            field='task_id',
            limit=length_of(TaskRow, 'task_id'),
            spelled=task_id,
            refused_as=OFF_THE_PATTERN,
        ),
        CallerText(
            model=FailedFixPayload,
            field='task_id',
            limit=length_of(TaskRow, 'task_id'),
            spelled=task_id,
            refused_as=OFF_THE_PATTERN,
        ),
    )
    IN_NO_COLUMN_OF_ITS_OWN = (
        CallerText(
            model=Closing, field='gotchas', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=ContractCommand, field='argv', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=CrashoutEntry, field='failures', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=FindingInput,
            field='sources',
            limit=PROSE_LIMIT,
            part='item',
            placed=in_a_list,
            spelled=source_id,
        ),
        CallerText(
            model=TaskStart, field='owned', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=TaskVerification,
            field='assertions',
            limit=PROSE_LIMIT,
            part='key',
            placed=naming_an_assertion,
        ),
        CallerText(
            model=TaskVerification,
            field='assertions',
            limit=PROSE_LIMIT,
            part='value',
            placed=as_an_assertion,
        ),
        CallerText(model=TaskMark, field='reason', limit=PROSE_LIMIT),
        CallerText(model=TaskFailedFix, field='hypothesis', limit=PROSE_LIMIT),
        CallerText(
            model=TicketRequest, field='context', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=TicketRequest,
            field='reference_urls',
            limit=PROSE_LIMIT,
            part='item',
            placed=in_a_list,
        ),
        CallerText(
            model=TicketRequest,
            field='investigations',
            limit=SLUG_LIMIT,
            part='item',
            placed=in_a_list,
        ),
        CallerText(
            model=TicketContext, field='context', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
    )
    TEXTS = (*IN_A_COLUMN, *IN_NO_COLUMN_OF_ITS_OWN)
    EACH_TEXT = tuple(
        pytest.param(text, id=f'{text.model.__name__}.{text.field}-{text.part}') for text in TEXTS
    )

    def test_is_listed_here_with_its_maximum(self) -> None:
        assert {(text.model.__name__, text.field) for text in self.TEXTS} == text_fields()

    @pytest.mark.parametrize('text', EACH_TEXT)
    def test_is_accepted_at_its_maximum(self, text: CallerText) -> None:
        assert text.refusals(text.limit) == []

    @pytest.mark.parametrize('text', EACH_TEXT)
    def test_is_refused_one_character_past_its_maximum(self, text: CallerText) -> None:
        assert text.refused_as in text.refusals(text.limit + 1)


class TestEveryFreeStringAToolAccepts:
    BOUND_OTHERWISE = frozenset({'enum', 'const', 'pattern'})

    @pytest.fixture
    def free_strings(self, state_server: StateServer) -> list[StringSchema]:
        published = [tool.input_schema for tool in state_server.tools().values()]
        return [
            string
            for string in strings_in(published)
            if not self.BOUND_OTHERWISE.intersection(string)
        ]

    def test_states_its_maximum_in_the_schema_its_tool_publishes(
        self, free_strings: list[StringSchema]
    ) -> None:
        assert free_strings != []
        assert [string for string in free_strings if 'maxLength' not in string] == []


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
                    'change': {'by': 'engineer', 'owned': [plain(PROSE_LIMIT + 1)]},
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
        (result,) = connected_server.call((name, arguments))

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
        with review_transaction(repository_database) as repository:
            repository.record_run(STARTED)
            repository.record_findings(RUN, [finding])
            repository.decisions.record_dispositions(RUN, [decided])
        return review_service.report(RUN, Shape.FULL).text

    def test_is_read_back_whole_and_leaves_its_run_readable(
        self, report_of_a_run_holding_it: str
    ) -> None:
        assert self.CITE in report_of_a_run_holding_it
        assert self.REASON in report_of_a_run_holding_it


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
        (result,) = connected_server.call((call.tool, call.arguments))

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
