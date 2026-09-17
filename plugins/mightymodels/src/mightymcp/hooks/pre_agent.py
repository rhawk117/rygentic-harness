import re
from pathlib import Path
from typing import Any

from mightymcp.hooks.guard import (
    ENGINEER,
    SCOUT,
    allow,
    deny,
    dispatch_role,
    payload_root,
    payload_slug,
)
from mightymcp.hookstate import record_pending
from mightymcp.routing import HAIKU, OPUS, SONNET
from mightymcp.ticket import resolve_model

ALIASES = {'haiku': HAIKU, 'sonnet': SONNET, 'opus': OPUS}
BRIEF_TASK = re.compile(r'briefs/(task-\d{2,})\.md')
# what each role's promptlint template puts in the prompt: a dispatch missing its
# shape is bounced by the worker anyway, and a bounce costs a whole round trip
REQUIRED_PARTS = {
    SCOUT: ('<objective>', '<discovery>'),
    ENGINEER: ('## ASKED',),
    'budgetron': ('Fix:', 'Verify:'),
    'wingman': ('<decision>', '<options>', '<facts>', '<lean>'),
}
PROPOSITION_ROLES = ('grumpy', 'sunny')
PROPOSITION_PARTS = ('<proposition', 'Proposition:')
PROPOSITION_MISSING = 'a <proposition> tag or a Proposition: line'
BRIEF_ROLES = (ENGINEER, SCOUT)


def pre_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """Guard a mightymodels dispatch: the prompt's shape first, then its model."""
    tool_input = payload['tool_input']
    role = dispatch_role(tool_input.get('subagent_type', ''))
    if role is None:
        return {}

    prompt = tool_input.get('prompt', '')
    missing = _missing_parts(role, prompt)
    if missing:
        return deny(
            f'a {role} dispatch is missing {", ".join(missing)}; '
            'see promptlint before dispatching'
        )
    root = payload_root(payload)
    _record_dispatch(root, payload['session_id'], role, prompt)
    return _model_decision(root, role, tool_input)


def _missing_parts(role: str, prompt: str) -> list[str]:
    if role in PROPOSITION_ROLES:
        if any(part in prompt for part in PROPOSITION_PARTS):
            return []
        return [PROPOSITION_MISSING]
    return [part for part in REQUIRED_PARTS.get(role, ()) if part not in prompt]


def _record_dispatch(root: Path, session_id: str, role: str, prompt: str) -> None:
    brief = BRIEF_TASK.search(prompt)
    if role in BRIEF_ROLES and brief:
        record_pending(root, session_id, role, brief.group(1))


def _model_decision(root: Path, role: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    choice = resolve_model(role, payload_slug(root))
    asked = tool_input.get('model', '')
    if choice.model is None or choice.model == ALIASES.get(asked, asked):
        return {}
    return allow(
        tool_input | {'model': choice.model},
        f'{role} runs on {choice.model} ({choice.source}: {choice.rule})',
    )
