# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""SUMMARY_OF_WHAT_THIS_AUTOMATION_DOES.

Run with: uv run scripts/SCRIPT_NAME.py --help
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

logger = logging.getLogger(__name__)


class ExitCode(IntEnum):
    OK = 0
    PARTIAL_FAILURE = 1
    USAGE = 2


@dataclass(slots=True, kw_only=True, frozen=True)
class Options:
    target: Path
    dry_run: bool = False
    workers: int = 1


@dataclass(slots=True, kw_only=True, frozen=True)
class Outcome:
    succeeded: int
    failed: int

    @property
    def exit_code(self) -> ExitCode:
        return ExitCode.PARTIAL_FAILURE if self.failed else ExitCode.OK


def run_automation(options: Options) -> Outcome:
    logger.info(
        'starting on %s (dry_run=%s, workers=%d)', options.target, options.dry_run, options.workers
    )
    return Outcome(succeeded=0, failed=0)


def parse_positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        message = f'expected a positive integer, got {text}'
        raise argparse.ArgumentTypeError(message)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument(
        '--dry-run', action='store_true', help='report actions without changing anything'
    )
    parser.add_argument(
        '--workers', type=parse_positive_int, default=1, help='concurrency (default: 1)'
    )
    parser.add_argument('-v', '--verbose', action='store_true')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if arguments.verbose else logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        stream=sys.stderr,
    )
    options = Options(
        target=arguments.target,
        dry_run=arguments.dry_run,
        workers=arguments.workers,
    )
    outcome = run_automation(options)
    logger.info('done: %d succeeded, %d failed', outcome.succeeded, outcome.failed)
    return outcome.exit_code


if __name__ == '__main__':
    raise SystemExit(main())
