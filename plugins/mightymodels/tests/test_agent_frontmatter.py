"""The agent files pin the routing table's model and effort, and grant only tools that exist.

Each also declares in its frontmatter the types it may dispatch, its turn ceiling and the skills
it preloads, and holds no key but the ones pinned here.
"""

import re
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels_plugin.commands.dispatch_hook import DISPATCH_RULES, agent_type
from mightymodels_plugin.core.routing import EFFORT, Worker, fixed_model
from mightymodels_plugin.server import SERVER_NAME, TOOLS

AGENTS = Path(__file__).parent.parent.joinpath('agents')
SKILLS = Path(__file__).parent.parent.joinpath('skills')
DISPATCHERS = frozenset(worker for worker, targets in DISPATCH_RULES.items() if targets)
FRONTMATTER = re.compile(r'\A---\n(?P<head>.*?)\n---\n(?P<body>.*)\Z', re.DOTALL)
KEY = re.compile(r'^(?P<key>\w+):', re.MULTILINE)
PIN = re.compile(r'^(?P<key>model|effort|maxTurns): (?P<value>\S+)$', re.MULTILINE)
GRANT = r'\w+(?:\([\w:-]+(?:, [\w:-]+)*\))?'
TOOLS_LINE = re.compile(rf'^tools: (?P<grants>\[\]|{GRANT}(?:, {GRANT})*)$', re.MULTILINE)
TOOL_GRANT = re.compile(r'(?P<name>\w+)(?:\((?P<types>[^)]*)\))?')
AGENT_TYPE = re.compile(r'[\w:-]+')
STATE_TOOL = re.compile(r'\bmcp__\w+')
PRELOADED_SKILLS = re.compile(r'^skills:(?P<names>.*(?:\n[ \t]*- .*)*)$', re.MULTILINE)
SKILL_NAME = re.compile(r'\w[\w-]*')
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
    keys: frozenset[str]
    pins: dict[str, str]
    tools: tuple[str, ...]
    dispatch_targets: tuple[str, ...]
    state_tools: tuple[str, ...]
    skills: tuple[str, ...]
    body: str


def preloaded_skills(head: str) -> tuple[str, ...]:
    found = PRELOADED_SKILLS.search(head)
    return tuple(SKILL_NAME.findall(found['names'])) if found else ()


def dispatch_targets(grants: str) -> tuple[str, ...]:
    listed = (
        grant['types'] or '' for grant in TOOL_GRANT.finditer(grants) if grant['name'] == 'Agent'
    )
    return tuple(chain.from_iterable(map(AGENT_TYPE.findall, listed)))


