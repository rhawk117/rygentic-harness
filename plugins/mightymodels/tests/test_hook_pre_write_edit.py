import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.brief import AskedStanza, brief_open
from mightymcp.hookstate import bind_agent, record_pending
from mightymcp.ticket import HandoffContext, ticket_create

HOOK = Path(__file__).resolve().parents[1].joinpath('hooks', 'pre_write_edit.py')
CONTEXT = ['the guard runs under uv', 'stdin is one object', 'stdout is one object']
SCOPE = ['src/app/**', 'tests/test_app.py']
AGENT = 'agent_01'
DONE_HALF = (
    '## DONE\nwhat: capped the backoff\ncommit: abc1234\n'
    'diff-summary: one file\ncommands-run: uv run pytest -q\n'
)

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]
Guard = Callable[[dict[str, Any]], dict[str, Any]]
Build = Callable[..., dict[str, Any]]


@pytest.fixture
def ticket(repo: Path) -> Path:
    written = ticket_create(
        'demo',
        'Ship demo',
        CONTEXT,
        HandoffContext(scope='med', plan_first=True, branch_name='main'),
    )
    assert written.refusals == [], written.refusals
    opened = brief_open(
        'demo',
        'task-03',
        AskedStanza(
            objective='Cap the retry backoff',
            acceptance=['AC-1: uv run pytest -q passes'],
            verification='uv run pytest -q',
            files_in_scope=SCOPE,
            engineer_tier='claude-sonnet-5',
        ),
        'feat(app): cap the retry backoff',
    )
    assert opened.refusals == [], opened.refusals
    return repo.joinpath('.mightymodels', 'demo')


@pytest.fixture
def guard(repo: Path, run_hook_script: RunScript) -> Guard:
    """Run the Write and Edit guard against this repo and return its decision."""

    def run(hook: dict[str, Any]) -> dict[str, Any]:
        proc = run_hook_script(HOOK, json.dumps(hook | {'cwd': str(repo)}), repo)
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == '', proc.stderr
        return json.loads(proc.stdout).get('hookSpecificOutput', {})

    return run


@pytest.fixture
def write(payload: Load) -> Build:
    """Build a Write payload for one path."""

    def build(target: Path, content: str, **extra: str) -> dict[str, Any]:
        hook = payload('PreToolUse-Write')
        named = {'file_path': str(target), 'content': content}
        return hook | {'tool_input': hook['tool_input'] | named} | extra

    return build


@pytest.fixture
def edit(payload: Load) -> Build:
    """Build an Edit payload for one path."""

    def build(
        target: Path, old: str, new: str, *, replace_all: bool = False, **extra: str
    ) -> dict[str, Any]:
        hook = payload('PreToolUse-Edit')
        named = {
            'file_path': str(target),
            'old_string': old,
            'new_string': new,
            'replace_all': replace_all,
        }
        return hook | {'tool_input': hook['tool_input'] | named} | extra

    return build


@pytest.fixture
def engineer(repo: Path, ticket: Path, payload: Load) -> str:
    """Bind an engineer subagent to task-03, the way SubagentStart does."""
    session = payload('PreToolUse-Write')['session_id']
    record_pending(repo, session, 'engineer', 'task-03')
    bind_agent(repo, session, AGENT, 'engineer')
    return AGENT


@pytest.fixture
def dir_scope_engineer(repo: Path, ticket: Path, payload: Load) -> str:
    """Bind an engineer subagent to a task whose scope is a bare directory."""
    opened = brief_open(
        'demo',
        'task-04',
        AskedStanza(
            objective='Cap the retry backoff',
            acceptance=['AC-1: uv run pytest -q passes'],
            verification='uv run pytest -q',
            files_in_scope=['a/b'],
            engineer_tier='claude-sonnet-5',
        ),
        'feat(app): cap the retry backoff',
    )
    assert opened.refusals == [], opened.refusals
    session = payload('PreToolUse-Write')['session_id']
    record_pending(repo, session, 'engineer', 'task-04')
    bind_agent(repo, session, 'agent_02', 'engineer')
    return 'agent_02'


def lines(count: int) -> str:
    return ''.join(f'line {number}\n' for number in range(count))


