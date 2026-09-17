import re
from typing import Any

from mightymcp.hooks.guard import payload_root, payload_slug
from mightymcp.ticket import ISSUE_NUMBER, PR_NUMBER, ticket_set_companion

# gh prints the URL of what it just opened; the number on the end is the tracker key
URL = r'https://github\.com/[^/\s]+/[^/\s]+/{kind}/(\d+)'
CAPTURES = (
    ('gh pr create', PR_NUMBER, re.compile(URL.format(kind='pull'))),
    ('gh issue create', ISSUE_NUMBER, re.compile(URL.format(kind='issues'))),
)


def post_bash(payload: dict[str, Any]) -> dict[str, Any]:
    """Capture the PR or issue gh just opened into the ticket's companion-docs block."""
    command = payload.get('tool_input', {}).get('command', '')
    capture = next(
        ((key, pattern) for phrase, key, pattern in CAPTURES if phrase in command), None
    )
    if capture is None:
        return {}
    key, pattern = capture
    found = pattern.search(payload.get('tool_response', {}).get('stdout', ''))
    slug = payload_slug(payload_root(payload))
    if found is not None and slug is not None:
        ticket_set_companion(slug, key, int(found.group(1)))
    return {}
