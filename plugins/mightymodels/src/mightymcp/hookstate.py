import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from mightymcp.paths import MIGHTYMODELS_DIR, TicketPathError, safe_name

STATE_DIR = '.hookstate'


class PendingDispatch(BaseModel):
    """A dispatch the Agent guard allowed, waiting for its subagent to start."""

    role: str = Field(description='The fleet role that was dispatched')
    task_id: str = Field(description='Brief stem the dispatch named, e.g. task-03')


class AgentState(BaseModel):
    """One running subagent: what it is, what it was bound to, what it has spent."""

    role: str = Field(description='The fleet role the subagent runs as')
    task_id: str = Field(default='', description='Brief stem, empty when unbound')
    bash_calls: int = Field(default=0, description='Bash calls seen from this subagent')


class HookState(BaseModel):
    """One session's guard state: dispatches awaiting a subagent, and running agents."""

    pending: list[PendingDispatch] = Field(
        default_factory=list, description='Allowed dispatches, oldest first'
    )
    agents: dict[str, AgentState] = Field(
        default_factory=dict, description='Running subagents, keyed by agent id'
    )


def state_path(root: Path, session_id: str) -> Path | None:
    """Where this session's state lives, or None when the id is not one path segment."""
    try:
        name = safe_name(session_id)
    except TicketPathError:
        return None
    return root.joinpath(MIGHTYMODELS_DIR, STATE_DIR, f'{name}.json')


def read_state(root: Path, session_id: str) -> HookState:
    """Read this session's guard state; anything unreadable reads as empty state."""
    path = state_path(root, session_id)
    if path is None or not path.is_file():
        return HookState()
    try:
        return HookState.model_validate_json(path.read_text(encoding='utf-8'))
    except OSError, ValidationError, json.JSONDecodeError:
        return HookState()


def write_state(root: Path, session_id: str, state: HookState) -> None:
    """Write this session's guard state back, creating .hookstate/ on the way."""
    path = state_path(root, session_id)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(), encoding='utf-8')


def record_pending(root: Path, session_id: str, role: str, task_id: str) -> None:
    """Record an allowed dispatch for the subagent that is about to start."""
    state = read_state(root, session_id)
    state.pending.append(PendingDispatch(role=role, task_id=task_id))
    write_state(root, session_id, state)


def bind_agent(root: Path, session_id: str, agent_id: str, role: str) -> AgentState:
    """Bind a starting subagent to the oldest pending dispatch of its own role."""
    state = read_state(root, session_id)
    pending = next((entry for entry in state.pending if entry.role == role), None)
    if pending is not None:
        state.pending.remove(pending)
    bound = AgentState(role=role, task_id=pending.task_id if pending else '')
    state.agents[agent_id] = bound
    write_state(root, session_id, state)
    return bound


def agent_state(root: Path, session_id: str, agent_id: str) -> AgentState | None:
    """The state of one running subagent, or None when nothing bound it."""
    return read_state(root, session_id).agents.get(agent_id)


def count_bash(root: Path, session_id: str, agent_id: str, role: str) -> int:
    """Count this Bash call against the subagent's budget and return the running total."""
    state = read_state(root, session_id)
    agent = state.agents.setdefault(agent_id, AgentState(role=role))
    agent.bash_calls += 1
    write_state(root, session_id, state)
    return agent.bash_calls