def test_a_write_outside_the_ticket_directory_is_left_alone(
    ticket: Path, repo: Path, write: Build, guard: Guard
) -> None:
    assert guard(write(repo.joinpath('src', 'app.py'), lines(400))) == {}


@pytest.mark.parametrize(
    ('relative', 'cap'),
    [
        (('briefs', 'task-03.md'), 80),
        (('REPORT.md',), 50),
        (('handoffs', 'BATON.md'), 40),
        (('decisions.md',), 40),
    ],
)
def test_a_ticket_artifact_over_its_cap_is_denied(
    relative: tuple[str, ...], cap: int, ticket: Path, write: Build, guard: Guard
) -> None:
    decision = guard(write(ticket.joinpath(*relative), lines(cap + 1)))

    assert decision['permissionDecision'] == 'deny'
    assert f'the cap is {cap}' in decision['permissionDecisionReason']


@pytest.mark.parametrize(
    ('relative', 'cap'),
    [
        (('briefs', 'task-03.md'), 80),
        (('REPORT.md',), 50),
        (('handoffs', 'BATON.md'), 40),
        (('decisions.md',), 40),
    ],
)
def test_a_ticket_artifact_at_its_cap_is_allowed(
    relative: tuple[str, ...], cap: int, ticket: Path, write: Build, guard: Guard
) -> None:
    assert guard(write(ticket.joinpath(*relative), lines(cap))) == {}


def test_an_archive_over_thirty_lines_is_denied(
    ticket: Path, repo: Path, write: Build, guard: Guard
) -> None:
    archive = repo.joinpath('.mightymodels', 'archives', 'demo.md')
    decision = guard(write(archive, lines(31)))

    assert decision['permissionDecision'] == 'deny'
    assert 'the cap is 30' in decision['permissionDecisionReason']


def test_an_archive_at_thirty_lines_is_allowed(
    ticket: Path, repo: Path, write: Build, guard: Guard
) -> None:
    archive = repo.joinpath('.mightymodels', 'archives', 'demo.md')

    assert guard(write(archive, lines(30))) == {}


def test_an_edit_is_judged_on_the_content_it_would_leave(
    ticket: Path, guard: Guard, edit: Build
) -> None:
    baton = ticket.joinpath('handoffs', 'BATON.md')
    baton.write_text(lines(39), encoding='utf-8')
    decision = guard(edit(baton, 'line 0\n', lines(3)))

    assert decision['permissionDecision'] == 'deny'
    assert 'the cap is 40' in decision['permissionDecisionReason']


def test_replace_all_counts_every_occurrence(
    ticket: Path, guard: Guard, edit: Build
) -> None:
    baton = ticket.joinpath('handoffs', 'BATON.md')
    baton.write_text('grow\n' * 2 + lines(37), encoding='utf-8')
    grown = 'grow\ngrow\n'

    assert guard(edit(baton, 'grow\n', grown)) == {}
    decision = guard(edit(baton, 'grow\n', grown, replace_all=True))
    assert decision['permissionDecision'] == 'deny'


def test_the_crashout_journal_is_never_written(
    ticket: Path, repo: Path, write: Build, guard: Guard
) -> None:
    journal = repo.joinpath('.mightymodels', 'crashouts.yml')
    journal.write_text('entries: []\n', encoding='utf-8')
    decision = guard(write(journal, 'entries: []\n'))

    assert decision['permissionDecision'] == 'deny'
    assert 'crashouts.yml' in decision['permissionDecisionReason']


def test_the_crashout_journal_is_never_edited(
    ticket: Path, repo: Path, edit: Build, guard: Guard
) -> None:
    journal = repo.joinpath('.mightymodels', 'crashouts.yml')
    journal.write_text('entries: []\n', encoding='utf-8')
    decision = guard(edit(journal, 'entries: []', 'entries: [one]'))

    assert decision['permissionDecision'] == 'deny'
    assert 'crashouts.yml' in decision['permissionDecisionReason']


def test_the_primary_may_not_append_the_done_half(
    ticket: Path, write: Build, guard: Guard
) -> None:
    brief = ticket.joinpath('briefs', 'task-03.md')
    content = brief.read_text(encoding='utf-8') + DONE_HALF
    decision = guard(write(brief, content))

    assert decision['permissionDecision'] == 'deny'
    assert '## DONE' in decision['permissionDecisionReason']


