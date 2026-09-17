import sys
from pathlib import Path
from typing import Any

from mightymcp.artifacts import bullets
from mightymcp.hooks.guard import payload_root, payload_slug
from mightymcp.hookstate import read_state
from mightymcp.paths import MIGHTYMODELS_DIR, git_output
from mightymcp.status import render_status, sprint_status

SNAPSHOT = 'snapshot.md'
BATON = Path('handoffs', 'BATON.md')
# contracts.md caps every artifact; a snapshot longer than this is a handoff in disguise
CAP = 40
UNKNOWN = 'unknown'


def pre_compact(payload: dict[str, Any]) -> dict[str, Any]:
    """Regenerate the ticket's snapshot so the next session can read it back."""
    root = payload_root(payload)
    slug = payload_slug(root)
    if slug is None:
        return {}
    directory = root.joinpath(MIGHTYMODELS_DIR, slug)
    text = '\n'.join(_lines(root, slug, directory, payload)) + '\n'
    try:
        directory.joinpath(SNAPSHOT).write_text(text, encoding='utf-8')
    except OSError as err:
        print(f'mightymcp hook stood down: {err}', file=sys.stderr)
    return {}


def _lines(root: Path, slug: str, directory: Path, payload: dict[str, Any]) -> list[str]:
    head = [
        f'# snapshot before the {payload.get("trigger", UNKNOWN)} compaction',
        f'branch: {_branch(root)}',
        'sprint status:',
    ]
    tail = [*_agent_lines(root, payload['session_id']), *_baton_lines(directory)]
    rows = _rows(slug, CAP - len(head) - len(tail))
    return [*head, *rows, *tail][:CAP]


def _branch(root: Path) -> str:
    branch = git_output(['rev-parse', '--abbrev-ref', 'HEAD'], cwd=root)
    sha = git_output(['rev-parse', '--short', 'HEAD'], cwd=root)
    return f'{branch or UNKNOWN} @ {sha or UNKNOWN}'


def _rows(slug: str, budget: int) -> list[str]:
    """The status rows, truncated to what the cap leaves for them."""
    rows = [f'  {line}' for line in render_status(sprint_status(slug)).splitlines()]
    if len(rows) <= budget:
        return rows
    kept = max(budget - 1, 0)
    return [*rows[:kept], f'  ... {len(rows) - kept} more rows']


def _agent_lines(root: Path, session_id: str) -> list[str]:
    state = read_state(root, session_id)
    return [
        'pending dispatches:',
        *bullets([f'{entry.role} {entry.task_id}' for entry in state.pending]),
        'bound agents:',
        *bullets([
            f'{agent_id}: {agent.role} {agent.task_id or "unbound"}'
            for agent_id, agent in state.agents.items()
        ]),
    ]


def _baton_lines(directory: Path) -> list[str]:
    baton = directory.joinpath(BATON)
    return [f'baton waiting: {baton}'] if baton.is_file() else []
