"""Profile a Parquet or CSV file, or the cardinality of a join, with DuckDB, as YAML."""

import argparse
import logging
import operator
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import reduce
from pathlib import Path
from typing import cast

import duckdb
import msgspec
from duckdb import ColumnExpression, ConstantExpression, FunctionExpression

from python_harness.scripts.report import (
    LAUNCHER,
    ContractViolationError,
    Report,
    UnreadableInputError,
    describe_arguments,
    run_command,
)

COMMAND = f'{LAUNCHER} profile-data'
EXAMPLE_LIMIT = 5
ROWS_PER_KEY = 'rows_per_key'

logger = logging.getLogger('profile_data')

type Relation = duckdb.DuckDBPyRelation
type Expression = duckdb.Expression


class UnsupportedFormatError(UnreadableInputError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path.name}: expected .parquet or .csv (globs allowed)')


class InputReadError(UnreadableInputError):
    def __init__(self, cause: Exception) -> None:
        super().__init__(f'DuckDB could not read or query the input: {cause}')


class MissingKeyColumnError(ContractViolationError):
    def __init__(self, source: str, missing: list[str]) -> None:
        super().__init__(f'{source} has no column(s) {", ".join(missing)}')


@dataclass(frozen=True, slots=True, kw_only=True)
class KeyedTable:
    source: str
    relation: Relation
    keys: tuple[str, ...]

    @property
    def quoted_keys(self) -> tuple[str, ...]:
        return tuple(map(quote_identifier, self.keys))

    @property
    def any_key_null(self) -> str:
        return ' OR '.join(f'{key} IS NULL' for key in self.quoted_keys)


class ColumnProfile(msgspec.Struct, frozen=True, kw_only=True):
    name: str
    type: str
    nulls: int
    approx_distinct: int
    min: str | None
    max: str | None


class KeyCheck(msgspec.Struct, frozen=True, kw_only=True):
    columns: tuple[str, ...]
    unique: bool
    duplicate_keys: int
    rows_in_duplicate_keys: int
    null_key_rows: int
    duplicate_examples: tuple[str, ...]


class TableProfile(msgspec.Struct, frozen=True, kw_only=True, omit_defaults=True):
    source: str
    rows: int
    columns: tuple[ColumnProfile, ...]
    key: KeyCheck | None = None


class JoinSide(msgspec.Struct, frozen=True, kw_only=True):
    source: str
    rows: int
    distinct_keys: int
    duplicate_keys: int
    max_rows_per_key: int
    null_key_rows: int
    unmatched_keys: int
    unmatched_rows: int


class JoinProfile(msgspec.Struct, frozen=True, kw_only=True):
    keys: tuple[str, ...]
    observed_cardinality: str
    left: JoinSide
    right: JoinSide
    inner_join_rows: int
    left_join_rows: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Profiled:
    result: TableProfile | JoinProfile
    caveats: tuple[str, ...]


type Command = Callable[[duckdb.DuckDBPyConnection, argparse.Namespace], Profiled]


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def key_alias(position: int) -> str:
    return f'key_{position}'


def open_table(connection: duckdb.DuckDBPyConnection, path: Path) -> Relation:
    match path.suffix.lower():
        case '.parquet':
            return connection.read_parquet(str(path))
        case '.csv':
            return connection.read_csv(str(path))
        case _:
            raise UnsupportedFormatError(path)


def check_keys_exist(table: KeyedTable) -> None:
    missing = [key for key in table.keys if key not in table.relation.columns]
    if missing:
        raise MissingKeyColumnError(table.source, missing)


def scalar(relation: Relation, expression: Expression) -> int:
    row = relation.aggregate([expression]).fetchone()
    return 0 if row is None or row[0] is None else int(row[0])


def count_rows(relation: Relation) -> int:
    return scalar(relation, FunctionExpression('count_star'))


def sum_of(relation: Relation, column: str) -> int:
    return scalar(relation, FunctionExpression('sum', ColumnExpression(column)))


