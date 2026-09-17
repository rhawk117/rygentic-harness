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
    'brief_open',
    'brief_append_done',
    'brief_read',
    'task_record_attempt',
    'report_write',
    'checklist_render',
    'whats_broken_write',
    'whats_broken_close',
    'handoff_write',
    'handoff_prompt',
    'decision_record',
    'parse_report',
    'findings_merge',
    'review_verdict',
    'review_report_write',
    'grade_compute',
    'blast_radius_questions',
    'pr_comment_render',
    'dialectic_score',
    'dialectic_record_write',
    'crashout_add',
    'crashout_stats',
    'crashout_last',
    'metrics_run',
    'ticket_prunable',
    'ticket_archive',
    'ticket_delete',
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


def test_every_workflow_tool_carries_a_refusals_list(probe: Probe) -> None:
    schemas = {
        tool.name: tool.output_schema or {}
        for tool in probe.tools
        if tool.name != 'fleet_roster'
    }

    assert sorted(schemas) == sorted(name for name in TOOLS if name != 'fleet_roster')
    assert all(
        schema['properties']['refusals']['type'] == 'array' for schema in schemas.values()
    )


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


def test_a_plugin_root_without_an_agents_directory_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(tmp_path))

    with pytest.raises(ValueError, match=str(tmp_path)):
        load_fleet()


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


def test_a_brief_round_trips_through_the_client(ticket_root: Path) -> None:
    stanza = {
        'objective': 'Ship the thing',
        'acceptance': ['AC-1: `uv run pytest -q` passes'],
        'verification': '`uv run pytest -q`',
        'files-in-scope': ['src/demo.py'],
        'engineer-tier': 'claude-sonnet-5',
    }
    opened = call(
        'brief_open',
        {
            'slug': 'demo',
            'task_id': 'task-01',
            'asked': stanza,
            'commit_message': 'feat(demo): ship it [#7]',
        },
    )
    assert opened['refusals'] == []
    assert 'feat(demo): ship it [#7]' in opened['dispatch']

    read = call('brief_read', {'slug': 'demo', 'task_id': 'task-01'})
    assert read['asked']['files-in-scope'] == ['src/demo.py']
    assert read['done'] is None
    assert not read['verified']


def test_a_placeholder_criterion_comes_back_as_a_refusal(ticket_root: Path) -> None:
    refused = call(
        'brief_open',
        {
            'slug': 'demo',
            'task_id': 'task-01',
            'asked': {
                'objective': 'Ship the thing',
                'acceptance': ['AC-1: it works correctly'],
                'verification': '`uv run pytest -q`',
                'files-in-scope': ['src/demo.py'],
                'engineer-tier': 'claude-sonnet-5',
            },
            'commit_message': 'feat(demo): ship it [#7]',
        },
    )

    assert refused['path'] is None
    assert 'is a placeholder' in refused['refusals'][0]
    assert not ticket_root.joinpath('briefs', 'task-01.md').exists()


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


def test_a_worker_report_parses_through_the_client() -> None:
    parsed = call(
        'parse_report',
        {
            'role': 'gitty-up',
            'text': (
                '<report agent="ci-watcher" pr="214"><verdict>fail</verdict>'
                '<confidence>high</confidence></report>'
            ),
        },
    )

    assert parsed['refusals'] == []
    assert (parsed['verdict'], parsed['stop'], parsed['subject']) == ('fail', True, '214')


def test_the_review_and_dialectic_tools_take_their_models_through_the_client() -> None:
    verdict = call(
        'review_verdict',
        {
            'findings': [
                {
                    'id': 'UB-1',
                    'severity': 'Blocker',
                    'file': 'src/api/limits.py',
                    'line': '17',
                    'source': 'uncle-bob',
                    'summary': 'a dependency cycle',
                }
            ],
            'security_unknown_blocked': False,
        },
    )
    decided = call(
        'dialectic_score',
        {'options': [{'name': 'A', 'worst': 'High'}, {'name': 'B'}]},
    )

    assert verdict['verdict'] == 'BLOCK'
    assert (decided['winner'], decided['rung']) == ('B', 1)


def test_a_ticket_is_closed_out_through_the_client(ticket_root: Path) -> None:
    assert call('ticket_prunable', {'slug': 'demo'})['prunable']

    archived = call(
        'ticket_archive',
        {'slug': 'demo', 'body': '# demo\nshipped: the retry cap · PR: #12\n'},
    )
    assert archived['refusals'] == []

    deleted = call('ticket_delete', {'slug': 'demo', 'accept_skipped': True})
    assert deleted['refusals'] == []
    assert not ticket_root.exists()
