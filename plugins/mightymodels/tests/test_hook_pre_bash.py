import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.hookstate import agent_state
from mightymcp.ticket import HandoffContext, ticket_create

HOOK = Path(__file__).resolve().parents[1].joinpath('hooks', 'pre_bash.py')
CONTEXT = ['the guard runs under uv', 'stdin is one object', 'stdout is one object']
MUTATIONS = [
    'rm -rf build',
    'mv src/app.py src/limits.py',
    'sed -i "s/a/b/" src/app.py',
    'cat src/app.py | tee copy.py',
    'echo hi > notes.txt',
    'echo hi >> notes.txt',
    'git add -A',
    'git commit -m "wip"',
    'git push origin main',
    'git checkout -b feat/x',
    'git rebase main',
    'git stash',
    'uv add httpx',
    'uv remove httpx',
    'pip install httpx',
]
READ_ONLY = [
    'rg -n "RetryPolicy" src/app',
    'cat src/app.py',
    'git log --oneline -5',
    'uv run pytest -q',
    'ls -la src',
]

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]
Guard = Callable[..., dict[str, Any]]


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
def guard(repo: Path, payload: Load, run_hook_script: RunScript) -> Guard:
    """Run the Bash guard against this repo and return the decision it made."""

    def run(command: str, **agent: str) -> dict[str, Any]:
        hook = payload('PreToolUse-Bash-scout')
        hook = hook | {
            'cwd': str(repo),
            'tool_input': hook['tool_input'] | {'command': command},
        }
        for key in ('agent_id', 'agent_type'):
            hook.pop(key, None)
        proc = run_hook_script(HOOK, json.dumps(hook | agent), repo)
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == '', proc.stderr
        return json.loads(proc.stdout).get('hookSpecificOutput', {})

    return run


def scout(**overrides: str) -> dict[str, str]:
    return {'agent_id': 'agent_01', 'agent_type': 'scout'} | overrides


def bash_calls(repo: Path, session: str) -> int:
    """The Bash calls the state file records against the scout helper's agent."""
    state = agent_state(repo, session, 'agent_01')
    assert state is not None
    return state.bash_calls


def test_an_ordinary_command_is_left_alone(ticket: Path, guard: Guard) -> None:
    assert guard('uv run pytest -q') == {}


@pytest.mark.parametrize(
    'command',
    [
        'git commit --no-verify -m "wip"',
        'git push --force origin main',
        'git push -f origin main',
        'git push --force-with-lease',
        'git reset --hard origin/main',
        'git push origin main --force',
        'git push origin x -f',
        'git reset HEAD~1 --hard',
        'git commit --no-verify',
    ],
)
def test_a_never_rule_is_denied_for_anyone(
    command: str, ticket: Path, guard: Guard
) -> None:
    decision = guard(command)

    assert decision['permissionDecision'] == 'deny'
    assert 'never-rule' in decision['permissionDecisionReason']


def test_a_never_rule_names_itself_in_the_reason(ticket: Path, guard: Guard) -> None:
    decision = guard('git push --force origin main')

    assert 'push --force' in decision['permissionDecisionReason']


@pytest.mark.parametrize(
    'command',
    [
        'command grep -rn -- "--no-verify" .',
        'echo "never use push --force here"',
    ],
)
def test_a_never_rule_named_in_an_argument_is_left_alone(
    command: str, ticket: Path, guard: Guard
) -> None:
    assert guard(command) == {}


def test_a_never_rule_denial_costs_a_scout_no_budget(
    ticket: Path, repo: Path, payload: Load, guard: Guard
) -> None:
    session = payload('PreToolUse-Bash-scout')['session_id']
    assert guard('cat src/app.py', **scout()) == {}
    before = bash_calls(repo, session)

    decision = guard('git push --force origin main', **scout())

    assert decision['permissionDecision'] == 'deny'
    assert bash_calls(repo, session) == before


def test_gitty_up_may_not_run_git(ticket: Path, guard: Guard) -> None:
    decision = guard('git log --oneline -5', **scout(agent_type='gitty-up'))

    assert decision['permissionDecision'] == 'deny'
    assert 'gitty-up' in decision['permissionDecisionReason']


def test_gitty_up_still_runs_gh(ticket: Path, guard: Guard) -> None:
    assert guard('gh pr checks 12 --json state', **scout(agent_type='gitty-up')) == {}


@pytest.mark.parametrize('command', MUTATIONS)
def test_a_scout_may_not_mutate_state(command: str, ticket: Path, guard: Guard) -> None:
    decision = guard(command, **scout())

    assert decision['permissionDecision'] == 'deny'
    assert 'read-only' in decision['permissionDecisionReason']