def max_of(relation: Relation, column: str) -> int:
    return scalar(relation, FunctionExpression('max', ColumnExpression(column)))


def null_counts(relation: Relation) -> dict[str, int]:
    expressions = ', '.join(
        f'count(*) - count({quote_identifier(name)})' for name in relation.columns
    )
    row = relation.aggregate(expressions).fetchone() or ()
    return dict(zip(relation.columns, map(int, row), strict=True))


def profile_columns(
    connection: duckdb.DuckDBPyConnection, relation: Relation
) -> tuple[ColumnProfile, ...]:
    nulls = null_counts(relation)
    connection.register('profiled_source', relation)
    summary = connection.sql('SUMMARIZE profiled_source').fetchall()
    return tuple(
        ColumnProfile(
            name=name,
            type=column_type,
            nulls=nulls[name],
            approx_distinct=int(approx_unique),
            min=None if lowest is None else str(lowest),
            max=None if highest is None else str(highest),
        )
        for name, column_type, lowest, highest, approx_unique, *_ in summary
    )


def rows_per_key(table: KeyedTable) -> Relation:
    present = table.relation.filter(f'NOT ({table.any_key_null})')
    keys = (f'{key} AS {key_alias(position)}' for position, key in enumerate(table.quoted_keys))
    return present.aggregate(f'{", ".join(keys)}, count(*) AS {ROWS_PER_KEY}', 'ALL')


def describe_duplicate(row: tuple[object, ...]) -> str:
    *key, rows = row
    return f'{", ".join(map(str, key))} ({rows} rows)'


def check_key(table: KeyedTable) -> KeyCheck:
    duplicates = rows_per_key(table).filter(ColumnExpression(ROWS_PER_KEY) > ConstantExpression(1))
    examples = duplicates.limit(EXAMPLE_LIMIT).fetchall()
    duplicate_keys = count_rows(duplicates)
    return KeyCheck(
        columns=table.keys,
        unique=duplicate_keys == 0,
        duplicate_keys=duplicate_keys,
        rows_in_duplicate_keys=sum_of(duplicates, ROWS_PER_KEY),
        null_key_rows=count_rows(table.relation.filter(table.any_key_null)),
        duplicate_examples=tuple(describe_duplicate(row) for row in examples),
    )


def matched_key_counts(left: KeyedTable, right: KeyedTable) -> Relation:
    left_counts = rows_per_key(left).set_alias('l')
    right_counts = rows_per_key(right).set_alias('r')
    condition = reduce(
        operator.and_,
        (
            ColumnExpression('l', key_alias(position)) == ColumnExpression('r', key_alias(position))
            for position in range(len(left.keys))
        ),
    )
    joined = left_counts.join(right_counts, condition, how='outer')
    return joined.select(
        ColumnExpression('l', ROWS_PER_KEY).alias('left_rows'),
        ColumnExpression('r', ROWS_PER_KEY).alias('right_rows'),
    )


def describe_side(table: KeyedTable, counts: Relation, *, side: str, other: str) -> JoinSide:
    own = counts.filter(ColumnExpression(side).isnotnull())
    unmatched = own.filter(ColumnExpression(other).isnull())
    return JoinSide(
        source=table.source,
        rows=count_rows(table.relation),
        distinct_keys=count_rows(own),
        duplicate_keys=count_rows(own.filter(ColumnExpression(side) > ConstantExpression(1))),
        max_rows_per_key=max_of(own, side),
        null_key_rows=count_rows(table.relation.filter(table.any_key_null)),
        unmatched_keys=count_rows(unmatched),
        unmatched_rows=sum_of(unmatched, side),
    )


def key_caveats(key: KeyCheck | None) -> tuple[str, ...]:
    if key is None:
        return ()
    candidates = (
        (not key.unique, f'{key.duplicate_keys} key values repeat: not a unique key'),
        (key.null_key_rows > 0, f'{key.null_key_rows} rows have a null key'),
    )
    return tuple(message for applies, message in candidates if applies)


