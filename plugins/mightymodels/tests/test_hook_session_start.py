import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.fleet import load_fleet
from mightymcp.routing import MODEL_ROLES
from mightymcp.ticket import HandoffContext, resolve_model, ticket_create

HOOK = Path(__file__).resolve().parents[1].joinpath('hooks', 'session_start.py')
CONTEXT = ['the hook runs under uv', 'stdin is one json object', 'stdout is one object']
MAX_LINES = 60

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]


def make_ticket(slug: str, branch: str = 'main') -> None:
    written = ticket_create(
        slug,
        f'Ship {slug}',
        CONTEXT,
        HandoffContext(scope='med', plan_first=True, branch_name=branch),
    )
    assert written.refusals == [], written.refusals


def commit(git: Callable[..., str], repo: Path) -> None:
    repo.joinpath('README.md').write_text('demo\n', encoding='utf-8')
    git(repo, 'add', '-A')
    git(
        repo,
        '-c',
        'user.email=test@example.com',
        '-c',
        'user.name=test',
        '-c',
        'commit.gpgsign=false',
        'commit',
        '-q',
        '-m',
        'demo',
    )


def context_of(proc: subprocess.CompletedProcess[str]) -> str:
    assert proc.returncode == 0, proc.stderr
    assert len(proc.stdout.strip().splitlines()) == 1, proc.stdout
    output = json.loads(proc.stdout)
    assert output['hookSpecificOutput']['hookEventName'] == 'SessionStart'
    return output['hookSpecificOutput']['additionalContext']


@pytest.fixture
def session(repo: Path, payload: Load, run_hook_script: RunScript) -> Callable[..., str]:
    """Run the SessionStart hook against this repo and return the injected context."""

    def run(source: str = 'startup') -> str:
        stdin = json.dumps(payload(f'SessionStart-{source}') | {'cwd': str(repo)})
        return context_of(run_hook_script(HOOK, stdin, repo))

    return run


@pytest.fixture
def ticket(repo: Path) -> Path:
    make_ticket('demo')
    return repo.joinpath('.mightymodels', 'demo')


def test_every_fleet_worker_is_named_with_its_job_and_model(
    ticket: Path, session: Callable[..., str]
) -> None:
    context = session()
    workers = load_fleet().workers

    assert len(workers) == 7
    for worker in workers:
        assert f'{worker.name} ({worker.model}): {worker.job}' in context


def test_the_ticket_slug_and_summary_are_injected(
    ticket: Path, session: Callable[..., str]
) -> None:
    assert 'active ticket: demo - Ship demo' in session()


def test_the_ramp_comes_from_the_routing_table(
    ticket: Path, session: Callable[..., str]
) -> None:
    assert 'ramp: game-plan (plan-first true)' in session()


def test_every_role_carries_its_resolved_model(
    ticket: Path, session: Callable[..., str]
) -> None:
    context = session()

    for role in MODEL_ROLES:
        choice = resolve_model(role, 'demo')
        assert f'  {role}: {choice.model} ({choice.source})' in context


def test_one_sprint_status_line_per_brief(
    ticket: Path, session: Callable[..., str]
) -> None:
    for name in ('task-01.md', 'task-02.md'):
        ticket.joinpath('briefs', name).write_text('## ASKED\n', encoding='utf-8')
    context = session()

    assert '  task-01: asked=True done=False' in context
    assert '  task-02: asked=True done=False' in context


def test_the_baton_is_pointed_at_when_it_exists(
    ticket: Path, session: Callable[..., str]
) -> None:
    baton = ticket.joinpath('handoffs', 'BATON.md')
    baton.write_text('# baton\n', encoding='utf-8')

    assert f'baton waiting: read {baton}' in session()


def test_no_baton_pointer_without_the_file(
    ticket: Path, session: Callable[..., str]
) -> None:
    assert 'baton waiting' not in session()


def test_the_ignore_ritual_runs_and_is_reported(
    repo: Path, session: Callable[..., str]
) -> None:
    context = session()

    assert '.mightymodels/ is excluded in .git/info/exclude' in context
    exclude = repo.joinpath('.git', 'info', 'exclude')
    assert '.mightymodels/\n' in exclude.read_text(encoding='utf-8')


def test_the_roster_still_prints_without_a_ticket(
    repo: Path, session: Callable[..., str]
) -> None:
    context = session()

    assert 'active ticket: none' in context
    assert 'tickets on disk: none' in context
    assert 'scout (' in context


def test_the_branch_name_picks_the_active_ticket(
    repo: Path, git: Callable[..., str], session: Callable[..., str]
) -> None:
    make_ticket('alpha', branch='feat/alpha')
    make_ticket('beta', branch='feat/beta')
    commit(git, repo)
    git(repo, 'checkout', '-q', '-b', 'feat/beta')

    assert 'active ticket: beta - Ship beta' in session()


def test_without_a_branch_match_every_slug_is_listed(
    repo: Path, git: Callable[..., str], session: Callable[..., str]
) -> None:
    make_ticket('alpha', branch='feat/alpha')
    make_ticket('beta', branch='feat/beta')
    commit(git, repo)
    context = session()

    assert 'active ticket: none' in context
    assert 'tickets on disk: alpha, beta' in context


def test_the_archives_directory_is_not_a_ticket(
    ticket: Path, repo: Path, session: Callable[..., str]
) -> None:
    archived = repo.joinpath('.mightymodels', 'archives')
    archived.mkdir()
    archived.joinpath('ticket.yml').write_text('task: old\n', encoding='utf-8')

    assert 'active ticket: demo - Ship demo' in session()


def test_the_snapshot_is_injected_verbatim_after_a_compaction(
    ticket: Path, session: Callable[..., str]
) -> None:
    snapshot = 'where we were:\n- the retry test was red\n- the fix is half written'
    ticket.joinpath('snapshot.md').write_text(f'{snapshot}\n', encoding='utf-8')

    assert snapshot in session(source='compact')


def test_the_snapshot_is_left_out_on_a_fresh_session(
    ticket: Path, session: Callable[..., str]
) -> None:
    ticket.joinpath('snapshot.md').write_text('where we were\n', encoding='utf-8')

    assert 'where we were' not in session()


def test_the_injected_context_stays_readable(
    ticket: Path, session: Callable[..., str]
) -> None:
    assert len(session().splitlines()) <= MAX_LINES
