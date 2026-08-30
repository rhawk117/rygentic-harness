"""Hook entry point. Both hosts invoke this; it must be fast, quiet and fail-open.

    python -m skilleng.hookshim            # normalize stdin JSON into $SKILLENG_EVENT_LOG
    python -m skilleng.hookshim --probe    # also record the raw payload for adapter discovery
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .events import ENV_ARM, ENV_LOG, ENV_RUN, append, normalize


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    probe = "--probe" in argv
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {"_payload": payload}
        log = os.environ.get(ENV_LOG)
        if log:
            append(Path(log), normalize(payload, os.environ.get(ENV_RUN), os.environ.get(ENV_ARM)))
            if probe:
                Path(log).with_suffix(".probe.ndjson").open("a", encoding="utf-8").write(
                    json.dumps(payload, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001 — instrumentation never breaks the observed run
        pass
    # An empty object is the universally safe "no decision" reply on both hosts.
    sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
