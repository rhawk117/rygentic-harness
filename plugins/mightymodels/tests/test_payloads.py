from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

PAYLOADS = Path(__file__).parent.joinpath('payloads')

COMMON = ['session_id', 'cwd', 'hook_event_name', 'transcript_path', 'permission_mode']
NAMES = [
    'SessionStart-startup',
    'SessionStart-resume',
    'SessionStart-compact',
    'SubagentStart',
    'SubagentStop',
    'PreToolUse-Agent',
    'PreToolUse-Write',
    'PreToolUse-Edit',
    'PreToolUse-Bash',
    'PostToolUse-Bash',
    'PreCompact',
    'Stop',
]
PRE_TOOL_USE = [name for name in NAMES if name.startswith('PreToolUse-')]

Load = Callable[[str], dict[str, Any]]


def test_the_payload_directory_holds_exactly_the_named_fixtures() -> None:
    assert sorted(path.name for path in PAYLOADS.iterdir()) == sorted(
        f'{name}.json' for name in NAMES
    )


@pytest.mark.parametrize('name', NAMES)
def test_every_fixture_carries_the_common_fields(name: str, payload: Load) -> None:
    assert [key for key in COMMON if key not in payload(name)] == []


@pytest.mark.parametrize('name', NAMES)
def test_the_event_name_matches_the_fixture_name(name: str, payload: Load) -> None:
    assert payload(name)['hook_event_name'] == name.split('-', maxsplit=1)[0]


@pytest.mark.parametrize('source', ['startup', 'resume', 'compact'])
def test_each_session_start_fixture_carries_its_source(
    source: str, payload: Load
) -> None:
    assert payload(f'SessionStart-{source}')['source'] == source


def test_subagent_start_carries_the_agent_type_and_id(payload: Load) -> None:
    started = payload('SubagentStart')

    assert started['agent_type'] == 'scout'
    assert started['agent_id']


def test_subagent_stop_carries_the_agent_and_its_last_message(payload: Load) -> None:
    stopped = payload('SubagentStop')

    assert stopped['stop_hook_active'] is False
    assert stopped['agent_id'] == 'agent_01J8QK3P7N'
    assert stopped['agent_transcript_path'].endswith('.jsonl')
    assert stopped['agent_type'] == 'scout'
    assert stopped['last_assistant_message']


@pytest.mark.parametrize('name', PRE_TOOL_USE)
def test_every_pre_tool_use_fixture_carries_its_tool(name: str, payload: Load) -> None:
    hook = payload(name)

    assert hook['tool_name'] == name.removeprefix('PreToolUse-')
    assert isinstance(hook['tool_input'], dict)
    assert hook['tool_input']


def test_post_tool_use_carries_the_tool_response(payload: Load) -> None:
    hook = payload('PostToolUse-Bash')

    assert hook['tool_name'] == 'Bash'
    assert hook['tool_input']['command']
    assert hook['tool_response']['stdout']


def test_pre_compact_carries_its_trigger(payload: Load) -> None:
    assert payload('PreCompact')['trigger'] == 'auto'


def test_stop_carries_the_stop_hook_active_guard(payload: Load) -> None:
    assert payload('Stop')['stop_hook_active'] is False
