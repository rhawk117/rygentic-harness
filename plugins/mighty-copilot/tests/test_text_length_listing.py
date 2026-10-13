from collections.abc import Callable, Collection, Generator
from dataclasses import dataclass
from typing import TypeAliasType, get_args

import pytest
import sqlalchemy as sql
from mightymodels.core.declarative import PROSE_LIMIT, Base
from mightymodels.core.slug import SLUG_LIMIT
from mightymodels.tools.close.schema import Closing
from mightymodels.tools.close.tables import ClosingRow
from mightymodels.tools.contract.schema import ContractCommand
from mightymodels.tools.contract.tables import CommandRow
from mightymodels.tools.crashout.schema import CrashoutEntry
from mightymodels.tools.crashout.tables import CrashoutRow
from mightymodels.tools.failed_fix.schema import FailedFixPayload, TaskFailedFix
from mightymodels.tools.investigation.schema import InvestigationStartRequest, LedgerEntry
from mightymodels.tools.investigation.tables import LedgerEntryRow
from mightymodels.tools.request import RequestModel
from mightymodels.tools.review.schema import (
    DisposeRequest,
    Disposition,
    Evidence,
    FindingInput,
    ResolvePayload,
    StartRequest,
)
from mightymodels.tools.review.tables import (
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels.tools.similarity.schema import SimilarityRequest, SpooledReport
from mightymodels.tools.similarity.tables import ScoutReportRow
from mightymodels.tools.task.schema import (
    MarkTaskPayload,
    StartTaskPayload,
    TaskMark,
    TaskStart,
    TaskVerification,
    TooLargeTaskStart,
    VerifyTaskPayload,
)
from mightymodels.tools.task.tables import TaskRow
from mightymodels.tools.tests.support import StateServer, table_of
from mightymodels.tools.tests.valid_requests import VALID, finding_id, plain
from mightymodels.tools.ticket.schema import TicketContext, TicketInterview
from mightymodels.tools.ticket.tables import TicketRow
from pydantic import ValidationError

type Placed = Callable[[str], object]
type Spelled = Callable[[int], str]
type StringSchema = Collection[object]

TOO_LONG = 'string_too_long'
OFF_THE_PATTERN = 'string_pattern_mismatch'


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


def source_id(length: int) -> str:
    return 'MV-' + '1' * (length - 3)


def task_id(length: int) -> str:
    return 'T' + '1' * (length - 1)


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
        stored(TicketInterview, 'summary', TicketRow, 'summary'),
        stored(TicketInterview, 'branch', TicketRow, 'branch'),
        stored(TicketInterview, 'jira', TicketRow, 'jira'),
        CallerText(
            model=StartTaskPayload,
            field='task_id',
            limit=length_of(TaskRow, 'task_id'),
            spelled=task_id,
            refused_as=OFF_THE_PATTERN,
        ),
        CallerText(
            model=VerifyTaskPayload,
            field='task_id',
            limit=length_of(TaskRow, 'task_id'),
            spelled=task_id,
            refused_as=OFF_THE_PATTERN,
        ),
        CallerText(
            model=MarkTaskPayload,
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
            model=TaskStart, field='acceptance', limit=PROSE_LIMIT, part='item', placed=in_a_list
        ),
        CallerText(
            model=TooLargeTaskStart,
            field='owned',
            limit=PROSE_LIMIT,
            part='item',
            placed=in_a_list,
        ),
        CallerText(
            model=TooLargeTaskStart,
            field='acceptance',
            limit=PROSE_LIMIT,
            part='item',
            placed=in_a_list,
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
        CallerText(model=SimilarityRequest, field='query', limit=PROSE_LIMIT),
        CallerText(
            model=TicketInterview,
            field='context',
            limit=PROSE_LIMIT,
            part='item',
            placed=in_a_list,
        ),
        CallerText(
            model=TicketInterview,
            field='reference_urls',
            limit=PROSE_LIMIT,
            part='item',
            placed=in_a_list,
        ),
        CallerText(
            model=TicketInterview,
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
