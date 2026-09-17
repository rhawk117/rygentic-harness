import json
import os
import sys
from collections.abc import Callable
from typing import Any

# Any non-empty value stands the plugin's hooks down without uninstalling them.
OFF_VAR = 'MIGHTYMCP_OFF'
HookHandler = Callable[[dict[str, Any]], dict[str, Any]]


def run_hook(handler: HookHandler) -> None:
    """Run one hook handler under the never-block contract: exit 0, whatever happens.

    Stdin is not read at all when MIGHTYMCP_OFF is set. A malformed payload or a
    handler that raises leaves stdout empty and puts the diagnostic on stderr, so a
    broken hook costs the session its context injection and nothing else.
    """
    if os.environ.get(OFF_VAR):
        return
    try:
        output = handler(read_payload(sys.stdin.read()))
    except Exception as err:  # noqa: BLE001 -- a hook stands down, never blocks
        print(f'mightymcp hook stood down: {err}', file=sys.stderr)
        return
    print(json.dumps(output))


def read_payload(raw: str) -> dict[str, Any]:
    """Parse the one JSON object Claude Code writes to a hook's stdin."""
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError(f'hook payload is {type(payload).__name__}, expected an object')
    return payload
