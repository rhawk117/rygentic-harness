import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.types import (
    CallToolResult,
    ReadResourceResult,
    TextResourceContents,
    Tool,
)
from mightymcp.fleet import BUNDLED_PLUGIN_ROOT, load_fleet, plugin_root, render_fleet
from mightymcp.server import server

TOOLS = [
    'fleet_roster',
    'ticket_read',
    'ticket_create',
    'ticket_update_context',
    'resolve_model',
    'route_ramp',
    'route_finding',
    'sprint_status',
]
FLEET = [
    'budgetron',
    'engineer',
    'gitty-up',
    'grumpy',
    'scout',
    'sunny',
    'wingman',
]


@dataclass(frozen=True, slots=True)
class Probe:
    tools: list[Tool]
    roster: CallToolResult
    fleet: ReadResourceResult


async def _probe() -> Probe:
    async with Client(server) as client:
        return Probe(
            tools=(await client.list_tools()).tools,
            roster=await client.call_tool('fleet_roster'),
            fleet=await client.read_resource('mm://fleet'),
        )


@pytest.fixture
def probe() -> Probe:
    return asyncio.run(_probe())


def test_server_exposes_the_roster_and_the_ticket_tools(probe: Probe) -> None:
    assert sorted(tool.name for tool in probe.tools) == sorted(TOOLS)


def test_every_tool_returns_structured_output(probe: Probe) -> None:
    assert all(tool.output_schema is not None for tool in probe.tools)


def test_fleet_roster_returns_every_worker(probe: Probe) -> None:
    assert not probe.roster.is_error
    structured = probe.roster.structured_content
    assert structured is not None

    workers = structured['workers']
    assert [worker['name'] for worker in workers] == FLEET
    assert all(worker['job'] and worker['model'] for worker in workers)


def test_fleet_resource_renders_the_same_roster(probe: Probe) -> None:
    assert len(probe.fleet.contents) == 1
    contents = probe.fleet.contents[0]
    assert isinstance(contents, TextResourceContents)
    assert contents.text == render_fleet(load_fleet())
    assert all(name in contents.text for name in FLEET)


def test_job_is_the_first_sentence_of_the_agent_description() -> None:
    jobs = {worker.name: worker.job for worker in load_fleet().workers}
    assert jobs['scout'] == 'Mechanical retrieval worker.'
    assert jobs['budgetron'] == 'Budgeted single-concern fixer.'


def test_plugin_root_prefers_the_claude_plugin_root_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(tmp_path))
    assert plugin_root() == tmp_path

    monkeypatch.delenv('CLAUDE_PLUGIN_ROOT')
    assert plugin_root() == BUNDLED_PLUGIN_ROOT


def test_agent_file_without_frontmatter_is_rejected(tmp_path: Path) -> None:
    agents = tmp_path.joinpath('agents')
    agents.mkdir()
    agents.joinpath('broken.md').write_text('no frontmatter here\n', encoding='utf-8')

    with pytest.raises(ValueError, match='no YAML frontmatter'):
        load_fleet(tmp_path)


async def _call(name: str, arguments: dict[str, Any]) -> CallToolResult:
    async with Client(server) as client:
        return await client.call_tool(name, arguments)


def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = asyncio.run(_call(name, arguments))
    assert not result.is_error
    assert result.structured_content is not None
    return result.structured_content


def test_a_ticket_round_trips_through_the_client(repo: Path) -> None:
    created = call(
        'ticket_create',
        {
            'slug': 'demo',
            'summary': 'Ship the thing',
            'context': ['one fact', 'two fact', 'three fact'],
            'handoff': {'scope': 'sm', 'plan-first': False, 'branch-name': 'feat/demo'},
        },
    )
    assert created['refusals'] == []

    read = call('ticket_read', {'slug': 'demo'})
    assert read['ticket']['summary'] == 'Ship the thing'
    assert read['ticket']['handoff-context']['scope'] == 'sm'

    status = call('sprint_status', {'slug': 'demo'})
    assert status == {
        'slug': 'demo',
        'tasks': [],
        'unpushed_commits': -1,
        'whats_broken_active': False,
        'report_present': False,
        'refusals': [],
    }


def test_a_path_violation_comes_back_as_a_refusal(repo: Path) -> None:
    refused = call('ticket_read', {'slug': '../evil'})

    assert refused['ticket'] is None
    assert refused['refusals']


def test_the_pure_tools_report_the_rule_that_fired() -> None:
    assert call('route_ramp', {'scope': 'sm', 'plan_first': False})['ramp'] == 'yolo'
    assert call(
        'route_finding',
        {'severity': 'Critical', 'source': 'merge-vader', 'security': False},
    ) == {
        'worker': 'engineer',
        'rule': 'Critical finding',
        'refusals': [],
    }
    assert call('resolve_model', {'role': 'wingman'})['model'] == 'claude-opus-5'
