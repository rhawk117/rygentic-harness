from pathlib import Path, PurePosixPath
from typing import Any

from mightymcp.artifacts import cap_refusals
from mightymcp.brief import BRIEF_CAP, DONE_HEADING, asked_half, brief_read
from mightymcp.handoff import BATON_CAP, DECISIONS_CAP
from mightymcp.hooks.guard import ENGINEER, deny, payload_root, payload_slug
from mightymcp.hookstate import agent_state
from mightymcp.paths import MIGHTYMODELS_DIR
from mightymcp.prune import ARCHIVE_CAP
from mightymcp.report import REPORT_CAP
from mightymcp.scripts import JOURNAL

WRITE = 'Write'
BRIEFS = f'{MIGHTYMODELS_DIR}/*/briefs/*.md'
CRASHOUTS = f'{MIGHTYMODELS_DIR}/{JOURNAL}'
# archives first: a cap is read from the first pattern the path matches
CAPS = (
    (f'{MIGHTYMODELS_DIR}/archives/*.md', ARCHIVE_CAP),
    (BRIEFS, BRIEF_CAP),
    (f'{MIGHTYMODELS_DIR}/*/REPORT.md', REPORT_CAP),
    (f'{MIGHTYMODELS_DIR}/*/handoffs/BATON.md', BATON_CAP),
    (f'{MIGHTYMODELS_DIR}/*/decisions.md', DECISIONS_CAP),
)


def pre_write_edit(payload: dict[str, Any]) -> dict[str, Any]:
    """Guard the caps under .mightymodels/ and an engineer's files-in-scope."""
    tool_input = payload['tool_input']
    root = payload_root(payload)
    target = Path(tool_input['file_path'])
    relative = _relative(root, target)
    current = target.read_text(encoding='utf-8') if target.is_file() else ''
    content = _post_edit_content(payload['tool_name'], tool_input, current)

    reason = (
        _crashout_reason(relative)
        or _scope_reason(root, payload, relative, current, content)
        or _cap_reason(relative, content)
        or _done_reason(payload, relative, current, content)
    )
    return deny(reason) if reason else {}


def _relative(root: Path, target: Path) -> PurePosixPath | None:
    try:
        return PurePosixPath(target.resolve().relative_to(root))
    except ValueError:
        return None


def _post_edit_content(tool_name: str, tool_input: dict[str, Any], current: str) -> str:
    if tool_name == WRITE:
        return tool_input.get('content', '')
    count = -1 if tool_input.get('replace_all') else 1
    return current.replace(
        tool_input.get('old_string', ''), tool_input.get('new_string', ''), count
    )


def _crashout_reason(relative: PurePosixPath | None) -> str | None:
    if relative is None or not relative.full_match(CRASHOUTS):
        return None
    return f'{CRASHOUTS} is the crashout journal; the crashout skill writes it'


def _cap_reason(relative: PurePosixPath | None, content: str) -> str | None:
    if relative is None:
        return None
    for pattern, cap in CAPS:
        if relative.full_match(pattern):
            refusals = cap_refusals(str(relative), content, cap)
            return refusals[0] if refusals else None
    return None


def _done_reason(
    payload: dict[str, Any],
    relative: PurePosixPath | None,
    current: str,
    content: str,
) -> str | None:
    if relative is None or not relative.full_match(BRIEFS):
        return None
    adds_done = DONE_HEADING in content and DONE_HEADING not in current
    if payload.get('agent_type') or not adds_done:
        return None
    return f'{DONE_HEADING} is the worker half of a brief; the primary never writes it'


def _scope_reason(
    root: Path,
    payload: dict[str, Any],
    relative: PurePosixPath | None,
    current: str,
    content: str,
) -> str | None:
    agent_id = payload.get('agent_id', '')
    state = agent_state(root, payload['session_id'], agent_id) if agent_id else None
    slug = payload_slug(root)
    if state is None or state.role != ENGINEER or not state.task_id or slug is None:
        return None
    read = brief_read(slug, state.task_id)
    if read.asked is None or read.path is None:
        return None

    if relative == _relative(root, Path(read.path)):
        return _asked_reason(state.task_id, current, content)
    scope = read.asked.files_in_scope
    if relative is not None and any(relative.full_match(p) for p in scope):
        return None
    return (
        f'{relative or payload["tool_input"]["file_path"]} is outside '
        f'{state.task_id} files-in-scope: {", ".join(scope)}'
    )


def _asked_reason(task_id: str, current: str, content: str) -> str | None:
    if asked_half(current) == asked_half(content):
        return None
    return f'the ASKED half of {task_id} is the dispatch; append the DONE half instead'
