"""The state tables as they are declared: lengths, server defaults, keys and indexes."""

import hashlib
import re
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import (
    DATABASE_NAME,
    SCHEMA_VERSION,
    Database,
    SchemaVersionError,
    open_database,
)
from mightymodels_plugin.core.declarative import (
    SHA_LIMIT,
    TASK_ID_LIMIT,
    TIMESTAMP_LIMIT,
    WORD_LIMIT,
    Base,
)
from mightymodels_plugin.core.repository_key import local_key
from mightymodels_plugin.core.routing import Depth, Scope
from mightymodels_plugin.core.run_id import RUN_ID_PATTERN
from mightymodels_plugin.core.task_id import TASK_ID_PATTERN
from mightymodels_plugin.tools.close.schema import Closing
from mightymodels_plugin.tools.close.tables import ClosingRow
from mightymodels_plugin.tools.contract.executor import TAIL_CHARS, tail
from mightymodels_plugin.tools.contract.schema import ContractCommand, Outcome, Phase
from mightymodels_plugin.tools.contract.tables import CommandRow, ReceiptRow
from mightymodels_plugin.tools.crashout import schema as crashout
from mightymodels_plugin.tools.crashout.tables import CrashoutRow
from mightymodels_plugin.tools.investigation.schema import EntryKind, LedgerEntry, Source
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.review.schema import (
    Decision,
    Disposition,
    Emphasis,
    EvidenceKind,
    FindingInput,
    Kind,
    ReportedSeverity,
    Result,
    ReviewScope,
    Severity,
)
from mightymodels_plugin.tools.review.tables import (
    FINDING_ID_LIMIT,
    RUN_ID_LIMIT,
    ReviewDispositionRow,
    ReviewFindingRow,
    ReviewOutcomeRow,
    ReviewRunRow,
)
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.similarity.schema import Scout, SimilarityKind
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow, SimilarityRow
from mightymodels_plugin.tools.task.schema import ArchitectMode, Implementer, Status
from mightymodels_plugin.tools.task.tables import AttemptRow, FailedFixRow, TaskRow, TransitionRow
from mightymodels_plugin.tools.tests.support import RowValues, filled_row, table_of
from mightymodels_plugin.tools.ticket.schema import TicketAnswers, TicketStatus
from mightymodels_plugin.tools.ticket.tables import TicketRow
from sqlalchemy.exc import IntegrityError

type Columns = tuple[str, ...]

REPOSITORY = 'repository_key'
SERIAL: Columns = ('id',)
OF_A_TICKET: Columns = (REPOSITORY, 'slug')
OF_A_RUN: Columns = (REPOSITORY, 'run_id')
OF_A_FINDING: Columns = (*OF_A_RUN, 'finding_id')
ANSWERS = TicketAnswers(
    summary='Retry queue drains slowly',
    scope=Scope.MED,
    compaction=False,
    branch='fix/retry-queue',
    context=('drain loop sleeps between batches',),
)
COMMAND = ContractCommand(id='T1.AC-1', argv=('uv', 'run', 'pytest'), approved_by='user')
FINDING = FindingInput(
    sources=('MV-1',),
    severity=ReportedSeverity.HIGH,
    title='the drain loop sleeps',
    location='src/queue.py:1',
    fix='fix it',
    verify='run the tests',
)
ENTRY = LedgerEntry(kind=EntryKind.OPEN, text='why does it sleep', source=Source.USER)
NO_REASON_GIVEN = Disposition(decision=Decision.FIX).reason
ABSENT_TEXT = ''


@dataclass(slots=True, kw_only=True, frozen=True)
class Shape:
    row_type: type[Base]
    key: Columns
    filtered_on: tuple[Columns, ...]
    parent: type[Base] | None = None
    unique: tuple[Columns, ...] = ()
    defaults: Mapping[str, object] = field(default_factory=dict)
    timestamp: str | None = 'at'


