from typing import Any

from mightymcp.artifacts import bullets
from mightymcp.brief import brief_read
from mightymcp.hooks.guard import ENGINEER, agent_role, payload_root, payload_slug
from mightymcp.hookstate import bind_agent

EVENT = 'SubagentStart'
DONE_SENTENCE = (
    'Append your DONE half with the brief_append_done tool once the commit lands; '
    'do not write it into the brief by hand.'
)


def subagent_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Bind a starting subagent to its brief and inject what the dispatch left out."""
    role = agent_role(payload.get('agent_type', ''))
    if role is None:
        return {}

    root = payload_root(payload)
    bound = bind_agent(root, payload['session_id'], payload['agent_id'], role)
    slug = payload_slug(root)
    if not bound.task_id or slug is None:
        return {}
    lines = _context_lines(slug, role, bound.task_id)
    if not lines:
        return {}
    return {
        'hookSpecificOutput': {
            'hookEventName': EVENT,
            'additionalContext': '\n'.join(lines),
        }
    }


def _context_lines(slug: str, role: str, task_id: str) -> list[str]:
    read = brief_read(slug, task_id)
    if read.asked is None or read.path is None:
        return []
    if role == ENGINEER:
        return [
            f'brief: {read.path}',
            'files-in-scope:',
            *bullets(read.asked.files_in_scope),
            DONE_SENTENCE,
        ]
    return [
        f'brief under verification: {read.path}',
        'acceptance criteria:',
        *bullets(read.asked.acceptance),
    ]
