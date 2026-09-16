import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.hookstate import bind_agent, record_pending
from mightymcp.ticket import HandoffContext, ticket_create

HOOK = Path(__file__).resolve().parents[1].joinpath('hooks', 'subagent_stop.py')
CONTEXT = ['the gate runs under uv', 'stdin is one object', 'stdout is one object']
SCOUT_REPORT = (
    '<report>\n  <verdict>VERIFIED</verdict>\n  <confidence>high</confidence>\n</report>'
)
UNPARSEABLE = 'I had a look and it all seems fine to me.'
CI_REPORT = (
    '<report pr="12">\n  <verdict>{verdict}</verdict>\n'
    '  <confidence>high</confidence>\n</report>'
)

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]
Stop = Callable[..., dict[str, Any]]


@pytest.fixture
def ticket(repo: Path) -> Path:
    written = ticket_create(
        'demo',
        'Ship demo',
        CONTEXT,
        HandoffContext(scope='med', plan_first=True, branch_name='main'),
    )
    assert written.refusals == [], written.refusals
    return repo.joinpath('.mightymodels', 'demo')


@pytest.fixture
def session(payload: Load) -> str:
    return payload('SubagentStop')['session_id']


@pytest.fixture
def stop(repo: Path, payload: Load, run_hook_script: RunScript) -> Stop:
    """Stop one subagent through the hook and return the decision it returned."""

    def run(**overrides: Any) -> dict[str, Any]:
        hook = payload('SubagentStop') | {'cwd': str(repo)} | overrides
        proc = run_hook_script(HOOK, json.dumps(hook), repo)
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == '', proc.stderr
        decision: dict[str, Any] = json.loads(proc.stdout)
        return decision

    return run


def dispatches(ticket: Path) -> list[dict[str, Any]]:
    log = ticket.joinpath('dispatches.jsonl')
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]


def test_an_agent_from_another_plugin_is_neither_gated_nor_logged(
    ticket: Path, stop: Stop
) -> None:
    assert stop(agent_type='researcher', last_assistant_message=UNPARSEABLE) == {}
    assert dispatches(ticket) == []


def test_a_re_entered_stop_hook_is_left_alone(ticket: Path, stop: Stop) -> None:
    assert stop(stop_hook_active=True, last_assistant_message=UNPARSEABLE) == {}
    assert dispatches(ticket) == []


def test_a_well_formed_report_passes(ticket: Path, stop: Stop) -> None:
    assert stop(last_assistant_message=SCOUT_REPORT) == {}


def test_an_engineer_report_is_parsed_for_its_own_role(
    ticket: Path, repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    hook = payload('SubagentStop-engineer') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo)

    assert json.loads(proc.stdout) == {}
    assert dispatches(ticket)[0]['verdict'] == 'done'


def test_a_message_that_is_not_a_report_is_blocked(ticket: Path, stop: Stop) -> None:
    decision = stop(last_assistant_message=UNPARSEABLE)

    assert decision['decision'] == 'block'
    assert 'no <report> element' in decision['reason']


def test_the_block_reason_carries_every_refusal(ticket: Path, stop: Stop) -> None:
    decision = stop(
        last_assistant_message=(
            '<report><verdict>MAYBE</verdict><confidence>certain</confidence></report>'
        )
    )

    assert "verdict 'MAYBE' is outside the scout vocabulary" in decision['reason']
    assert "; confidence 'certain' is not high, medium, low" in decision['reason']


def test_every_stop_appends_one_line_with_its_fields(
    ticket: Path, session: str, stop: Stop
) -> None:
    stop(last_assistant_message=SCOUT_REPORT)
    stop(last_assistant_message=SCOUT_REPORT)
    logged = dispatches(ticket)

    assert len(logged) == 2
    assert sorted(logged[0]) == [
        'agent_id',
        'agent_type',
        'ok',
        'session_id',
        'task_id',
        'ts',
        'verdict',
    ]
    assert logged[0]['session_id'] == session
    assert logged[0]['agent_id'] == 'agent_01J8QK3P7N'
    assert logged[0]['agent_type'] == 'scout'
    assert logged[0]['verdict'] == 'VERIFIED'
    assert logged[0]['ok'] is True
    assert logged[0]['task_id'] == ''


def test_the_logged_task_id_comes_from_the_binding(
    ticket: Path, repo: Path, session: str, stop: Stop
) -> None:
    record_pending(repo, session, 'scout', 'task-03')
    bind_agent(repo, session, 'agent_01J8QK3P7N', 'scout')
    stop(last_assistant_message=SCOUT_REPORT)

    assert dispatches(ticket)[0]['task_id'] == 'task-03'


def test_a_blocked_report_is_logged_as_not_ok(ticket: Path, stop: Stop) -> None:
    stop(last_assistant_message=UNPARSEABLE)
    logged = dispatches(ticket)[0]

    assert logged['ok'] is False
    assert logged['verdict'] == ''


@pytest.mark.parametrize('verdict', ['fail', 'error'])
def test_a_ci_verdict_that_stops_the_loop_is_logged_never_blocked(
    verdict: str, ticket: Path, stop: Stop
) -> None:
    decision = stop(
        agent_type='mightymodels:gitty-up',
        last_assistant_message=CI_REPORT.format(verdict=verdict),
    )
    logged = dispatches(ticket)[0]

    assert decision == {}
    assert logged['agent_type'] == 'gitty-up'
    assert logged['verdict'] == verdict
    assert logged['ok'] is False


def test_a_passing_ci_verdict_is_logged_as_ok(ticket: Path, stop: Stop) -> None:
    stop(
        agent_type='mightymodels:gitty-up',
        last_assistant_message=CI_REPORT.format(verdict='pass'),
    )

    assert dispatches(ticket)[0]['ok'] is True


def test_a_stop_with_no_ticket_is_still_gated(repo: Path, stop: Stop) -> None:
    decision = stop(last_assistant_message=UNPARSEABLE)

    assert decision['decision'] == 'block'
    assert list(repo.joinpath('.mightymodels').glob('*/dispatches.jsonl')) == []


def test_the_off_switch_stands_the_hook_down(
    ticket: Path, repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    hook = payload('SubagentStop') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo, MIGHTYMCP_OFF='1')

    assert proc.returncode == 0
    assert proc.stdout == ''
    assert dispatches(ticket) == []
