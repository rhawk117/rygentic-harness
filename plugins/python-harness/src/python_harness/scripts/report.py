"""The YAML report envelope, exit codes and error mapping every data command shares."""

import argparse
import logging
import sys
from collections.abc import Callable

import msgspec

SCHEMA_VERSION = 2
CONTRACT_VIOLATION = 2
UNREADABLE_INPUT = 3
LAUNCHER = 'python-harness-data'

type ArgumentValue = str | int | float | bool | tuple[str, ...] | None


class ContractViolationError(Exception):
    pass


class UnreadableInputError(Exception):
    pass


class Report[ResultT](msgspec.Struct, frozen=True, kw_only=True):
    schema_version: int = SCHEMA_VERSION
    command: str
    arguments: dict[str, ArgumentValue]
    result: ResultT
    caveats: tuple[str, ...]


def normalize_argument(value: object) -> ArgumentValue:
    match value:
        case str() | int() | float() | bool() | None:
            return value
        case list() | tuple():
            return tuple(map(str, value))
        case _:
            return str(value)


def describe_arguments(arguments: argparse.Namespace) -> dict[str, ArgumentValue]:
    return {
        name: normalize_argument(value)
        for name, value in vars(arguments).items()
        if not callable(value)
    }


def log_failure(logger: logging.Logger, failure: Exception, exit_code: int) -> int:
    logger.error('%s', failure)
    return exit_code


def run_command[ResultT](
    logger: logging.Logger, build: Callable[[list[str]], Report[ResultT]], argv: list[str]
) -> int:
    logging.basicConfig(stream=sys.stderr, format='%(levelname)s %(message)s')
    try:
        report = build(argv)
    except ContractViolationError as violation:
        return log_failure(logger, violation, CONTRACT_VIOLATION)
    except UnreadableInputError as unreadable:
        return log_failure(logger, unreadable, UNREADABLE_INPUT)
    sys.stdout.write(msgspec.yaml.encode(report).decode())
    return 0
