"""The `mightymodels dispatch-hook` command, which the plugin's PreToolUse hook on `Agent` runs.

Claude Code lets a subagent dispatch any subagent type and ignores an allow-list in a subagent's
definition, so the plugin enforces the "delegate only to" lines of its agent files here. The hook
input is JSON on standard input; a call made inside a subagent carries `agent_type`, and the main
conversation's does not. The hook polices only this plugin's workers, whose `agent_type` begins
`mightymodels:`: a worker's dispatch outside its row is denied, a name under that prefix that is
no worker has no row, and unreadable input that names such an `agent_type` is denied. Every other
caller (a built-in subagent, another plugin's agent, a main thread started with `--agent`) and
input without `agent_type` get no decision, as if the plugin were not installed.
"""

import json
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import TextIO

from mightymodels_plugin.core.routing import Worker

PLUGIN_PREFIX = 'mightymodels:'
AGENT_TYPE_KEY = 'agent_type'
PLUGIN_CALLER = re.compile(rf'"{AGENT_TYPE_KEY}"\s*:\s*"{re.escape(PLUGIN_PREFIX)}')
UNREADABLE = 'a dispatch was refused: the hook input is not the expected JSON'
HOOK_EVENT = 'PreToolUse'
DENY = 'deny'
NO_TARGETS = frozenset[Worker]()

DISPATCH_RULES: Mapping[Worker, frozenset[Worker]] = MappingProxyType(
    {
        Worker.CODE_SCOUT: NO_TARGETS,
        Worker.WEB_SCOUT: NO_TARGETS,
        Worker.QUALITYLENS: NO_TARGETS,
        Worker.ENGINEER: frozenset({Worker.CODE_SCOUT}),
        Worker.ARCHITECT: frozenset({Worker.CODE_SCOUT}),
        Worker.GITTY_UP: NO_TARGETS,
        Worker.WINGMAN: NO_TARGETS,
        Worker.MERGE_VADER_REVIEWER: frozenset(
            {Worker.CODE_SCOUT, Worker.WEB_SCOUT, Worker.QUALITYLENS}
        ),
        Worker.UNCLE_BOB_REVIEWER: frozenset({Worker.CODE_SCOUT, Worker.QUALITYLENS}),
    }
)


def worker_named(name: str) -> Worker | None:
    return next((worker for worker in Worker if worker == name.removeprefix(PLUGIN_PREFIX)), None)


def decoded_object(text: str) -> dict[str, object] | None:
    try:
        decoded: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    return {str(key): value for key, value in decoded.items()}


def target_of(fields: Mapping[str, object]) -> object:
    tool_input = fields.get('tool_input')
    return tool_input.get('subagent_type') if isinstance(tool_input, dict) else None


def allowed_names(allowed: frozenset[Worker]) -> str:
    return ', '.join(sorted(allowed)) or 'nothing'


def allowed_for(caller: str) -> frozenset[Worker]:
    worker = worker_named(caller)
    return NO_TARGETS if worker is None else DISPATCH_RULES[worker]


def denial_for_worker(caller: str, target: object) -> str | None:
    if not isinstance(target, str):
        return f'{caller} was refused a dispatch: the hook input names no target type'
    allowed = allowed_for(caller)
    worker = worker_named(target)
    if worker is not None and worker in allowed:
        return None
    return f'{caller} may not dispatch {target}; it may dispatch: {allowed_names(allowed)}'


def dispatch_denial(text: str) -> str | None:
    fields = decoded_object(text)
    if fields is None:
        return UNREADABLE if PLUGIN_CALLER.search(text) else None
    caller = fields.get(AGENT_TYPE_KEY)
    if not isinstance(caller, str) or not caller.startswith(PLUGIN_PREFIX):
        return None
    return denial_for_worker(caller, target_of(fields))


def check_dispatch(stdin: TextIO, stdout: TextIO) -> int:
    reason = dispatch_denial(stdin.read())
    if reason is None:
        return 0
    decision = {
        'hookSpecificOutput': {
            'hookEventName': HOOK_EVENT,
            'permissionDecision': DENY,
            'permissionDecisionReason': reason,
        }
    }
    stdout.write(json.dumps(decision) + '\n')
    return 0
