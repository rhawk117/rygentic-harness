from pathlib import Path

import pytest
from mightymcp.hookstate import (
    agent_state,
    bind_agent,
    count_bash,
    read_state,
    record_pending,
    state_path,
)

SESSION = '0f9c1c8a-3f5e-4b2a-9e61-7a5f6c3d1b20'


def test_a_session_with_no_state_reads_as_empty(repo: Path) -> None:
    state = read_state(repo, SESSION)

    assert state.pending == []
    assert state.agents == {}


def test_a_dispatch_survives_the_round_trip(repo: Path) -> None:
    record_pending(repo, SESSION, 'engineer', 'task-03')
    state = read_state(repo, SESSION)

    assert state.pending[0].role == 'engineer'
    assert state.pending[0].task_id == 'task-03'


def test_the_state_file_lives_under_the_ticket_directory(repo: Path) -> None:
    record_pending(repo, SESSION, 'engineer', 'task-03')
    path = state_path(repo, SESSION)

    assert path is not None
    assert path == repo.joinpath('.mightymodels', '.hookstate', f'{SESSION}.json')
    assert path.is_file()


def test_unreadable_state_reads_as_empty(repo: Path) -> None:
    record_pending(repo, SESSION, 'engineer', 'task-03')
    path = state_path(repo, SESSION)
    assert path is not None
    path.write_text('{not json at all', encoding='utf-8')

    assert read_state(repo, SESSION).pending == []


@pytest.mark.parametrize('session_id', ['../escape', 'a/b', ''])
def test_a_session_id_that_is_not_a_file_name_is_refused(
    session_id: str, repo: Path
) -> None:
    record_pending(repo, session_id, 'engineer', 'task-03')

    assert state_path(repo, session_id) is None
    assert read_state(repo, session_id).pending == []


def test_binding_without_a_pending_dispatch_leaves_the_agent_unbound(
    repo: Path,
) -> None:
    bound = bind_agent(repo, SESSION, 'agent_01', 'scout')

    assert bound.task_id == ''
    assert agent_state(repo, SESSION, 'agent_01') == bound


def test_binding_consumes_the_oldest_dispatch_of_that_role(repo: Path) -> None:
    record_pending(repo, SESSION, 'scout', 'task-03')
    record_pending(repo, SESSION, 'engineer', 'task-04')
    record_pending(repo, SESSION, 'scout', 'task-05')
    bound = bind_agent(repo, SESSION, 'agent_01', 'scout')

    assert bound.task_id == 'task-03'
    assert [entry.task_id for entry in read_state(repo, SESSION).pending] == [
        'task-04',
        'task-05',
    ]


def test_an_unknown_agent_has_no_state(repo: Path) -> None:
    assert agent_state(repo, SESSION, 'agent_99') is None


def test_bash_calls_are_counted_per_agent(repo: Path) -> None:
    counts = [count_bash(repo, SESSION, 'agent_01', 'scout') for _ in range(3)]

    assert counts == [1, 2, 3]
    assert count_bash(repo, SESSION, 'agent_02', 'scout') == 1


def test_counting_keeps_what_the_binding_recorded(repo: Path) -> None:
    record_pending(repo, SESSION, 'engineer', 'task-03')
    bind_agent(repo, SESSION, 'agent_01', 'engineer')
    count_bash(repo, SESSION, 'agent_01', 'engineer')
    state = agent_state(repo, SESSION, 'agent_01')

    assert state is not None
    assert state.task_id == 'task-03'
    assert state.bash_calls == 1
