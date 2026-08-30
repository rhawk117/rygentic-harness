"""The portable instrumentation layer: one normalized event log, two hosts.

Claude Code and Copilot both support hooks that hand a JSON payload to a command.
That is the only instrumentation channel both hosts share, and it is ground truth
rather than inference — which is why everything downstream reads this log and
nothing parses a transcript or scrapes stdout.

skill-creator infers triggering from the *first* streamed tool block, so a session
that opens with a todo list is scored as "did not trigger". Reading an event log
removes both the ordering assumption and the parsing.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ENV_LOG = 'SKILLENG_EVENT_LOG'
ENV_RUN = 'SKILLENG_RUN_ID'
ENV_ARM = 'SKILLENG_ARM'

# Emitted in place of a lost event — a write that failed, or a log line that could
# not be decoded — so a reader can tell "the log lost something" from "nothing
# happened", instead of scoring the loss as a non-trigger.
EVENT_INSTRUMENTATION_ERROR = 'instrumentation_error'

# Hosts spell the same concepts differently and the spellings are not fully
# documented, so every lookup tries a list of candidates and records what it saw.
_EVENT_KEYS = ('hook_event_name', 'hookEventName', 'event', 'eventName', 'type', 'hook')
_TOOL_KEYS = ('tool_name', 'toolName', 'tool', 'name')
_INPUT_KEYS = (
    'tool_input',
    'toolInput',
    'toolArgs',
    'tool_args',
    'arguments',
    'args',
    'input',
    'parameters',
)
_SESSION_KEYS = ('session_id', 'sessionId', 'conversation_id', 'conversationId', 'id')

_SKILL_TOOLS = {'skill', 'skills', 'invokeskill', 'use_skill', 'useskill'}
_SKILL_NAME_KEYS = ('skill', 'skill_name', 'skillName', 'name', 'command')
_SKILL_PATH_RE = re.compile(r'skills/([A-Za-z0-9._-]+)/SKILL\.md')
_SLASH_RE = re.compile(r'(?:\A|\s)/([a-z0-9][a-z0-9-]*)\b')


def _norm_event(value: str) -> str:
    """PreToolUse | preToolUse | pre_tool_use -> pre_tool_use."""
    s = re.sub(r'(?<!^)(?=[A-Z])', '_', str(value)).replace('-', '_').replace('.', '_')
    return re.sub(r'_+', '_', s).strip('_').lower()


def _first(payload: dict, keys: Iterable[str]) -> Any:
    for k in keys:
        if k in payload and payload[k] not in (None, ''):
            return payload[k]
    return None


@dataclass
class Event:
    ts: str
    event: str
    run_id: str | None = None
    arm: str | None = None
    session_id: str | None = None
    tool: str | None = None
    skill: str | None = None
    ok: bool | None = None
    detail: str | None = None
    unmapped: bool = False
    raw_keys: list[str] = field(default_factory=list)


def normalize(payload: dict, run_id: str | None = None, arm: str | None = None) -> Event:
    """Map a host hook payload onto the shared event shape.

    Anything unrecognised is kept as `unmapped=True` with its key list, so
    `skilleng doctor --probe-hooks` can report an adapter mismatch instead of
    letting a whole eval silently score as "never triggered".
    """
    raw_event = _first(payload, _EVENT_KEYS)
    tool = _first(payload, _TOOL_KEYS)
    tool_input = _first(payload, _INPUT_KEYS)
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError:
            tool_input = {'_raw': tool_input}
    if not isinstance(tool_input, dict):
        tool_input = {}

    skill = None
    if tool and str(tool).lower().replace('_', '') in _SKILL_TOOLS:
        for k in _SKILL_NAME_KEYS:
            if isinstance(tool_input.get(k), str) and tool_input[k].strip():
                skill = tool_input[k].strip().lstrip('/')
                break
        skill = skill or '<unnamed>'
    else:
        blob = json.dumps(tool_input) if tool_input else ''
        m = _SKILL_PATH_RE.search(blob)
        if m:
            skill = m.group(1)

    ev = Event(
        ts=datetime.now(UTC).isoformat(timespec='milliseconds'),
        event=_norm_event(raw_event) if raw_event else 'unknown',
        run_id=run_id or payload.get('run_id') or os.environ.get(ENV_RUN),
        arm=arm or payload.get('arm') or os.environ.get(ENV_ARM),
        session_id=_first(payload, _SESSION_KEYS),
        tool=str(tool) if tool else None,
        skill=skill,
        raw_keys=sorted(payload.keys()),
    )
    if ev.event == 'unknown':
        ev.unmapped = True
        ev.detail = 'no recognised event key in payload'
    return ev


def append(path: Path, ev: Event) -> None:
    """Append one event. Instrumentation must never break the run it observes.

    A write that fails is not lost without a trace: skill_invoked must be able to
    tell "no signal" from "signal was lost", so a sentinel event replaces the one
    that failed to write, as long as the log is reachable at all.
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(asdict(ev), separators=(',', ':')) + '\n')
    except OSError as error:
        sentinel = Event(
            ts=datetime.now(UTC).isoformat(timespec='milliseconds'),
            event=EVENT_INSTRUMENTATION_ERROR,
            run_id=ev.run_id,
            arm=ev.arm,
            detail=str(error),
        )
        try:
            with path.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(asdict(sentinel), separators=(',', ':')) + '\n')
        except OSError:
            pass


def read(path: Path) -> list[Event]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[Event] = []
    undecodable = 0
    for raw_line in p.read_text(encoding='utf-8', errors='replace').splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            out.append(Event(**json.loads(stripped)))
        except json.JSONDecodeError:
            undecodable += 1
        except TypeError:
            undecodable += 1
    if undecodable:
        out.append(
            Event(
                ts=datetime.now(UTC).isoformat(timespec='milliseconds'),
                event=EVENT_INSTRUMENTATION_ERROR,
                detail=f'{undecodable} log line(s) could not be decoded',
            )
        )
    return out


def events_for(events: list[Event], run_id: str) -> list[Event]:
    return [e for e in events if e.run_id == run_id]


def skill_invoked(events: list[Event], run_id: str, skill_name: str) -> bool | None:
    """Did this run invoke this skill?

    Returns None when the run produced no events at all, when the log lost data
    that could belong to this run (a write-failure sentinel or an undecodable
    line), or when every skill-tool invocation seen had no parseable name.
    "not known" is not the same answer as "did not trigger", and conflating them
    is how an eval set scores 9/20 against a completely dead harness — or how an
    unparseable name silently counts as a hit for whatever skill is being asked
    about.
    """
    mine = events_for(events, run_id)
    if not mine:
        return None
    target = skill_name.strip().lower()
    skill_names = [e.skill.strip().lower() for e in mine if e.skill]
    if target in skill_names:
        return True
    if skill_names and all(name == '<unnamed>' for name in skill_names):
        return None
    if any(
        e.event == EVENT_INSTRUMENTATION_ERROR and e.run_id in (None, run_id)
        for e in events
    ):
        return None
    return False


def tool_calls(events: list[Event], run_id: str) -> int:
    return sum(1 for e in events_for(events, run_id) if e.event == 'pre_tool_use')


def prompt_mentions_skill(prompt: str, skill_name: str) -> bool:
    """Whether a prompt explicitly names the skill — used to validate arm hygiene.

    An `available` arm whose prompt names the skill is really a `forced` arm and
    the trigger number it produces is meaningless.
    """
    low = prompt.lower()
    if skill_name.lower() in low:
        return True
    return any(m.group(1) == skill_name.lower() for m in _SLASH_RE.finditer(low))
