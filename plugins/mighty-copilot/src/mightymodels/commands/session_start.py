"""The `mightymodels session-start` command, which the plugin's SessionStart hook runs.

A Copilot SessionStart hook has no env file to export into, and the plugin's `bin/` is not known
to be on the shell's PATH. The command prints the absolute path of the launcher and the plugin
root, both worked out from where this package sits (`<root>/src/mightymodels/commands`, run by
`<root>/bin/mightymodels`), as one JSON object on standard output. The text is `additionalContext`
at the top level and under `hookSpecificOutput`, so a skill can run the CLI at that path. The
command writes no file and reads no variable.
"""

from pathlib import Path
from typing import BinaryIO

from mightymodels.core.codec import encode_compact

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
HOOK_EVENT = 'SessionStart'
LAUNCHER_NAME = 'mightymodels'


def announcement() -> str:
    launcher = PLUGIN_ROOT.joinpath('bin', LAUNCHER_NAME)
    return (
        f'The mightymodels CLI is at {launcher}; run it by that absolute path, since the '
        f"plugin's bin directory may not be on the PATH. The plugin root is {PLUGIN_ROOT}."
    )


def announce(output: BinaryIO) -> int:
    context = announcement()
    document = {
        'additionalContext': context,
        'hookSpecificOutput': {'hookEventName': HOOK_EVENT, 'additionalContext': context},
    }
    output.write(encode_compact(document) + b'\n')
    return 0
