"""Paired pass/fail comparison of two configurations on the same tasks, as YAML."""

import argparse
import logging
import sys
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from statistics import NormalDist

import msgspec
import numpy as np
import polars as pl
from scipy.stats import binomtest

from python_harness.scripts.report import (
    LAUNCHER,
    ContractViolationError,
    Report,
    UnreadableInputError,
    describe_arguments,
    run_command,
)

COMMAND = f'{LAUNCHER} paired-compare'
SMALL_SAMPLE = 30

logger = logging.getLogger('paired_compare')


class UnsupportedFormatError(UnreadableInputError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path.name}: expected a .csv or .parquet file')


class InputReadError(UnreadableInputError):
    def __init__(self, path: Path, cause: Exception) -> None:
        super().__init__(f'cannot read {path}: {cause}')


class MissingColumnError(ContractViolationError):
    def __init__(self, column: str) -> None:
        super().__init__(f'column {column!r} is not in the results table')


class EmptyResultsError(ContractViolationError):
    def __init__(self) -> None:
        super().__init__('the results table has no rows')


class NullOutcomeError(ContractViolationError):
    def __init__(self, column: str, nulls: int) -> None:
        super().__init__(f'column {column!r} has {nulls} null outcomes; resolve them first')


class NonBinaryOutcomeError(ContractViolationError):
    def __init__(self, column: str, values: list[object]) -> None:
        super().__init__(f'column {column!r} must hold only 0/1 or booleans, found {values}')


class DuplicateTaskError(ContractViolationError):
    def __init__(self, column: str, duplicates: int) -> None:
        super().__init__(f'{duplicates} task ids repeat in {column!r}; pairing is ambiguous')


class LevelOutOfRangeError(ContractViolationError):
    def __init__(self, level: float) -> None:
        super().__init__(f'confidence level must be in (0, 1), got {level}')


class NonPositiveResamplesError(ContractViolationError):
    def __init__(self, resamples: int) -> None:
        super().__init__(f'resamples must be positive, got {resamples}')


@dataclass(frozen=True, slots=True, kw_only=True)
class ComparisonOptions:
    old_column: str
    new_column: str
    key_column: str | None = None
    level: float = 0.95
    resamples: int = 20_000
    seed: int = 42

    @property
    def outcome_columns(self) -> tuple[str, str]:
        return self.old_column, self.new_column


class Interval(msgspec.Struct, frozen=True, kw_only=True):
    lower: float
    upper: float
    level: float
    method: str


class RateEstimate(msgspec.Struct, frozen=True, kw_only=True):
    successes: int
    trials: int
    rate: float
    interval: Interval


class Difference(msgspec.Struct, frozen=True, kw_only=True):
    value: float
    unit: str
    interval: Interval


class DiscordantPairs(msgspec.Struct, frozen=True, kw_only=True):
    new_only: int
    old_only: int

    @property
    def total(self) -> int:
        return self.new_only + self.old_only


class PairedComparison(msgspec.Struct, frozen=True, kw_only=True):
    n_tasks: int
    old: RateEstimate
    new: RateEstimate
    difference: Difference
    discordant: DiscordantPairs
    exact_mcnemar_p: float


def read_results(path: Path) -> pl.DataFrame:
    match path.suffix.lower():
        case '.csv':
            reader = pl.read_csv
        case '.parquet':
            reader = pl.read_parquet
        case _:
            raise UnsupportedFormatError(path)
    try:
        return reader(path)
    except (OSError, pl.exceptions.PolarsError) as error:
        raise InputReadError(path, error) from error


def check_columns_exist(frame: pl.DataFrame, options: ComparisonOptions) -> None:
    required = (*options.outcome_columns, *filter(None, (options.key_column,)))
    absent = next((column for column in required if column not in frame.columns), None)
    if absent is not None:
        raise MissingColumnError(absent)


def check_outcome(series: pl.Series) -> None:
    if series.null_count():
        raise NullOutcomeError(series.name, series.null_count())
    values = series.unique().to_list()
    is_binary = series.dtype.is_integer() or series.dtype == pl.Boolean
    if not (is_binary and set(values) <= {0, 1}):
        raise NonBinaryOutcomeError(series.name, values)


def check_unique_keys(frame: pl.DataFrame, key_column: str | None) -> None:
    duplicates = 0 if key_column is None else int(frame[key_column].is_duplicated().sum())
    if duplicates:
        raise DuplicateTaskError(str(key_column), duplicates)