def test_a_scout_may_not_mutate_after_an_unspaced_operator(
    ticket: Path, guard: Guard
) -> None:
    decision = guard('echo y&&rm -rf x', **scout())

    assert decision['permissionDecision'] == 'deny'
    assert 'rm mutates state' in decision['permissionDecisionReason']


def test_a_scout_may_not_redirect_without_spaces(ticket: Path, guard: Guard) -> None:
    decision = guard('echo x>file', **scout())

    assert decision['permissionDecision'] == 'deny'
    assert 'a redirection' in decision['permissionDecisionReason']


@pytest.mark.parametrize('command', READ_ONLY)
def test_a_scout_runs_read_only_commands(
    command: str, ticket: Path, guard: Guard
) -> None:
    assert guard(command, **scout()) == {}


def test_the_primary_may_still_mutate_state(ticket: Path, guard: Guard) -> None:
    assert guard('git add -A') == {}


def test_a_scout_runs_out_of_budget_on_its_sixth_call(ticket: Path, guard: Guard) -> None:
    for _ in range(5):
        assert guard('cat src/app.py', **scout()) == {}
    decision = guard('cat src/app.py', **scout())

    assert decision['permissionDecision'] == 'deny'
    assert '5 Bash calls' in decision['permissionDecisionReason']


def test_a_budgetron_runs_out_of_budget_on_its_eleventh_call(
    ticket: Path, guard: Guard
) -> None:
    budgetron = scout(agent_type='budgetron')
    for _ in range(10):
        assert guard('uv run pytest -q', **budgetron) == {}
    decision = guard('uv run pytest -q', **budgetron)

    assert decision['permissionDecision'] == 'deny'
    assert '10 Bash calls' in decision['permissionDecisionReason']


def test_each_subagent_carries_its_own_budget(ticket: Path, guard: Guard) -> None:
    for _ in range(5):
        guard('cat src/app.py', **scout())

    assert guard('cat src/app.py', **scout(agent_id='agent_02')) == {}


def test_the_primary_has_no_bash_budget(ticket: Path, guard: Guard) -> None:
    for _ in range(11):
        assert guard('uv run pytest -q') == {}


def test_a_clean_ticket_may_be_pruned(ticket: Path, guard: Guard) -> None:
    assert guard('rm -rf .mightymodels/demo') == {}


def test_a_ticket_with_live_work_may_not_be_pruned(ticket: Path, guard: Guard) -> None:
    ticket.joinpath('whats-broken.md').write_text('# broken\n', encoding='utf-8')
    decision = guard('rm -rf .mightymodels/demo')

    assert decision['permissionDecision'] == 'deny'
    assert 'whats-broken.md' in decision['permissionDecisionReason']


def test_an_open_report_thread_blocks_the_prune(ticket: Path, guard: Guard) -> None:
    ticket.joinpath('REPORT.md').write_text(
        '# REPORT: demo\n\nopen threads:\n- the retry test is still red\n',
        encoding='utf-8',
    )
    decision = guard('rm -rf .mightymodels/demo')

    assert decision['permissionDecision'] == 'deny'
    assert 'the retry test is still red' in decision['permissionDecisionReason']


def test_a_removal_outside_the_ticket_directory_is_left_alone(
    ticket: Path, guard: Guard
) -> None:
    ticket.joinpath('whats-broken.md').write_text('# broken\n', encoding='utf-8')

    assert guard('rm -rf build') == {}


def test_a_removal_that_is_not_recursive_is_left_alone(
    ticket: Path, guard: Guard
) -> None:
    ticket.joinpath('whats-broken.md').write_text('# broken\n', encoding='utf-8')

    assert guard('rm .mightymodels/demo/REPORT.md') == {}


def test_an_absolute_removal_path_is_read_the_same_way(
    ticket: Path, guard: Guard
) -> None:
    ticket.joinpath('whats-broken.md').write_text('# broken\n', encoding='utf-8')
    decision = guard(f'rm -rf {ticket}')

    assert decision['permissionDecision'] == 'deny'


def test_an_unparseable_command_is_still_read(ticket: Path, guard: Guard) -> None:
    decision = guard('git commit -m "unbalanced --no-verify', **scout())

    assert decision['permissionDecision'] == 'deny'


def test_the_off_switch_stands_the_guard_down(
    ticket: Path, repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    hook = payload('PreToolUse-Bash-scout')
    hook = hook | {
        'cwd': str(repo),
        'tool_input': hook['tool_input'] | {'command': 'rm -rf build'},
    }
    proc = run_hook_script(HOOK, json.dumps(hook), repo, MIGHTYMCP_OFF='1')

    assert proc.returncode == 0
    assert proc.stdout == ''
