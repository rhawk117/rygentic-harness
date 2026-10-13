"""How a command refuses: the failure on standard error, and the exit code that says refused.

A hook command never refuses: a hook that exits 2 can block the stop or the compaction it
watches, so `skipped` gives the reason on standard error and exits 0.
"""

import sys

from mightymodels.core.errors import StateError

EXIT_PASSED = 0
EXIT_REJECTED = 2


def rejected(error: StateError) -> int:
    sys.stderr.write(f'error: {error}\n')
    return EXIT_REJECTED


def skipped(reason: Exception) -> int:
    sys.stderr.write(f'mightymodels hook did nothing: {reason}\n')
    return EXIT_PASSED