def join_caveats(left: JoinSide, right: JoinSide) -> tuple[str, ...]:
    candidates = (
        (right.duplicate_keys > 0, 'right keys repeat: a left join multiplies left rows'),
        (left.duplicate_keys > 0, 'left keys repeat: check the intended grain'),
        (left.unmatched_rows > 0, f'{left.unmatched_rows} left rows have no right match'),
        (left.null_key_rows > 0, f'{left.null_key_rows} left rows have null keys'),
        (right.null_key_rows > 0, f'{right.null_key_rows} right rows have null keys'),
    )
    return tuple(message for applies, message in candidates if applies)


def profile_join(left: KeyedTable, right: KeyedTable) -> JoinProfile:
    counts = matched_key_counts(left, right)
    left_side = describe_side(left, counts, side='left_rows', other='right_rows')
    right_side = describe_side(right, counts, side='right_rows', other='left_rows')
    both = counts.filter(
        ColumnExpression('left_rows').isnotnull() & ColumnExpression('right_rows').isnotnull()
    )
    inner_rows = scalar(
        both,
        FunctionExpression('sum', ColumnExpression('left_rows') * ColumnExpression('right_rows')),
    )
    left_grain = 'm' if left_side.duplicate_keys else '1'
    right_grain = 'm' if right_side.duplicate_keys else '1'
    return JoinProfile(
        keys=left.keys,
        observed_cardinality=f'{left_grain}:{right_grain}',
        left=left_side,
        right=right_side,
        inner_join_rows=inner_rows,
        left_join_rows=inner_rows + left_side.unmatched_rows + left_side.null_key_rows,
    )


def run_profile(connection: duckdb.DuckDBPyConnection, arguments: argparse.Namespace) -> Profiled:
    table = KeyedTable(
        source=str(arguments.path),
        relation=open_table(connection, arguments.path),
        keys=tuple(arguments.key or ()),
    )
    check_keys_exist(table)
    key = check_key(table) if table.keys else None
    profile = TableProfile(
        source=table.source,
        rows=count_rows(table.relation),
        columns=profile_columns(connection, table.relation),
        key=key,
    )
    return Profiled(result=profile, caveats=key_caveats(key))


def run_join(connection: duckdb.DuckDBPyConnection, arguments: argparse.Namespace) -> Profiled:
    keys = tuple(arguments.key)
    left, right = (
        KeyedTable(source=str(path), relation=open_table(connection, path), keys=keys)
        for path in (arguments.left, arguments.right)
    )
    check_keys_exist(left)
    check_keys_exist(right)
    joined = profile_join(left, right)
    return Profiled(result=joined, caveats=join_caveats(joined.left, joined.right))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=COMMAND, description=__doc__)
    commands = parser.add_subparsers(dest='subcommand', required=True)
    profile = commands.add_parser('profile', help='schema, nulls, distinct counts, key check')
    profile.add_argument('path', type=Path)
    profile.add_argument('--key', action='append', help='key column; repeat for composite')
    profile.set_defaults(command=run_profile)
    join = commands.add_parser('join', help='observed cardinality of LEFT join RIGHT')
    join.add_argument('left', type=Path)
    join.add_argument('right', type=Path)
    join.add_argument(
        '--key', action='append', required=True, help='key column; repeat for composite'
    )
    join.set_defaults(command=run_join)
    return parser


def execute(connection: duckdb.DuckDBPyConnection, arguments: argparse.Namespace) -> Profiled:
    try:
        command = cast('Command', arguments.command)
        return command(connection, arguments)
    except duckdb.Error as error:
        raise InputReadError(error) from error


def build_report(argv: list[str]) -> Report[TableProfile | JoinProfile]:
    arguments = build_parser().parse_args(argv)
    with duckdb.connect() as connection:
        profiled = execute(connection, arguments)
    return Report(
        command=f'{COMMAND} {arguments.subcommand}',
        arguments=describe_arguments(arguments),
        result=profiled.result,
        caveats=profiled.caveats,
    )


def main(argv: list[str]) -> int:
    return run_command(logger, build_report, argv)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
