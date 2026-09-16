import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from mightymcp.ticket import CompanionDocs, HandoffContext, ticket_create

HOOK = Path(__file__).resolve().parents[1].joinpath('hooks', 'post_bash.py')
CONTEXT = ['gh prints the url it opened', 'the ticket is the record', 'order is kept']
PR_URL = 'https://github.com/dev/project/pull/42'
ISSUE_URL = 'https://github.com/dev/project/issues/7'

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]
Capture = Callable[..., None]


@pytest.fixture
def ticket(repo: Path) -> Path:
    written = ticket_create(
        'demo',
        'Ship demo',
        CONTEXT,
        HandoffContext(scope='med', plan_first=True, branch_name='main'),
        CompanionDocs(jira_key='PROJ-1'),
    )
    assert written.refusals == [], written.refusals
    return repo.joinpath('.mightymodels', 'demo', 'ticket.yml')


@pytest.fixture
def capture(repo: Path, payload: Load, run_hook_script: RunScript) -> Capture:
    """Run one finished Bash call through the hook, asserting it decides nothing."""

    def run(command: str, stdout: str) -> None:
        hook = payload('PostToolUse-Bash-pr')
        hook['cwd'] = str(repo)
        hook['tool_input']['command'] = command
        hook['tool_response']['stdout'] = stdout
        proc = run_hook_script(HOOK, json.dumps(hook), repo)
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == '', proc.stderr
        assert json.loads(proc.stdout) == {}

    return run


def docs(ticket: Path) -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(ticket.read_text(encoding='utf-8'))
    return raw['companion-docs']


def test_the_pr_number_gh_printed_lands_in_the_ticket(
    ticket: Path, repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    hook = payload('PostToolUse-Bash-pr') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo)

    assert json.loads(proc.stdout) == {}
    assert docs(ticket)['pr-number'] == 42


def test_the_issue_number_gh_printed_lands_in_the_ticket(
    ticket: Path, capture: Capture
) -> None:
    capture('gh issue create --title Bug', f'Creating issue\n{ISSUE_URL}\n')

    assert docs(ticket)['issue-number'] == 7


def test_the_capture_leaves_every_other_field_and_its_order_alone(
    ticket: Path, capture: Capture
) -> None:
    before = yaml.safe_load(ticket.read_text(encoding='utf-8'))
    capture('gh pr create --fill', f'{PR_URL}\n')
    after = yaml.safe_load(ticket.read_text(encoding='utf-8'))

    assert list(after) == list(before)
    assert after['companion-docs']['jira-key'] == 'PROJ-1'
    assert after['subagent-models'] == before['subagent-models']
    assert after['handoff-context'] == before['handoff-context']
    assert after['context'] == before['context']


def test_any_other_command_leaves_the_ticket_untouched(
    ticket: Path, capture: Capture
) -> None:
    before = ticket.read_bytes()
    capture('uv run pytest -q', f'750 passed\n{PR_URL}\n')

    assert ticket.read_bytes() == before


def test_a_gh_create_that_printed_no_url_leaves_the_ticket_untouched(
    ticket: Path, capture: Capture
) -> None:
    before = ticket.read_bytes()
    capture('gh pr create --fill', 'pull request create failed: no commits\n')

    assert ticket.read_bytes() == before


def test_an_issue_url_is_not_read_as_a_pr_number(ticket: Path, capture: Capture) -> None:
    before = ticket.read_bytes()
    capture('gh pr create --fill', f'see {ISSUE_URL}\n')

    assert ticket.read_bytes() == before


def test_a_session_with_no_active_ticket_writes_nothing(
    repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    hook = payload('PostToolUse-Bash-pr') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo)

    assert json.loads(proc.stdout) == {}
    assert list(repo.joinpath('.mightymodels').glob('*/ticket.yml')) == []


def test_the_off_switch_stands_the_hook_down(
    ticket: Path, repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    hook = payload('PostToolUse-Bash-pr') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo, MIGHTYMCP_OFF='1')

    assert proc.returncode == 0
    assert proc.stdout == ''
    assert docs(ticket)['pr-number'] is None
