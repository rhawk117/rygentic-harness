import asyncio
from dataclasses import dataclass
from pathlib import Path

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


def test_server_exposes_only_fleet_roster(probe: Probe) -> None:
    assert [tool.name for tool in probe.tools] == ['fleet_roster']
    assert probe.tools[0].output_schema is not None


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