SHAPES = (
    Shape(
        row_type=TicketRow,
        key=OF_A_TICKET,
        filtered_on=(OF_A_TICKET,),
        unique=((REPOSITORY, 'ticket'),),
        defaults={
            'status': TicketStatus.STAGED,
            'investigations': list(ANSWERS.investigations),
            'auto_escalate': False,
        },
        timestamp='validated_at',
    ),
    Shape(
        row_type=TaskRow,
        key=(*OF_A_TICKET, 'task_id'),
        filtered_on=(OF_A_TICKET, (*OF_A_TICKET, 'task_id')),
        parent=TicketRow,
        defaults={'reasons': []},
        timestamp='updated_at',
    ),
    Shape(
        row_type=AttemptRow,
        key=SERIAL,
        filtered_on=(OF_A_TICKET, (*OF_A_TICKET, 'task_id', 'mode')),
        parent=TaskRow,
    ),
    Shape(
        row_type=FailedFixRow,
        key=SERIAL,
        filtered_on=(OF_A_TICKET, (*OF_A_TICKET, 'task_id')),
        parent=TaskRow,
    ),
    Shape(
        row_type=TransitionRow,
        key=SERIAL,
        filtered_on=((*OF_A_TICKET, 'after'),),
        parent=TaskRow,
    ),
    Shape(
        row_type=CommandRow,
        key=(*OF_A_TICKET, 'command_id'),
        filtered_on=(OF_A_TICKET,),
        defaults={'expect_exit': COMMAND.expect_exit, 'timeout': COMMAND.timeout},
        timestamp='approved_at',
    ),
    Shape(
        row_type=ReceiptRow,
        key=SERIAL,
        filtered_on=(OF_A_TICKET, (*OF_A_TICKET, 'command_id')),
        parent=CommandRow,
    ),
    Shape(
        row_type=ReviewRunRow,
        key=OF_A_RUN,
        filtered_on=((REPOSITORY,), OF_A_RUN, OF_A_TICKET),
        timestamp='created_at',
    ),
    Shape(
        row_type=ReviewFindingRow,
        key=OF_A_FINDING,
        filtered_on=(OF_A_RUN,),
        parent=ReviewRunRow,
        defaults={'kind': FINDING.kind, 'security': FINDING.security},
        timestamp=None,
    ),
    Shape(
        row_type=ReviewDispositionRow,
        key=OF_A_FINDING,
        filtered_on=(OF_A_RUN, OF_A_FINDING),
        parent=ReviewFindingRow,
        defaults={'reason': NO_REASON_GIVEN},
    ),
    Shape(
        row_type=ReviewOutcomeRow,
        key=OF_A_FINDING,
        filtered_on=(OF_A_RUN, OF_A_FINDING),
        parent=ReviewDispositionRow,
        defaults={'commit': ABSENT_TEXT, 'reason': ABSENT_TEXT},
    ),
    Shape(
        row_type=ClosingRow,
        key=OF_A_TICKET,
        filtered_on=(OF_A_TICKET,),
        parent=TicketRow,
        unique=((REPOSITORY, 'archive'),),
        defaults={'gotchas': list(Closing().gotchas)},
        timestamp='closed_at',
    ),
    Shape(
        row_type=LedgerEntryRow,
        key=(REPOSITORY, 'investigation_id', 'seq'),
        filtered_on=(
            (REPOSITORY,),
            (REPOSITORY, 'investigation_id'),
            (REPOSITORY, 'investigation_id', 'seq'),
        ),
        defaults={'supersedes': list(ENTRY.supersedes)},
    ),
    Shape(row_type=CrashoutRow, key=SERIAL, filtered_on=((REPOSITORY,),)),
    Shape(
        row_type=SimilarityRow,
        key=SERIAL,
        filtered_on=((REPOSITORY,), (REPOSITORY, 'kind', 'reference')),
        unique=((REPOSITORY, 'kind', 'reference'),),
    ),
    Shape(row_type=ScoutReportRow, key=SERIAL, filtered_on=((REPOSITORY,),)),
)
SHAPE_OF = {shape.row_type: shape for shape in SHAPES}


