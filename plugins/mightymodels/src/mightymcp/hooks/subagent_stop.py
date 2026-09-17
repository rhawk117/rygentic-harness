import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mightymcp.hooks.guard import agent_role, payload_root, payload_slug
from mightymcp.hookstate import agent_state
from mightymcp.paths import MIGHTYMODELS_DIR
from mightymcp.worker_reports import WorkerReport, parse_report

LOG = 'dispatches.jsonl'


def subagent_stop(payload: dict[str, Any]) -> dict[str, Any]:
    """Gate a worker's report on its way out, and log the dispatch either way."""
    role = agent_role(payload.get('agent_type', ''))
    if payload.get('stop_hook_active') or role is None:
        return {}

    root = payload_root(payload)
    report = parse_report(role, payload.get('last_assistant_message', ''))
    _log(root, payload, role, report)
    if report.refusals:
        return {'decision': 'block', 'reason': '; '.join(report.refusals)}
    return {}


def _log(root: Path, payload: dict[str, Any], role: str, report: WorkerReport) -> None:
    """Append this stop to the ticket's dispatch log; with no ticket, nowhere to log."""
    slug = payload_slug(root)
    if slug is None:
        return
    session_id = payload['session_id']
    agent_id = payload.get('agent_id', '')
    bound = agent_state(root, session_id, agent_id)
    record = {
        'ts': datetime.now(UTC).isoformat(),
        'session_id': session_id,
        'agent_id': agent_id,
        'agent_type': role,
        'task_id': bound.task_id if bound else '',
        'verdict': report.verdict,
        'ok': not report.refusals and not report.stop,
    }
    log = root.joinpath(MIGHTYMODELS_DIR, slug, LOG)
    try:
        with log.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record) + '\n')
    except OSError as err:
        print(f'mightymcp hook stood down: {err}', file=sys.stderr)
