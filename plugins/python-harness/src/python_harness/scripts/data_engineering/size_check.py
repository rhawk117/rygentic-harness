"""Size arithmetic for data work before running it: bytes, rows and fit counts as YAML."""

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from math import log10

import msgspec
import numpy as np

from python_harness.scripts.report import (
    LAUNCHER,
    ContractViolationError,
    Report,
    describe_arguments,
    run_command,
)

COMMAND = f'{LAUNCHER} size-check'
DECIMAL_UNITS = ('B', 'kB', 'MB', 'GB', 'TB', 'PB', 'EB')
SECONDS_PER_HOUR = 3_600
EXCLUSIONS = 'excludes indexes, metadata, input copies, temporaries and process overhead'

logger = logging.getLogger('size_check')

type Estimator = Callable[[argparse.Namespace], Sized]


class NegativeQuantityError(ContractViolationError):
    def __init__(self, names: list[str]) -> None:
        super().__init__(f'quantities must be nonnegative: {", ".join(names)}')


class UnknownDtypeError(ContractViolationError):
    def __init__(self, dtype: str) -> None:
        super().__init__(f'{dtype!r} is not a NumPy dtype name')


class QuantityTooLargeError(ContractViolationError):
    def __init__(self) -> None:
        super().__init__('quantities are too large to estimate')


class SizeEstimate(msgspec.Struct, frozen=True, kw_only=True, omit_defaults=True):
    quantity: str
    elements: int
    unit: str
    bytes: int | None = None
    readable: str | None = None
    comparison: str | None = None
    serial_hours: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Sized:
    estimate: SizeEstimate
    caveats: tuple[str, ...]


def readable_bytes(size: int) -> str:
    exponent = min(int(log10(size)) // 3, len(DECIMAL_UNITS) - 1) if size else 0
    return f'{size / 1000**exponent:.3g} {DECIMAL_UNITS[exponent]}'


def is_dtype_name(name: str) -> bool:
    try:
        np.dtype(name)
    except (TypeError, SyntaxError):
        return False
    return True


def item_size(dtype: str) -> int:
    return np.dtype(dtype).itemsize


def byte_estimate(quantity: str, elements: int, dtype: str) -> Sized:
    size = elements * item_size(dtype)
    return Sized(
        estimate=SizeEstimate(
            quantity=quantity,
            elements=elements,
            unit=f'{dtype} values',
            bytes=size,
            readable=readable_bytes(size),
        ),
        caveats=(EXCLUSIONS,),
    )


def estimate_dense(arguments: argparse.Namespace) -> Sized:
    elements = arguments.rows * arguments.cols
    return byte_estimate('dense array', elements, arguments.dtype)


def estimate_pairwise(arguments: argparse.Namespace) -> Sized:
    return byte_estimate('n by n pairwise output', arguments.n**2, arguments.dtype)


def estimate_embeddings(arguments: argparse.Namespace) -> Sized:
    elements = arguments.n * arguments.dim
    return byte_estimate('embedding vectors', elements, arguments.dtype)


def estimate_sparse(arguments: argparse.Namespace) -> Sized:
    index_bytes = item_size(arguments.index_dtype)
    entry_bytes = item_size(arguments.dtype) + index_bytes
    size = arguments.nnz * entry_bytes + (arguments.rows + 1) * index_bytes
    dense = arguments.rows * arguments.cols * item_size(arguments.dtype)
    return Sized(
        estimate=SizeEstimate(
            quantity='CSR sparse matrix',
            elements=arguments.nnz,
            unit='stored nonzeros',
            bytes=size,
            readable=readable_bytes(size),
            comparison=f'dense equivalent {readable_bytes(dense)}',
        ),
        caveats=(
            EXCLUSIONS,
            f'indices and row pointers stored as {arguments.index_dtype}',
        ),
    )


def estimate_join(arguments: argparse.Namespace) -> Sized:
    return Sized(
        estimate=SizeEstimate(
            quantity='inner join output for one key',
            elements=arguments.left_matches * arguments.right_matches,
            unit='rows',
        ),
        caveats=(f'sum this over keys for the whole join; {LAUNCHER} profile-data join does',),
    )


def estimate_fits(arguments: argparse.Namespace) -> Sized:
    fits = arguments.configs * arguments.folds * arguments.repeats
    hours = None if arguments.seconds_per_fit is None else fits * arguments.seconds_per_fit
    return Sized(
        estimate=SizeEstimate(
            quantity='model fits',
            elements=fits,
            unit='fits',
            serial_hours=None if hours is None else hours / SECONDS_PER_HOUR,
        ),
        caveats=('excludes final refits, calibration and nested search',),
    )


def add_command(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    estimator: Estimator,
) -> argparse.ArgumentParser:
    parser = commands.add_parser(name)
    parser.set_defaults(estimator=estimator)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=COMMAND, description=__doc__)
    commands = parser.add_subparsers(dest='subcommand', required=True)
    dense = add_command(commands, 'dense', estimate_dense)
    dense.add_argument('--rows', type=int, required=True)
    dense.add_argument('--cols', type=int, required=True)
    pairwise = add_command(commands, 'pairwise', estimate_pairwise)
    pairwise.add_argument('--n', type=int, required=True)
    embeddings = add_command(commands, 'embeddings', estimate_embeddings)
    embeddings.add_argument('--n', type=int, required=True)
    embeddings.add_argument('--dim', type=int, required=True)
    sparse = add_command(commands, 'sparse', estimate_sparse)
    sparse.add_argument('--rows', type=int, required=True)
    sparse.add_argument('--cols', type=int, required=True)
    sparse.add_argument('--nnz', type=int, required=True)
    sparse.add_argument('--index-dtype', default='int32')
    for command in (dense, pairwise, embeddings, sparse):
        command.add_argument('--dtype', default='float64')
    add_fit_and_join_commands(commands)
    return parser


def add_fit_and_join_commands(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    join = add_command(commands, 'join', estimate_join)
    join.add_argument('--left-matches', type=int, required=True)
    join.add_argument('--right-matches', type=int, required=True)
    fits = add_command(commands, 'fits', estimate_fits)
    fits.add_argument('--configs', type=int, required=True)
    fits.add_argument('--folds', type=int, required=True)
    fits.add_argument('--repeats', type=int, default=1)
    fits.add_argument('--seconds-per-fit', type=float)


def check_dtypes(arguments: argparse.Namespace) -> None:
    names = (vars(arguments).get(key) for key in ('dtype', 'index_dtype'))
    unknown = next((name for name in names if name and not is_dtype_name(name)), None)
    if unknown is not None:
        raise UnknownDtypeError(unknown)


def check_quantities(arguments: argparse.Namespace) -> None:
    numbers = {
        name: value
        for name, value in vars(arguments).items()
        if isinstance(value, int | float) and not isinstance(value, bool)
    }
    negative = sorted(name for name, value in numbers.items() if value < 0)
    if negative:
        raise NegativeQuantityError(negative)


def estimate(estimator: Estimator, arguments: argparse.Namespace) -> Sized:
    try:
        return estimator(arguments)
    except OverflowError as overflow:
        raise QuantityTooLargeError from overflow


def build_report(argv: list[str]) -> Report[SizeEstimate]:
    arguments = build_parser().parse_args(argv)
    check_quantities(arguments)
    check_dtypes(arguments)
    sized = estimate(arguments.estimator, arguments)
    return Report(
        command=f'{COMMAND} {arguments.subcommand}',
        arguments=describe_arguments(arguments),
        result=sized.estimate,
        caveats=sized.caveats,
    )


def main(argv: list[str]) -> int:
    return run_command(logger, build_report, argv)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
