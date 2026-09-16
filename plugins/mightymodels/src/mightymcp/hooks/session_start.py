from pathlib import Path
from typing import Any

from mightymcp.fleet import load_fleet, render_fleet
from mightymcp.paths import MIGHTYMODELS_DIR, git_output, repo_root
from mightymcp.routing import MODEL_ROLES, route_ramp
from mightymcp.status import sprint_status
from mightymcp.ticket import IGNORE_LINE, ensure_ignored, resolve_model, ticket_read

EVENT = 'SessionStart'
COMPACT = 'compact'
ARCHIVES = 'archives'
EXCLUDE = Path('.git', 'info', 'exclude')


def session_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Inject the fleet roster, the active ticket's state, and the ignore ritual."""
    root = repo_root(explicit=Path(payload['cwd']))
    slugs = _ticket_slugs(root)
    lines = [
        'mightymodels fleet:',
        render_fleet(load_fleet()),
        '',
        *_ticket_lines(root, _active_slug(root, slugs), slugs, payload.get('source', '')),
        '',
        _ignore_line(root),
    ]
    return {
        'hookSpecificOutput': {
            'hookEventName': EVENT,
            'additionalContext': '\n'.join(lines),
        }
    }


def _ticket_slugs(root: Path) -> list[str]:
    tickets = root.joinpath(MIGHTYMODELS_DIR).glob('*/ticket.yml')
    return sorted(path.parent.name for path in tickets if path.parent.name != ARCHIVES)


def _active_slug(root: Path, slugs: list[str]) -> str | None:
    if len(slugs) == 1:
        return slugs[0]
    branch = git_output(['rev-parse', '--abbrev-ref', 'HEAD'], cwd=root)
    if branch is None:
        return None
    on_branch = [slug for slug in slugs if _ticket_branch(slug) == branch]
    return on_branch[0] if len(on_branch) == 1 else None


def _ticket_branch(slug: str) -> str | None:
    read = ticket_read(slug)
    return read.ticket.handoff_context.branch_name if read.ticket else None


def _ticket_lines(
    root: Path, slug: str | None, slugs: list[str], source: str
) -> list[str]:
    if slug is None:
        return [
            'active ticket: none',
            f'tickets on disk: {", ".join(slugs) or "none"}',
        ]
    read = ticket_read(slug)
    if read.ticket is None:
        return [
            f'active ticket: {slug}, unreadable',
            *(f'  refused: {refusal}' for refusal in read.refusals),
        ]
    handoff = read.ticket.handoff_context
    ramp = route_ramp(handoff.scope, plan_first=handoff.plan_first)
    return [
        f'active ticket: {slug} - {read.ticket.summary}',
        f'ramp: {ramp.ramp or "unresolved"} ({ramp.rule or "; ".join(ramp.refusals)})',
        'models:',
        *_model_lines(slug),
        'sprint status:',
        *_status_lines(slug),
        *_baton_lines(root, slug),
        *_snapshot_lines(root, slug, source),
    ]


def _model_lines(slug: str) -> list[str]:
    choices = (resolve_model(role, slug) for role in MODEL_ROLES)
    return [
        f'  {choice.role}: {choice.model or "unresolved"} ({choice.source})'
        for choice in choices
    ]


def _status_lines(slug: str) -> list[str]:
    status = sprint_status(slug)
    if status.refusals:
        return [f'  unavailable: {"; ".join(status.refusals)}']
    if not status.tasks:
        return ['  no briefs yet']
    return [
        f'  {task.task_id}: asked={task.asked} done={task.done} '
        f'verified={task.verified} commit={task.commit or "none"} '
        f'attempts={task.attempts}'
        for task in status.tasks
    ]


def _baton_lines(root: Path, slug: str) -> list[str]:
    baton = root.joinpath(MIGHTYMODELS_DIR, slug, 'handoffs', 'BATON.md')
    return [f'baton waiting: read {baton}'] if baton.is_file() else []


def _snapshot_lines(root: Path, slug: str, source: str) -> list[str]:
    snapshot = root.joinpath(MIGHTYMODELS_DIR, slug, 'snapshot.md')
    if source != COMPACT or not snapshot.is_file():
        return []
    return [
        f'snapshot from before the compaction ({snapshot}):',
        snapshot.read_text(encoding='utf-8').rstrip('\n'),
    ]


def _ignore_line(root: Path) -> str:
    ensure_ignored(root)
    exclude = root.joinpath(EXCLUDE)
    if exclude.is_file() and IGNORE_LINE in exclude.read_text(encoding='utf-8'):
        return f'{MIGHTYMODELS_DIR}/ is excluded in {EXCLUDE}'
    return f'{MIGHTYMODELS_DIR}/ is already ignored by git'
