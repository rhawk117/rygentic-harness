import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.brief import AskedStanza, brief_open
from mightymcp.hookstate import read_state, record_pending
from mightymcp.ticket import HandoffContext, ticket_create

HOOK = Path(__file__).resolve().parents[1].joinpath('hooks', 'subagent_start.py')
CONTEXT = ['the guard runs under uv', 'stdin is one object', 'stdout is one object']
SCOPE = ['src/app/**', 'tests/test_app.py']
ACCEPTANCE = ['AC-1: uv run pytest -q passes', 'AC-2: the backoff is capped at 30s']

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]
Start = Callable[..., str]


def write_brief(task_id: str) -> None:
    written = brief_open(
        'demo',
        task_id,
        AskedStanza(
            objective='Cap the retry backoff',
            acceptance=ACCEPTANCE,
            verification='uv run pytest -q',
            files_in_scope=SCOPE,
            engineer_tier='claude-sonnet-5',
        ),
        'feat(app): cap the retry backoff',
    )
    assert written.refusals == [], written.refusals


@pytest.fixture
def ticket(repo: Path) -> Path:
    written = ticket_create(
        'demo',
        'Ship demo',
        CONTEXT,
        HandoffContext(scope='med', plan_first=True, branch_name='main'),
    )
    assert written.refusals == [], written.refusals
    write_brief('task-03')
    return repo.joinpath('.mightymodels', 'demo')


@pytest.fixture
def start(repo: Path, payload: Load, run_hook_script: RunScript) -> Start:
    """Start one subagent through the hook and return the context it injected."""

    def run(agent_type: str = 'engineer', agent_id: str = 'agent_01') -> str:
        hook = payload('SubagentStart-engineer') | {
            'cwd': str(repo),
            'agent_type': agent_type,
            'agent_id': agent_id,
        }
        proc = run_hook_script(HOOK, json.dumps(hook), repo)
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == '', proc.stderr
        output = json.loads(proc.stdout).get('hookSpecificOutput', {})
        return output.get('additionalContext', '')

    return run


@pytest.fixture
def session(payload: Load) -> str:
    return payload('SubagentStart-engineer')['session_id']


def test_an_agent_from_another_plugin_gets_nothing(ticket: Path, start: Start) -> None:
    assert start(agent_type='researcher') == ''


def test_an_engineer_with_nothing_pending_gets_nothing(
    ticket: Path, start: Start
) -> None:
    assert start() == ''


def test_an_unbound_agent_is_still_recorded(
    ticket: Path, repo: Path, session: str, start: Start
) -> None:
    start()
    state = read_state(repo, session)

    assert state.agents['agent_01'].role == 'engineer'
    assert state.agents['agent_01'].task_id == ''


def test_a_bound_engineer_is_given_its_brief_and_its_scope(
    ticket: Path, repo: Path, session: str, start: Start
) -> None:
    record_pending(repo, session, 'engineer', 'task-03')
    context = start()

    assert str(ticket.joinpath('briefs', 'task-03.md')) in context
    for pattern in SCOPE:
        assert f'- {pattern}' in context


def test_a_bound_engineer_is_told_how_its_done_half_is_appended(
    ticket: Path, repo: Path, session: str, start: Start
) -> None:
    record_pending(repo, session, 'engineer', 'task-03')

    assert 'brief_append_done' in start()


@pytest.mark.parametrize('agent_type', ['scout', 'mightymodels:scout'])
def test_a_bound_scout_is_given_the_acceptance_criteria(
    agent_type: str, ticket: Path, repo: Path, session: str, start: Start
) -> None:
    record_pending(repo, session, 'scout', 'task-03')
    context = start(agent_type=agent_type)

    for criterion in ACCEPTANCE:
        assert f'- {criterion}' in context


def test_a_scout_is_not_bound_to_an_engineer_dispatch(
    ticket: Path, repo: Path, session: str, start: Start
) -> None:
    record_pending(repo, session, 'engineer', 'task-03')

    assert start(agent_type='scout') == ''


def test_the_oldest_pending_dispatch_of_the_role_is_bound_first(
    ticket: Path, repo: Path, session: str, start: Start
) -> None:
    write_brief('task-04')
    record_pending(repo, session, 'engineer', 'task-03')
    record_pending(repo, session, 'engineer', 'task-04')

    assert 'task-03.md' in start(agent_id='agent_01')
    assert 'task-04.md' in start(agent_id='agent_02')


def test_a_bound_dispatch_is_consumed(
    ticket: Path, repo: Path, session: str, start: Start
) -> None:
    record_pending(repo, session, 'engineer', 'task-03')
    start(agent_id='agent_01')

    assert start(agent_id='agent_02') == ''
    assert read_state(repo, session).pending == []


def test_a_dispatch_whose_brief_is_missing_injects_nothing(
    ticket: Path, repo: Path, session: str, start: Start
) -> None:
    record_pending(repo, session, 'engineer', 'task-09')

    assert start() == ''


def test_the_off_switch_stands_the_hook_down(
    ticket: Path, repo: Path, session: str, payload: Load, run_hook_script: RunScript
) -> None:
    record_pending(repo, session, 'engineer', 'task-03')
    hook = payload('SubagentStart-engineer') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo, MIGHTYMCP_OFF='1')

    assert proc.returncode == 0
    assert proc.stdout == ''