def by_table(shapes: Iterable[Shape]) -> list[object]:
    return [pytest.param(shape, id=shape.row_type.__tablename__) for shape in shapes]


EVERY_TABLE = by_table(SHAPES)
CHILD_TABLES = by_table(shape for shape in SHAPES if shape.parent is not None)
TABLES_WITH_ANOTHER_NATURAL_KEY = by_table(shape for shape in SHAPES if shape.unique)
TIMESTAMPS = [
    pytest.param(shape, shape.timestamp, id=shape.row_type.__tablename__)
    for shape in SHAPES
    if shape.timestamp is not None
]


def names_of(columns: Iterable[sql.Column[object]]) -> Columns:
    return tuple(column.name for column in columns)


def indexed_columns(row_type: type[Base]) -> list[Columns]:
    table = table_of(row_type)
    unique = (
        constraint
        for constraint in table.constraints
        if isinstance(constraint, sql.UniqueConstraint)
    )
    return [
        names_of(table.primary_key.columns),
        *(names_of(constraint.columns) for constraint in unique),
        *(names_of(index.columns) for index in table.indexes),
    ]


def led_by(filtered_on: Columns, row_type: type[Base]) -> list[Columns]:
    return [
        columns
        for columns in indexed_columns(row_type)
        if set(columns[: len(filtered_on)]) == set(filtered_on)
    ]


def lineage(shape: Shape) -> list[type[Base]]:
    if shape.parent is None:
        return [shape.row_type]
    return [shape.row_type, *lineage(SHAPE_OF[shape.parent])]


def stored_alone(database: Database, row_type: type[Base], **given: object) -> None:
    with database.transaction() as session:
        session.execute(sql.insert(table_of(row_type)).values(filled_row(row_type, **given)))


class TestTheDeclaredShapes:
    def test_every_table_the_database_creates_has_one(self) -> None:
        assert [shape.row_type for shape in SHAPES] == list(ROW_TYPES)


class TestStringColumns:
    LONGEST_IDS = (
        pytest.param('T999999', TASK_ID_PATTERN, TASK_ID_LIMIT, id='task-id'),
        pytest.param('20260928-120000', RUN_ID_PATTERN, RUN_ID_LIMIT, id='run-id'),
    )
    STORED_WORDS = (
        pytest.param(TicketStatus, id='ticket-status'),
        pytest.param(Scope, id='ticket-scope'),
        pytest.param(Status, id='task-status'),
        pytest.param(Implementer, id='attempt-worker'),
        pytest.param(ArchitectMode, id='attempt-mode'),
        pytest.param(Outcome, id='receipt-outcome'),
        pytest.param(Phase, id='receipt-phase'),
        pytest.param(ReviewScope, id='review-scope'),
        pytest.param(Depth, id='review-depth'),
        pytest.param(Emphasis, id='review-emphasis'),
        pytest.param(Severity, id='finding-severity'),
        pytest.param(Kind, id='finding-kind'),
        pytest.param(EvidenceKind, id='finding-evidence-kind'),
        pytest.param(Decision, id='disposition-decision'),
        pytest.param(Result, id='outcome-result'),
        pytest.param(EntryKind, id='ledger-entry-kind'),
        pytest.param(Source, id='ledger-entry-source'),
        pytest.param(crashout.Severity, id='crashout-severity'),
        pytest.param(crashout.Verdict, id='crashout-verdict'),
        pytest.param(SimilarityKind, id='similarity-kind'),
        pytest.param(Scout, id='scout-report-scout'),
    )
    LARGEST_COUNT = 2**63 - 1

    @pytest.mark.parametrize('shape', EVERY_TABLE)
    def test_every_string_column_declares_a_length(self, shape: Shape) -> None:
        unbounded = [
            column.name
            for column in table_of(shape.row_type).columns
            if isinstance(column.type, sql.String) and not column.type.length
        ]

        assert unbounded == []

    @pytest.mark.parametrize(('longest', 'pattern', 'limit'), LONGEST_IDS)
    def test_the_longest_id_its_pattern_admits_fills_the_declared_length(
        self, longest: str, pattern: str, limit: int
    ) -> None:
        assert re.fullmatch(pattern, longest) is not None
        assert re.fullmatch(pattern, f'{longest}0') is None
        assert len(longest) == limit

    @pytest.mark.parametrize('words', STORED_WORDS)
    def test_every_member_of_a_stored_enum_fits_a_word(self, words: type[StrEnum]) -> None:
        assert [word for word in words if len(word) > WORD_LIMIT] == []

    def test_the_clock_writes_a_timestamp_of_the_declared_length(self) -> None:
        assert len(now()) == TIMESTAMP_LIMIT

    def test_a_sha_256_digest_fills_the_declared_length(self) -> None:
        assert len(hashlib.sha256(b'').hexdigest()) == SHA_LIMIT

    def test_the_id_of_the_largest_count_of_findings_fits_the_declared_length(self) -> None:
        assert len(f'F{self.LARGEST_COUNT}') <= FINDING_ID_LIMIT

    def test_a_receipt_keeps_a_tail_no_longer_than_the_declared_length(self) -> None:
        declared = table_of(ReceiptRow).columns['stdout_tail'].type

        assert isinstance(declared, sql.String)
        assert len(tail('x' * 2 * TAIL_CHARS)) == declared.length


