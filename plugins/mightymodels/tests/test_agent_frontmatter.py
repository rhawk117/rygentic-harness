"""The agent files pin the model and effort the routing table fixes for them."""

import re
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels_plugin.core.routing import EFFORT, Worker, fixed_model

AGENTS = Path(__file__).parent.parent.joinpath('agents')
SKILLS = Path(__file__).parent.parent.joinpath('skills')
FRONTMATTER = re.compile(r'\A---\n(?P<head>.*?)\n---\n(?P<body>.*)\Z', re.DOTALL)
PIN = re.compile(r'^(?P<key>model|effort): (?P<value>\S+)$', re.MULTILINE)
STATE_TOOL = re.compile(r'\bmcp__\w+')
PRELOADED_SKILLS = re.compile(r'^skills: (?P<names>.+)$', re.MULTILINE)
SKILL_NAME = re.compile(r'[\w-]+')
FORBIDDEN_PHRASES = (
    re.compile(r'\b(call|use) no tools?\b', re.IGNORECASE),
    re.compile(r'\bno tools?\b(?!\))', re.IGNORECASE),
    re.compile(r'\b(do not|don\'t|never) (call|use) (any )?tools?\b', re.IGNORECASE),
    re.compile(r'\bwithout (calling|using) (any )?tools?\b', re.IGNORECASE),
    re.compile(r'\b(plain|raw) text only\b', re.IGNORECASE),
    re.compile(r'\b(reply|respond|answer) (with|in) (plain )?text only\b', re.IGNORECASE),
    re.compile(r'\bonly (reply|respond) with\b', re.IGNORECASE),
)


@dataclass(slots=True, kw_only=True, frozen=True)
class AgentFile:
    worker: Worker
    pins: dict[str, str]
    state_tools: tuple[str, ...]
    skills: tuple[str, ...]
    body: str


def preloaded_skills(head: str) -> tuple[str, ...]:
    found = PRELOADED_SKILLS.search(head)
    return tuple(SKILL_NAME.findall(found['names'])) if found else ()


def agent_file(path: Path) -> AgentFile:
    parts = FRONTMATTER.match(path.read_text(encoding='utf-8'))
    assert parts is not None, path.name
    pins = {found['key']: found['value'] for found in PIN.finditer(parts['head'])}
    return AgentFile(
        worker=Worker(path.stem),
        pins=pins,
        state_tools=tuple(STATE_TOOL.findall(parts['head'])),
        skills=preloaded_skills(parts['head']),
        body=parts['body'],
    )


class TestAgentFiles:
    AGENT_FILES = tuple(map(agent_file, sorted(AGENTS.glob('*/*.md'))))

    def test_every_worker_has_one_agent_file(self) -> None:
        assert {agent.worker for agent in self.AGENT_FILES} == set(Worker)

    @pytest.mark.parametrize(
        'agent', [pytest.param(agent, id=agent.worker.value) for agent in AGENT_FILES]
    )
    def test_the_model_is_the_one_routing_fixes(self, agent: AgentFile) -> None:
        assert agent.pins['model'] == fixed_model(agent.worker)

    @pytest.mark.parametrize(
        'agent', [pytest.param(agent, id=agent.worker.value) for agent in AGENT_FILES]
    )
    def test_the_effort_is_the_pin_of_the_tier(self, agent: AgentFile) -> None:
        assert agent.pins['effort'] == EFFORT[fixed_model(agent.worker)]

    @pytest.mark.parametrize(
        'agent', [pytest.param(agent, id=agent.worker.value) for agent in AGENT_FILES]
    )
    def test_the_body_neither_forbids_tool_calls_nor_asks_for_plain_text_only(
        self, agent: AgentFile
    ) -> None:
        found = [phrase.pattern for phrase in FORBIDDEN_PHRASES if phrase.search(agent.body)]

        assert found == []


class TestStateToolsOfTheAgents:
    NAMED = MappingProxyType(
        {
            Worker.ENGINEER: ('mcp__plugin_mightymodels_state__failed_fix',),
            Worker.WINGMAN: ('mcp__plugin_mightymodels_state__ticket',),
        }
    )

    def test_the_engineer_names_the_failed_fix_tool_and_no_other_agent_names_the_task_tool(
        self,
    ) -> None:
        named = {agent.worker: agent.state_tools for agent in TestAgentFiles.AGENT_FILES}

        assert {worker: tools for worker, tools in named.items() if tools} == self.NAMED


class TestSkillsOfTheAgents:
    PRELOADED = MappingProxyType(
        {agent.worker: agent.skills for agent in TestAgentFiles.AGENT_FILES}
    )

    def test_the_engineer_preloads_agent_debugging(self) -> None:
        assert self.PRELOADED[Worker.ENGINEER] == ('agent-debugging',)

    def test_every_preloaded_skill_is_a_skill_directory(self) -> None:
        preloaded = chain.from_iterable(self.PRELOADED.values())

        assert [name for name in preloaded if not SKILLS.joinpath(name, 'SKILL.md').is_file()] == []
