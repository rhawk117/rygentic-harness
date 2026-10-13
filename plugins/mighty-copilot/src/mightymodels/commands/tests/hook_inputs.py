import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from mightymodels.cli import main

SKIPPED = 'mightymodels hook did nothing: '
REPORT = '<report><verdict>VERIFIED</verdict><findings>the drain loop sleeps</findings></report>'
PLUGIN = 'mightymodels'
OTHER_AGENTS = (
    'mightymodels:review:qualitylens',
    'mightymodels:triage:wingman',
    f'{PLUGIN}:code-scout',
    f'{PLUGIN}:engineer',
    'mightymodels:workers:code-scout',
    'mightymodels:triage:engineer',
    'code-scout',
    'engineer',
    'other:engineer',
    'general-purpose',
    '',
)
ENGINEER = 'mightymodels:workers:engineer'
MAIN_THREAD_CALLERS = (
    pytest.param({}, id='no-agent-type'),
    pytest.param({'agent_type': 7}, id='agent-type-a-number'),
    pytest.param({'agent_type': None}, id='agent-type-null'),
    pytest.param({'agent_type': [ENGINEER]}, id='agent-type-a-list'),
    pytest.param({'agent_type': {'name': ENGINEER}}, id='agent-type-an-object'),
    pytest.param({'agent_type': ''}, id='agent-type-empty'),
    pytest.param({'agent_type': 'general-purpose'}, id='built-in'),
    pytest.param({'agent_type': 'other:engineer'}, id='another-plugins-agent'),
)
ENGINEER_STOP_HOLDING = '{{"agent_type": "mightymodels:workers:engineer", "elapsed": {value}}}'
UNREADABLE_INPUTS = (
    pytest.param('', id='empty'),
    pytest.param('not json', id='not-json'),
    pytest.param('[]', id='not-an-object'),
    pytest.param(ENGINEER_STOP_HOLDING.format(value='NaN'), id='nan'),
    pytest.param(ENGINEER_STOP_HOLDING.format(value='Infinity'), id='infinity'),
    pytest.param(ENGINEER_STOP_HOLDING.format(value='1e400'), id='number-out-of-range'),
    pytest.param(ENGINEER_STOP_HOLDING.format(value='"\\ud800"'), id='escaped-lone-surrogate'),
    pytest.param(ENGINEER_STOP_HOLDING.format(value='"\ud800"'), id='raw-lone-surrogate'),
)


def hook_input(event: str, agent_type: str | None = None, **given: object) -> str:
    fields = {'hook_event_name': event, 'session_id': 's1'}
    return json.dumps(fields | ({} if agent_type is None else {'agent_type': agent_type}) | given)


def scout_stop(agent_type: str = 'mightymodels:triage:code-scout', **given: object) -> str:
    stop = {'agent_id': 'a1b2', 'stop_hook_active': False, 'last_assistant_message': REPORT}
    return hook_input('SubagentStop', agent_type, **(stop | given))


def implementer_stop(agent_type: str = 'mightymodels:workers:engineer', **given: object) -> str:
    stop = {'stop_hook_active': False, 'last_assistant_message': 'done'}
    return hook_input('SubagentStop', agent_type, **(stop | given))


def dispatch(target: str, agent_type: str | None = None) -> str:
    return hook_input(
        'PreToolUse', agent_type, tool_name='Agent', tool_input={'subagent_type': target}
    )


def tool_call(tool: str, agent_type: str | None = None, **tool_input: object) -> str:
    return hook_input('PreToolUse', agent_type, tool_name=tool, tool_input=tool_input)


@dataclass(slots=True, kw_only=True, frozen=True)
class Hook:
    repository: Path
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]

    def run(self, command: str, text: str) -> tuple[int, str, str]:
        self.monkeypatch.setattr(sys, 'stdin', io.StringIO(text))
        code = main([command])
        captured = self.capsys.readouterr()
        return code, captured.out, captured.err