class TestServerDefaults:
    A_MINUTE = timedelta(minutes=1)

    @pytest.fixture
    def row_left_to_the_database(self, shape: Shape, repository_database: Database) -> RowValues:
        table = table_of(shape.row_type)
        with repository_database.engine.connect() as connection:
            connection.execute(sql.insert(table).values(filled_row(shape.row_type)))
            return dict(connection.execute(sql.select(table)).mappings().one())

    @pytest.mark.parametrize('shape', EVERY_TABLE)
    def test_no_default_is_known_to_the_application_alone(self, shape: Shape) -> None:
        columns = table_of(shape.row_type).columns

        assert [column.name for column in columns if column.default is not None] == []

    @pytest.mark.parametrize('shape', EVERY_TABLE)
    def test_only_the_columns_the_plugin_has_a_default_for_carry_one(self, shape: Shape) -> None:
        defaulted = {
            column.name
            for column in table_of(shape.row_type).columns
            if column.server_default is not None
        }

        assert defaulted == set(shape.defaults) | {shape.timestamp} - {None}

    @pytest.mark.parametrize('shape', EVERY_TABLE)
    def test_a_column_left_out_reads_as_the_plugin_writes_it(
        self, shape: Shape, row_left_to_the_database: RowValues
    ) -> None:
        left_out = {name: row_left_to_the_database[name] for name in shape.defaults}

        assert left_out == shape.defaults

    @pytest.mark.parametrize(('shape', 'timestamp'), TIMESTAMPS)
    def test_a_timestamp_left_out_is_the_time_of_the_write_as_the_clock_writes_it(
        self, timestamp: str, row_left_to_the_database: RowValues
    ) -> None:
        stored = str(row_left_to_the_database[timestamp])
        written = datetime.fromisoformat(stored)

        assert written.isoformat(timespec='seconds') == stored
        assert abs(datetime.fromisoformat(now()) - written) < self.A_MINUTE


