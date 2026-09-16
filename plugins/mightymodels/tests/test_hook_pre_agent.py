import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.hookstate import read_state
from mightymcp.routing import HAIKU, OPUS, SONNET
from mightymcp.ticket import HandoffContext, ticket_create

HOOK = Path(__file__).resolve().parents[1].joinpath('hooks', 'pre_agent.py')
CONTEXT = ['the guard runs under uv', 'stdin is one object', 'stdout is one object']
SCOUT_PROMPT = (
    '<objective>Locate every RetryPolicy call site.</objective>\n'
    '<discovery>Search scope: src/app. Terms: "RetryPolicy".</discovery>\n'
)
ENGINEER_PROMPT = '## ASKED\nobjective: cap the retry backoff\n'
BUDGETRON_PROMPT = (
    '<objective>Close one residual.</objective>\n'
    'Fix: add the cap\n'
    'Verify: uv run pytest -q\n'
)
WINGMAN_PROMPT = (
    '<decision>ship or wait</decision>\n'
    '<options>ship now, wait for CI</options>\n'
    '<facts>src/app.py:1 caps the backoff</facts>\n'
    '<lean>ship</lean>\n'
)

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]
Guard = Callable[[dict[str, Any]], dict[str, Any]]
Dispatch = Callable[..., dict[str, Any]]


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
def guard(repo: Path, run_hook_script: RunScript) -> Guard:
    """Run the Agent guard against this repo and return the decision it made."""

    def run(hook: dict[str, Any]) -> dict[str, Any]:
        proc = run_hook_script(HOOK, json.dumps(hook | {'cwd': str(repo)}), repo)
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == '', proc.stderr
        return json.loads(proc.stdout).get('hookSpecificOutput', {})

    return run


@pytest.fixture
def dispatch(payload: Load) -> Dispatch:
    """Build an Agent payload for one mightymodels role."""

    def build(role: str, prompt: str, **tool_input: str) -> dict[str, Any]:
        hook = payload('PreToolUse-Agent')
        named = {'subagent_type': f'mightymodels:{role}', 'prompt': prompt}
        return hook | {'tool_input': hook['tool_input'] | named | tool_input}

    return build


def test_an_agent_from_another_plugin_gets_no_decision(
    ticket: Path, payload: Load, guard: Guard
) -> None:
    assert guard(payload('PreToolUse-Agent')) == {}


