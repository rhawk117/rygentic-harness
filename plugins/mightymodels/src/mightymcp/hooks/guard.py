from pathlib import Path
from typing import Any

from mightymcp.paths import TicketPathError, active_ticket, repo_root

PRE_TOOL_USE = 'PreToolUse'
PLUGIN_PREFIX = 'mightymodels:'
ENGINEER = 'engineer'
SCOUT = 'scout'
# the agent files this plugin ships; a dispatch names one of these after the prefix
AGENT_ROLES = (
    SCOUT,
    ENGINEER,
    'budgetron',
    'gitty-up',
    'grumpy',
    'sunny',
    'wingman',
)


def allow(tool_input: dict[str, Any], reason: str) -> dict[str, Any]:
    """Allow a tool call with a replacement tool_input; the whole input is replaced."""
    return {
        'hookSpecificOutput': {
            'hookEventName': PRE_TOOL_USE,
            'permissionDecision': 'allow',
            'permissionDecisionReason': reason,
            'updatedInput': tool_input,
        }
    }


def deny(reason: str) -> dict[str, Any]:
    """Deny a tool call, naming the rule that refused it."""
    return {
        'hookSpecificOutput': {
            'hookEventName': PRE_TOOL_USE,
            'permissionDecision': 'deny',
            'permissionDecisionReason': reason,
        }
    }


def dispatch_role(subagent_type: str) -> str | None:
    """The fleet role a dispatch names, or None when the agent is not one of ours."""
    if not subagent_type.startswith(PLUGIN_PREFIX):
        return None
    role = subagent_type.removeprefix(PLUGIN_PREFIX)
    return role if role in AGENT_ROLES else None


def agent_role(agent_type: str) -> str | None:
    """The fleet role a running subagent carries, with or without the plugin prefix."""
    role = agent_type.removeprefix(PLUGIN_PREFIX)
    return role if role in AGENT_ROLES else None


def payload_root(payload: dict[str, Any]) -> Path:
    """The repository root the hook call came from."""
    return repo_root(explicit=Path(payload['cwd']))


def payload_slug(root: Path) -> str | None:
    """The live ticket's slug, or None when no ticket answers for this repository."""
    try:
        return active_ticket(root)
    except TicketPathError:
        return None
