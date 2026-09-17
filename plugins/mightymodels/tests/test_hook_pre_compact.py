import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.brief import AskedStanza, brief_open
from mightymcp.hookstate import bind_agent, record_pending
from mightymcp.ticket import HandoffContext, ticket_create

HOOK = Path(__file__).resolve().parents[1].joinpath('hooks', 'pre_compact.py')
CONTEXT = ['the snapshot is regenerated', 'paths not pastes', 'caps are contracts']
CAP = 40

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]
Compact = Callable[..., str]


def write_brief(task_id: str) -> None:
    written = brief_open(
        'demo',
        task_id,
        AskedStanza(
            objective='Cap the retry backoff',
            acceptance=['AC-1: uv run pytest -q passes'],
            verification='uv run pytest -q',
            files_in_scope=['src/app/**'],
            engineer_tier='claude-sonnet-5',
        ),
        'feat(app): cap the retry backoff',
    )
    assert written.refusals == [], written.refusals


@pytest.fixture
def ticket(repo: Path, commit: Callable[[Path, str], str]) -> Path:
    commit(repo, 'README.md')
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
def session(payload: Load) -> str:
    return payload('PreCompact')['session_id']


@pytest.fixture
def compact(repo: Path, payload: Load, run_hook_script: RunScript) -> Compact:
    """Run one compaction through the hook and return the snapshot it left behind."""

    def run(**overrides: Any) -> str:
        hook = payload('PreCompact') | {'cwd': str(repo)} | overrides
        proc = run_hook_script(HOOK, json.dumps(hook), repo)
        assert proc.returncode == 0, proc.stderr
        assert proc.stderr == '', proc.stderr
        assert json.loads(proc.stdout) == {}
        snapshot = repo.joinpath('.mightymodels', 'demo', 'snapshot.md')
        return snapshot.read_text(encoding='utf-8') if snapshot.is_file() else ''

    return run


@pytest.mark.parametrize('trigger', ['auto', 'manual'])
def test_the_snapshot_names_the_trigger(
    trigger: str, ticket: Path, compact: Compact
) -> None:
    assert f'# snapshot before the {trigger} compaction' in compact(trigger=trigger)


def test_the_snapshot_names_the_branch_and_the_short_sha(
    ticket: Path, repo: Path, git: Callable[..., str], compact: Compact
) -> None:
    sha = git(repo, 'rev-parse', '--short', 'HEAD')

    assert f'branch: main @ {sha}' in compact()


def test_the_snapshot_carries_the_sprint_status_rows(
    ticket: Path, compact: Compact
) -> None:
    snapshot = compact()

    assert 'task-03: asked, 0 attempts, commit none' in snapshot
    assert 'demo: 1 tasks, 0 done, 0 verified' in snapshot


def test_the_snapshot_lists_the_pending_and_the_bound_agents(
    ticket: Path, repo: Path, session: str, compact: Compact
) -> None:
    record_pending(repo, session, 'engineer', 'task-03')
    record_pending(repo, session, 'scout', 'task-03')
    bind_agent(repo, session, 'agent_01', 'engineer')
    snapshot = compact()

    assert '- scout task-03' in snapshot
    assert '- agent_01: engineer task-03' in snapshot


def test_an_empty_hookstate_says_so(ticket: Path, compact: Compact) -> None:
    snapshot = compact()

    assert 'pending dispatches:\n- none' in snapshot
    assert 'bound agents:\n- none' in snapshot


def test_the_baton_pointer_appears_once_the_baton_is_written(
    ticket: Path, compact: Compact
) -> None:
    assert 'baton waiting' not in compact()

    baton = ticket.joinpath('handoffs', 'BATON.md')
    baton.write_text('# BATON\n', encoding='utf-8')

    assert f'baton waiting: {baton}' in compact()


def test_the_snapshot_is_regenerated_rather_than_appended(
    ticket: Path, compact: Compact
) -> None:
    first = compact()

    assert compact() == first


def test_a_long_sprint_is_truncated_to_the_cap(ticket: Path, compact: Compact) -> None:
    for number in range(4, 60):
        write_brief(f'task-{number:02d}')
    snapshot = compact()

    assert len(snapshot.splitlines()) <= CAP
    assert 'more rows' in snapshot
    assert 'bound agents:' in snapshot


def test_a_session_with_no_active_ticket_writes_nothing(
    repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    hook = payload('PreCompact') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo)

    assert json.loads(proc.stdout) == {}
    assert list(repo.joinpath('.mightymodels').glob('*/snapshot.md')) == []


def test_a_snapshot_that_cannot_be_written_says_so_on_stderr(
    ticket: Path, repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    ticket.joinpath('snapshot.md').mkdir()
    hook = payload('PreCompact') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo)

    assert proc.returncode == 0
    assert proc.stderr.startswith('mightymcp hook stood down: ')
    assert 'snapshot.md' in proc.stderr
    assert json.loads(proc.stdout) == {}


def test_the_off_switch_stands_the_hook_down(
    ticket: Path, repo: Path, payload: Load, run_hook_script: RunScript
) -> None:
    hook = payload('PreCompact') | {'cwd': str(repo)}
    proc = run_hook_script(HOOK, json.dumps(hook), repo, MIGHTYMCP_OFF='1')

    assert proc.returncode == 0
    assert proc.stdout == ''
    assert not ticket.joinpath('snapshot.md').exists()