def test_an_unknown_mightymodels_role_gets_no_decision(
    ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    assert guard(dispatch('archaeologist', 'anything at all')) == {}


@pytest.mark.parametrize('missing', ['<objective>', '<discovery>'])
def test_a_scout_dispatch_without_its_sections_is_denied(
    missing: str, ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    decision = guard(dispatch('scout', SCOUT_PROMPT.replace(missing, '<other>')))

    assert decision['permissionDecision'] == 'deny'
    assert missing in decision['permissionDecisionReason']


def test_an_engineer_dispatch_without_the_asked_stanza_is_denied(
    ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    decision = guard(dispatch('engineer', 'go implement the thing'))

    assert decision['permissionDecision'] == 'deny'
    assert '## ASKED' in decision['permissionDecisionReason']


@pytest.mark.parametrize('missing', ['Fix:', 'Verify:'])
def test_a_budgetron_dispatch_without_its_lines_is_denied(
    missing: str, ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    prompt = BUDGETRON_PROMPT.replace(missing, 'Note:')
    decision = guard(dispatch('budgetron', prompt))

    assert decision['permissionDecision'] == 'deny'
    assert missing in decision['permissionDecisionReason']


@pytest.mark.parametrize('role', ['grumpy', 'sunny'])
def test_a_reasoning_dispatch_without_a_proposition_is_denied(
    role: str, ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    decision = guard(dispatch(role, '<objective>Attack the plan.</objective>'))

    assert decision['permissionDecision'] == 'deny'
    assert 'proposition' in decision['permissionDecisionReason'].casefold()


@pytest.mark.parametrize(
    'prompt',
    ['<proposition>The cap holds.</proposition>', 'Proposition: the cap holds.'],
)
def test_either_proposition_shape_is_accepted(
    prompt: str, ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    decision = guard(dispatch('grumpy', prompt))

    assert decision['permissionDecision'] == 'allow'
    assert decision['updatedInput']['model'] == SONNET


@pytest.mark.parametrize('missing', ['<decision>', '<options>', '<facts>', '<lean>'])
def test_a_wingman_dispatch_without_its_packet_is_denied(
    missing: str, ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    prompt = WINGMAN_PROMPT.replace(missing, '<other>')
    decision = guard(dispatch('wingman', prompt))

    assert decision['permissionDecision'] == 'deny'
    assert missing in decision['permissionDecisionReason']


def test_a_dispatch_without_a_model_is_rewritten_to_the_resolved_one(
    ticket: Path, payload: Load, guard: Guard
) -> None:
    decision = guard(payload('PreToolUse-Agent-engineer'))

    assert decision['permissionDecision'] == 'allow'
    assert decision['updatedInput']['model'] == SONNET


def test_the_rewrite_carries_the_rest_of_the_tool_input(
    ticket: Path, payload: Load, guard: Guard
) -> None:
    hook = payload('PreToolUse-Agent-engineer')
    decision = guard(hook)

    assert decision['updatedInput'] | hook['tool_input'] == decision['updatedInput']


@pytest.mark.parametrize(('role', 'model'), [('scout', HAIKU), ('wingman', OPUS)])
def test_each_role_resolves_to_its_own_model(
    role: str, model: str, ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    prompts = {'scout': SCOUT_PROMPT, 'wingman': WINGMAN_PROMPT}
    decision = guard(dispatch(role, prompts[role]))

    assert decision['updatedInput']['model'] == model


@pytest.mark.parametrize('alias', ['haiku', 'opus'])
def test_an_alias_that_is_not_the_resolved_model_is_rewritten(
    alias: str, ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    decision = guard(dispatch('engineer', ENGINEER_PROMPT, model=alias))

    assert decision['updatedInput']['model'] == SONNET


@pytest.mark.parametrize('model', ['sonnet', SONNET])
def test_a_dispatch_already_on_the_resolved_model_gets_no_decision(
    model: str, ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    assert guard(dispatch('engineer', ENGINEER_PROMPT, model=model)) == {}


def test_the_ticket_pin_wins_over_the_default(
    ticket: Path, dispatch: Dispatch, guard: Guard
) -> None:
    text = ticket.joinpath('ticket.yml').read_text(encoding='utf-8')
    ticket.joinpath('ticket.yml').write_text(
        text.replace('scout: claude-haiku-4-5', f'scout: {OPUS}'), encoding='utf-8'
    )
    decision = guard(dispatch('scout', SCOUT_PROMPT))

    assert decision['updatedInput']['model'] == OPUS
    assert 'ticket' in decision['permissionDecisionReason']


def test_a_repository_without_a_ticket_still_resolves_the_default(
    repo: Path, payload: Load, guard: Guard
) -> None:
    decision = guard(payload('PreToolUse-Agent-engineer'))

    assert decision['updatedInput']['model'] == SONNET


@pytest.mark.parametrize(
    ('fixture', 'role'),
    [('PreToolUse-Agent-engineer', 'engineer'), ('PreToolUse-Agent-scout', 'scout')],
)
def test_an_allowed_dispatch_naming_a_brief_is_recorded_as_pending(
    fixture: str, role: str, repo: Path, payload: Load, guard: Guard
) -> None:
    hook = payload(fixture)
    guard(hook)
    state = read_state(repo, hook['session_id'])

    assert [(entry.role, entry.task_id) for entry in state.pending] == [(role, 'task-03')]


def test_a_dispatch_that_names_no_brief_records_nothing(
    ticket: Path, repo: Path, dispatch: Dispatch, guard: Guard
) -> None:
    hook = dispatch('scout', SCOUT_PROMPT)
    guard(hook)

    assert read_state(repo, hook['session_id']).pending == []


def test_a_denied_dispatch_records_nothing(
    ticket: Path, repo: Path, dispatch: Dispatch, guard: Guard
) -> None:
    hook = dispatch('engineer', 'briefs/task-03.md, and nothing else')
    guard(hook)

    assert read_state(repo, hook['session_id']).pending == []


def test_two_dispatches_are_recorded_in_the_order_they_were_allowed(
    ticket: Path, repo: Path, payload: Load, guard: Guard
) -> None:
    first = payload('PreToolUse-Agent-engineer')
    second = first | {
        'tool_input': first['tool_input']
        | {'prompt': first['tool_input']['prompt'].replace('task-03', 'task-04')}
    }
    guard(first)
    guard(second)
    state = read_state(repo, first['session_id'])

    assert [entry.task_id for entry in state.pending] == ['task-03', 'task-04']


def test_the_off_switch_stands_the_guard_down(
    ticket: Path, repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    hook = payload('PreToolUse-Agent-engineer') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo, MIGHTYMCP_OFF='1')

    assert proc.returncode == 0
    assert proc.stdout == ''