def test_a_worker_may_append_the_done_half(
    ticket: Path, write: Build, guard: Guard
) -> None:
    brief = ticket.joinpath('briefs', 'task-03.md')
    content = brief.read_text(encoding='utf-8') + DONE_HALF

    assert guard(write(brief, content, agent_type='engineer')) == {}


def test_a_brief_write_that_adds_no_done_half_is_left_alone(
    ticket: Path, payload: Load, guard: Guard
) -> None:
    hook = payload('PreToolUse-Write-brief')
    named = {'file_path': str(ticket.joinpath('briefs', 'task-03.md'))}

    assert guard(hook | {'tool_input': hook['tool_input'] | named}) == {}


def test_an_engineer_writes_inside_its_files_in_scope(
    ticket: Path, repo: Path, engineer: str, write: Build, guard: Guard
) -> None:
    target = repo.joinpath('src', 'app', 'limits.py')

    assert guard(write(target, 'LIMIT = 10\n', agent_id=engineer)) == {}


def test_an_engineer_is_denied_a_path_outside_its_files_in_scope(
    ticket: Path, repo: Path, engineer: str, write: Build, guard: Guard
) -> None:
    decision = guard(
        write(repo.joinpath('src', 'other.py'), 'LIMIT = 10\n', agent_id=engineer)
    )

    assert decision['permissionDecision'] == 'deny'
    assert 'files-in-scope' in decision['permissionDecisionReason']
    assert 'task-03' in decision['permissionDecisionReason']


def test_an_engineer_writes_inside_a_bare_directory_scope(
    ticket: Path, repo: Path, dir_scope_engineer: str, write: Build, guard: Guard
) -> None:
    target = repo.joinpath('a', 'b', 'c.py')

    assert guard(write(target, 'LIMIT = 10\n', agent_id=dir_scope_engineer)) == {}


def test_an_engineer_is_denied_a_sibling_of_a_bare_directory_scope(
    ticket: Path, repo: Path, dir_scope_engineer: str, write: Build, guard: Guard
) -> None:
    decision = guard(
        write(repo.joinpath('a', 'bc.py'), 'LIMIT = 10\n', agent_id=dir_scope_engineer)
    )

    assert decision['permissionDecision'] == 'deny'
    assert 'files-in-scope' in decision['permissionDecisionReason']


def test_an_engineer_is_denied_a_path_outside_the_repository(
    ticket: Path, tmp_path: Path, engineer: str, write: Build, guard: Guard
) -> None:
    decision = guard(
        write(tmp_path.joinpath('elsewhere.py'), 'x = 1\n', agent_id=engineer)
    )

    assert decision['permissionDecision'] == 'deny'


def test_an_engineer_may_append_the_done_half_of_its_own_brief(
    ticket: Path, engineer: str, write: Build, guard: Guard
) -> None:
    brief = ticket.joinpath('briefs', 'task-03.md')
    content = brief.read_text(encoding='utf-8') + DONE_HALF
    hook = write(brief, content, agent_id=engineer, agent_type='engineer')

    assert guard(hook) == {}


def test_an_engineer_may_not_rewrite_the_asked_half(
    ticket: Path, engineer: str, write: Build, guard: Guard
) -> None:
    brief = ticket.joinpath('briefs', 'task-03.md')
    content = brief.read_text(encoding='utf-8').replace(
        'files-in-scope: [src/app/**, tests/test_app.py]', 'files-in-scope: [src/**]'
    )
    hook = write(brief, content, agent_id=engineer, agent_type='engineer')
    decision = guard(hook)

    assert decision['permissionDecision'] == 'deny'
    assert 'ASKED' in decision['permissionDecisionReason']


def test_an_unbound_subagent_writes_where_it_likes(
    ticket: Path, repo: Path, write: Build, guard: Guard
) -> None:
    hook = write(repo.joinpath('src', 'other.py'), 'x = 1\n', agent_id='agent_99')

    assert guard(hook) == {}


def test_the_off_switch_stands_the_guard_down(
    ticket: Path, repo: Path, write: Build, run_hook_script: RunScript
) -> None:
    hook = write(ticket.joinpath('REPORT.md'), lines(200)) | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo, MIGHTYMCP_OFF='1')

    assert proc.returncode == 0
    assert proc.stdout == ''