class TestForeignKeys:
    @pytest.mark.parametrize('shape', EVERY_TABLE)
    def test_a_child_names_its_parent_by_the_parents_whole_key(self, shape: Shape) -> None:
        declared = [
            (constraint.referred_table.name, names_of(constraint.columns))
            for constraint in table_of(shape.row_type).foreign_key_constraints
        ]
        parents = [] if shape.parent is None else [SHAPE_OF[shape.parent]]

        assert declared == [(parent.row_type.__tablename__, parent.key) for parent in parents]

    @pytest.mark.parametrize('shape', CHILD_TABLES)
    def test_a_row_whose_parent_is_missing_is_refused_when_it_is_committed(
        self, shape: Shape, repository_database: Database
    ) -> None:
        with pytest.raises(IntegrityError, match='FOREIGN KEY constraint failed'):
            stored_alone(repository_database, shape.row_type)

    @pytest.mark.parametrize('shape', CHILD_TABLES)
    def test_a_child_written_before_its_parents_in_one_transaction_is_kept(
        self, shape: Shape, repository_database: Database
    ) -> None:
        with repository_database.transaction() as session:
            for row_type in lineage(shape):
                session.execute(sql.insert(table_of(row_type)).values(filled_row(row_type)))
        with repository_database.transaction() as session:
            kept = session.execute(sql.select(table_of(shape.row_type))).all()

        assert len(kept) == 1


class TestNaturalKeys:
    @pytest.mark.parametrize('shape', EVERY_TABLE)
    def test_a_table_keyed_by_names_is_keyed_under_the_repository_first(self, shape: Shape) -> None:
        assert names_of(table_of(shape.row_type).primary_key.columns) == shape.key
        assert shape.key in {SERIAL, (REPOSITORY, *shape.key[1:])}

    @pytest.mark.parametrize('shape', EVERY_TABLE)
    def test_a_natural_key_that_is_not_the_primary_key_is_declared_unique(
        self, shape: Shape
    ) -> None:
        declared = [
            names_of(constraint.columns)
            for constraint in table_of(shape.row_type).constraints
            if isinstance(constraint, sql.UniqueConstraint)
        ]

        assert declared == list(shape.unique)

    @pytest.mark.parametrize('shape', TABLES_WITH_ANOTHER_NATURAL_KEY)
    def test_a_second_row_under_a_natural_key_already_taken_is_refused(
        self, shape: Shape, repository_database: Database
    ) -> None:
        with (
            pytest.raises(IntegrityError, match='UNIQUE constraint failed'),
            repository_database.transaction() as session,
        ):
            session.execute(
                sql.insert(table_of(shape.row_type)),
                [filled_row(shape.row_type, slug=slug) for slug in ('first', 'second')],
            )


class TestIndexes:
    @pytest.mark.parametrize('shape', EVERY_TABLE)
    def test_the_columns_a_read_filters_on_lead_an_index(self, shape: Shape) -> None:
        unindexed = [
            filtered_on
            for filtered_on in shape.filtered_on
            if not led_by(filtered_on, shape.row_type)
        ]

        assert unindexed == []

    @pytest.mark.parametrize('shape', EVERY_TABLE)
    def test_the_repository_key_leads_an_index_of_every_table(self, shape: Shape) -> None:
        assert led_by((REPOSITORY,), shape.row_type) != []

    def test_the_review_runs_of_a_ticket_are_found_by_an_index_on_the_slug(self) -> None:
        assert led_by(OF_A_TICKET, ReviewRunRow) == [(*OF_A_TICKET, 'run_id')]


class TestAFileStampedByAnotherSchema:
    ANOTHER_VERSION = SCHEMA_VERSION + 1

    @pytest.fixture
    def stamped_by_another_schema(self, tmp_path: Path) -> Path:
        database_file = tmp_path.joinpath(DATABASE_NAME)
        with closing(sqlite3.connect(database_file)) as connection:
            connection.execute(f'PRAGMA user_version = {self.ANOTHER_VERSION}')
        return database_file

    def test_opening_it_is_refused_with_the_file_and_the_version_found(
        self, stamped_by_another_schema: Path, tmp_path: Path
    ) -> None:
        with (
            pytest.raises(SchemaVersionError) as refused,
            open_database(stamped_by_another_schema, local_key(tmp_path), ROW_TYPES),
        ):
            pass

        assert (refused.value.database_file, refused.value.found) == (
            stamped_by_another_schema,
            self.ANOTHER_VERSION,
        )