def check_table(frame: pl.DataFrame, options: ComparisonOptions) -> None:
    if not 0 < options.level < 1:
        raise LevelOutOfRangeError(options.level)
    if options.resamples < 1:
        raise NonPositiveResamplesError(options.resamples)
    check_columns_exist(frame, options)
    if frame.is_empty():
        raise EmptyResultsError
    for column in options.outcome_columns:
        check_outcome(frame.get_column(column))
    check_unique_keys(frame, options.key_column)


def wilson_interval(successes: int, trials: int, level: float) -> Interval:
    z = NormalDist().inv_cdf((1 + level) / 2)
    proportion = successes / trials
    denominator = 1 + z * z / trials
    center = (proportion + z * z / (2 * trials)) / denominator
    variance = proportion * (1 - proportion) / trials + z * z / (4 * trials * trials)
    half_width = z * sqrt(variance) / denominator
    return Interval(
        lower=min(proportion, max(0.0, center - half_width)),
        upper=max(proportion, min(1.0, center + half_width)),
        level=level,
        method='Wilson score; independent trials',
    )


def estimate_rate(outcomes: np.ndarray, level: float) -> RateEstimate:
    successes = int(outcomes.sum())
    return RateEstimate(
        successes=successes,
        trials=len(outcomes),
        rate=successes / len(outcomes),
        interval=wilson_interval(successes, len(outcomes), level),
    )


def bootstrap_difference(
    discordant: DiscordantPairs, n_tasks: int, options: ComparisonOptions
) -> Interval:
    ties = n_tasks - discordant.total
    counts = np.array([discordant.old_only, ties, discordant.new_only])
    rng = np.random.default_rng(options.seed)
    draws = rng.multinomial(n_tasks, counts / n_tasks, size=options.resamples)
    means = draws @ np.array([-1, 0, 1]) / n_tasks
    tail = (1 - options.level) / 2
    lower, upper = np.quantile(means, [tail, 1 - tail])
    return Interval(
        lower=float(lower),
        upper=float(upper),
        level=options.level,
        method=f'multinomial-count percentile bootstrap, {options.resamples} resamples',
    )


def collect_caveats(comparison: PairedComparison) -> tuple[str, ...]:
    interval = comparison.difference.interval
    candidates = (
        (
            comparison.n_tasks < SMALL_SAMPLE,
            f'only {comparison.n_tasks} paired tasks: weak population evidence',
        ),
        (
            comparison.discordant.total == 0,
            'no discordant pairs: the paired test is uninformative',
        ),
        (interval.lower <= 0 <= interval.upper, 'the difference interval includes zero'),
    )
    return tuple(message for applies, message in candidates if applies)


def compare(frame: pl.DataFrame, options: ComparisonOptions) -> PairedComparison:
    old = frame[options.old_column].cast(pl.Int64).to_numpy()
    new = frame[options.new_column].cast(pl.Int64).to_numpy()
    discordant = DiscordantPairs(
        new_only=int(((new == 1) & (old == 0)).sum()),
        old_only=int(((new == 0) & (old == 1)).sum()),
    )
    interval = bootstrap_difference(discordant, len(old), options)
    tested = discordant.total
    p_value = binomtest(discordant.new_only, tested).pvalue if tested else 1.0
    return PairedComparison(
        n_tasks=len(old),
        old=estimate_rate(old, options.level),
        new=estimate_rate(new, options.level),
        difference=Difference(
            value=float((new - old).mean()),
            unit='proportion_difference',
            interval=interval,
        ),
        discordant=discordant,
        exact_mcnemar_p=float(p_value),
    )


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=COMMAND, description=__doc__)
    parser.add_argument('results', type=Path, help='CSV or Parquet, one row per task')
    parser.add_argument('--old', required=True, help='0/1 outcome column for the old arm')
    parser.add_argument('--new', required=True, help='0/1 outcome column for the new arm')
    parser.add_argument('--key', help='task key column; checked for uniqueness')
    parser.add_argument('--level', type=float, default=0.95)
    parser.add_argument('--resamples', type=int, default=20_000)
    parser.add_argument('--seed', type=int, default=42)
    return parser.parse_args(argv)


def options_from(arguments: argparse.Namespace) -> ComparisonOptions:
    return ComparisonOptions(
        old_column=arguments.old,
        new_column=arguments.new,
        key_column=arguments.key,
        level=arguments.level,
        resamples=arguments.resamples,
        seed=arguments.seed,
    )


def build_report(argv: list[str]) -> Report[PairedComparison]:
    arguments = parse_arguments(argv)
    options = options_from(arguments)
    frame = read_results(arguments.results)
    check_table(frame, options)
    comparison = compare(frame, options)
    return Report(
        command=COMMAND,
        arguments=describe_arguments(arguments),
        result=comparison,
        caveats=collect_caveats(comparison),
    )


def main(argv: list[str]) -> int:
    return run_command(logger, build_report, argv)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