def agent_file(path: Path) -> AgentFile:
    parts = FRONTMATTER.match(path.read_text(encoding='utf-8'))
    assert parts is not None, path.name
    pins = {found['key']: found['value'] for found in PIN.finditer(parts['head'])}
    tools = TOOLS_LINE.search(parts['head'])
    assert tools is not None, path.name
    return AgentFile(
        worker=Worker(path.stem),
        keys=frozenset(found['key'] for found in KEY.finditer(parts['head'])),
        pins=pins,
        tools=tuple(grant['name'] for grant in TOOL_GRANT.finditer(tools['grants'])),
        dispatch_targets=dispatch_targets(tools['grants']),
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


class TestToolsOfTheAgents:
    HELD = MappingProxyType({agent.worker: agent.tools for agent in TestAgentFiles.AGENT_FILES})

    def test_wingman_holds_an_empty_tools_list(self) -> None:
        assert self.HELD[Worker.WINGMAN] == ()

    def test_web_scout_holds_no_shell(self) -> None:
        assert 'Bash' not in self.HELD[Worker.WEB_SCOUT]


class TestStateToolsOfTheAgents:
    REGISTERED = frozenset(
        f'mcp__plugin_mightymodels_{SERVER_NAME}__{tool.__name__}' for tool in TOOLS
    )

    @pytest.mark.parametrize(
        'agent',
        [pytest.param(agent, id=agent.worker.value) for agent in TestAgentFiles.AGENT_FILES],
    )
    def test_every_state_tool_grant_names_a_tool_the_server_registers(
        self, agent: AgentFile
    ) -> None:
        assert [grant for grant in agent.state_tools if grant not in self.REGISTERED] == []


class TestSkillsOfTheAgents:
    PRELOADED = MappingProxyType(
        {agent.worker: agent.skills for agent in TestAgentFiles.AGENT_FILES}
    )

    def test_the_engineer_preloads_agent_debugging_and_prompting_subagents(self) -> None:
        assert self.PRELOADED[Worker.ENGINEER] == ('agent-debugging', 'prompting-subagents')

    def test_exactly_the_workers_that_dispatch_preload_prompting_subagents(self) -> None:
        preloading = {
            worker for worker, skills in self.PRELOADED.items() if 'prompting-subagents' in skills
        }

        assert preloading == DISPATCHERS

    def test_every_preloaded_skill_is_a_skill_directory(self) -> None:
        preloaded = chain.from_iterable(self.PRELOADED.values())

        assert [name for name in preloaded if not SKILLS.joinpath(name, 'SKILL.md').is_file()] == []


class TestPreloadedSkills:
    NAMED = ('agent-debugging', 'prompting-subagents')

    @pytest.mark.parametrize(
        'head',
        [
            pytest.param(
                'tools: []\nskills: [agent-debugging, prompting-subagents]\nmodel: sonnet',
                id='one-line-list',
            ),
            pytest.param(
                'tools: []\nskills:\n  - agent-debugging\n  - prompting-subagents\nmodel: sonnet',
                id='block-list',
            ),
            pytest.param(
                'tools: []\nskills:\n- agent-debugging\n- prompting-subagents\nmodel: sonnet',
                id='block-list-without-indent',
            ),
        ],
    )
    def test_a_one_line_list_and_a_block_list_name_the_same_skills(self, head: str) -> None:
        assert preloaded_skills(head) == self.NAMED

    def test_a_head_without_skills_preloads_nothing(self) -> None:
        assert preloaded_skills('tools: []\nmodel: fable') == ()


class TestDispatchTargetsOfTheAgents:
    @pytest.mark.parametrize(
        'agent',
        [pytest.param(agent, id=agent.worker.value) for agent in TestAgentFiles.AGENT_FILES],
    )
    def test_the_types_listed_in_agent_are_the_dispatch_row_of_the_worker(
        self, agent: AgentFile
    ) -> None:
        row = DISPATCH_RULES[agent.worker]

        assert sorted(agent.dispatch_targets) == sorted(map(agent_type, row))

    def test_exactly_the_workers_that_dispatch_hold_agent(self) -> None:
        holding = {agent.worker for agent in TestAgentFiles.AGENT_FILES if 'Agent' in agent.tools}

        assert holding == DISPATCHERS


class TestTurnCeilingsOfTheAgents:
    CEILINGS = MappingProxyType(
        {Worker.CODE_SCOUT: '10', Worker.WEB_SCOUT: '10', Worker.QUALITYLENS: '10'}
    )

    def test_exactly_the_retrieval_workers_stop_at_ten_turns(self) -> None:
        ceilings = {
            agent.worker: agent.pins['maxTurns']
            for agent in TestAgentFiles.AGENT_FILES
            if 'maxTurns' in agent.pins
        }

        assert ceilings == self.CEILINGS


class TestKeysOfTheAgents:
    SHARED = frozenset({'name', 'tools', 'model', 'effort', 'description'})
    RETRIEVAL = SHARED.union({'maxTurns'})
    DISPATCHER = SHARED.union({'skills'})
    KEYS = MappingProxyType(
        {
            Worker.CODE_SCOUT: RETRIEVAL,
            Worker.WEB_SCOUT: RETRIEVAL,
            Worker.QUALITYLENS: RETRIEVAL,
            Worker.ENGINEER: DISPATCHER,
            Worker.ARCHITECT: DISPATCHER,
            Worker.GITTY_UP: SHARED,
            Worker.WINGMAN: SHARED,
            Worker.MERGE_VADER: DISPATCHER,
            Worker.UNCLE_BOB: DISPATCHER,
        }
    )

    @pytest.mark.parametrize(
        'agent',
        [pytest.param(agent, id=agent.worker.value) for agent in TestAgentFiles.AGENT_FILES],
    )
    def test_the_frontmatter_holds_exactly_the_keys_pinned_for_the_worker(
        self, agent: AgentFile
    ) -> None:
        assert agent.keys == self.KEYS[agent.worker]
