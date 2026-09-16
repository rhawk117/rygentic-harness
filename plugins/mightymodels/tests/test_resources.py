import asyncio
from pathlib import Path

import pytest
from mcp import Client, MCPError
from mcp.types import Resource, ResourceTemplate, TextResourceContents
from mightymcp.brief import AskedStanza, render_asked
from mightymcp.fleet import plugin_root
from mightymcp.paths import ACTIVE_TICKET_VAR
from mightymcp.resources import BRIEF_URI, ENGINEER_URI, STATUS_URI, TICKET_URI
from mightymcp.server import server

REFS = [
    'agents-assemble/contracts',
    'merge-vader/dimensions',
    'merge-vader/report-template',
    'merge-vader/scout',
    'prepare-handoff/mightymodels-dir',
    'prepare-handoff/ticket-schema',
    'promptlint/claude-code',
    'promptlint/copilot',
    'promptlint/snippets',
    'uncle-bob/clean-code',
    'uncle-bob/components',
    'uncle-bob/report',
    'uncle-bob/solid',
]
AGENTS = [
    'budgetron',
    'engineer',
    'gitty-up',
    'grumpy',
    'scout',
    'sunny',
    'wingman',
]
ROLES = ['budgetron', 'engineer', 'reviewer', 'scout']
STANZA = AskedStanza(
    objective='Ship the thing',
    acceptance=['AC-1: `uv run pytest -q` passes'],
    verification='`uv run pytest -q`',
    files_in_scope=['src/demo.py'],
    engineer_tier='claude-sonnet-5',
)


async def _resources() -> tuple[list[Resource], list[ResourceTemplate]]:
    async with Client(server) as client:
        listed = await client.list_resources()
        templated = await client.list_resource_templates()
        return listed.resources, templated.resource_templates


async def _read(uri: str) -> str:
    async with Client(server) as client:
        contents = (await client.read_resource(uri)).contents[0]
    assert isinstance(contents, TextResourceContents)
    return contents.text


def read(uri: str) -> str:
    return asyncio.run(_read(uri))


async def _read_error(uri: str) -> str:
    async with Client(server) as client:
        with pytest.raises(MCPError) as caught:
            await client.read_resource(uri)
    return str(caught.value)


def read_error(uri: str) -> str:
    return asyncio.run(_read_error(uri))


@pytest.fixture
def listing() -> tuple[list[Resource], list[ResourceTemplate]]:
    return asyncio.run(_resources())


@pytest.fixture
def sprint(ticket_root: Path) -> Path:
    """A repository whose single ticket carries one brief with an ASKED half."""
    ticket_root.joinpath('ticket.yml').write_text('task: demo\n', encoding='utf-8')
    ticket_root.joinpath('briefs', 'task-01.md').write_text(
        render_asked(STANZA), encoding='utf-8'
    )
    return ticket_root


def test_every_skill_reference_is_served_as_markdown(
    listing: tuple[list[Resource], list[ResourceTemplate]],
) -> None:
    refs = {
        resource.uri: resource
        for resource in listing[0]
        if resource.uri.startswith('mm://ref/')
    }

    assert sorted(refs) == [f'mm://ref/{name}' for name in REFS]
    assert all(refs[uri].name == uri.removeprefix('mm://') for uri in refs)
    assert all(resource.mime_type == 'text/markdown' for resource in refs.values())


def test_every_agent_and_role_template_is_served(
    listing: tuple[list[Resource], list[ResourceTemplate]],
) -> None:
    uris = {resource.uri for resource in listing[0]}

    assert {f'mm://agent/{name}' for name in AGENTS} <= uris
    assert {f'mm://template/{role}' for role in ROLES} <= uris


def test_the_ticket_uris_are_resource_templates(
    listing: tuple[list[Resource], list[ResourceTemplate]],
) -> None:
    assert sorted(template.uri_template for template in listing[1]) == sorted((
        ENGINEER_URI,
        TICKET_URI,
        BRIEF_URI,
        STATUS_URI,
    ))


def test_a_reference_an_agent_and_a_template_read_back_verbatim() -> None:
    root = plugin_root()

    assert read('mm://ref/uncle-bob/solid') == root.joinpath(
        'skills/uncle-bob/references/solid.md'
    ).read_text(encoding='utf-8')
    assert read('mm://agent/wingman') == root.joinpath('agents/wingman.md').read_text(
        encoding='utf-8'
    )
    assert read('mm://template/reviewer').startswith('# Template: ')


def test_the_agent_contract_keeps_its_frontmatter() -> None:
    assert read('mm://agent/scout').startswith('---\nname: scout\n')


def test_the_bundled_scout_reference_is_not_the_scout_agent() -> None:
    """The merge-vader copy is stale by design; a later task retires it."""
    assert read('mm://ref/merge-vader/scout') != read('mm://agent/scout')


def test_an_unknown_skill_or_reference_is_an_error() -> None:
    assert 'Unknown resource' in read_error('mm://ref/uncle-bob/nope')
    assert 'Unknown resource' in read_error('mm://ref/nope/solid')
    assert 'Unknown resource' in read_error('mm://agent/nobody')


def test_a_ticket_and_its_brief_read_back_through_the_client(sprint: Path) -> None:
    assert read('mm://ticket/demo') == 'task: demo\n'
    assert read('mm://ticket/demo/brief/task-01') == render_asked(STANZA)


def test_the_status_resource_renders_a_line_per_task_and_the_counters(
    sprint: Path,
) -> None:
    lines = read('mm://ticket/demo/status').splitlines()

    assert lines[0] == 'task-01: asked, 0 attempts, commit none'
    assert lines[1] == (
        'demo: 1 tasks, 0 done, 0 verified, no upstream, whats-broken no, report no'
    )


def test_the_fleet_resource_still_serves_the_roster() -> None:
    assert 'scout (claude-haiku-4-5)' in read('mm://fleet')


def test_the_engineer_template_carries_the_active_tickets_asked_half(
    sprint: Path,
) -> None:
    dispatch = read('mm://template/engineer/task-01')

    assert render_asked(STANZA) in dispatch
    assert '.mightymodels/demo/briefs/task-01.md' in dispatch
    assert 'objective: <one sentence' not in dispatch


def test_the_engineer_template_needs_an_active_ticket_and_a_brief(sprint: Path) -> None:
    assert 'no brief at' in read_error('mm://template/engineer/task-09')

    sprint.joinpath('ticket.yml').unlink()
    assert ACTIVE_TICKET_VAR in read_error('mm://template/engineer/task-01')


def test_a_second_ticket_makes_the_environment_name_the_active_one(
    sprint: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = sprint.parent.joinpath('other')
    other.mkdir()
    other.joinpath('ticket.yml').write_text('task: other\n', encoding='utf-8')
    assert ACTIVE_TICKET_VAR in read_error('mm://template/engineer/task-01')

    monkeypatch.setenv(ACTIVE_TICKET_VAR, 'demo')
    assert render_asked(STANZA) in read('mm://template/engineer/task-01')


def test_every_bundled_resource_carries_a_description(
    listing: tuple[list[Resource], list[ResourceTemplate]],
) -> None:
    bundled = [resource for resource in listing[0] if resource.uri != 'mm://fleet']

    assert len(bundled) == len(REFS) + len(AGENTS) + len(ROLES)
    assert all(resource.description for resource in bundled)


def test_the_status_counters_follow_the_briefs(sprint: Path) -> None:
    brief = sprint.joinpath('briefs', 'task-01.md')
    halves = brief.read_text(encoding='utf-8')
    brief.write_text(
        f'{halves}\n## DONE\ncommit: abc1234\n\n## VERIFIED\n', encoding='utf-8'
    )
    sprint.joinpath('attempts.jsonl').write_text(
        '{"task_id": "task-01"}\n{"task_id": "task-01"}\n', encoding='utf-8'
    )
    sprint.joinpath('whats-broken.md').write_text('debugging\n', encoding='utf-8')
    sprint.joinpath('REPORT.md').write_text('shipped\n', encoding='utf-8')

    lines = read('mm://ticket/demo/status').splitlines()

    assert lines[0] == 'task-01: asked/done/verified, 2 attempts, commit abc1234'
    assert lines[1] == (
        'demo: 1 tasks, 1 done, 1 verified, no upstream, whats-broken yes, report yes'
    )


def test_the_raw_engineer_template_is_served_beside_the_filled_one(sprint: Path) -> None:
    assert 'objective: <one sentence' in read('mm://template/engineer')
    assert 'objective: Ship the thing' in read('mm://template/engineer/task-01')


def test_the_ticket_named_by_the_environment_must_be_one_path_segment(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ACTIVE_TICKET_VAR, '../evil')

    assert "contains '/'" in read_error('mm://template/engineer/task-01')


def test_a_brief_without_an_asked_half_has_no_engineer_dispatch(sprint: Path) -> None:
    sprint.joinpath('briefs', 'task-02.md').write_text('# notes\n', encoding='utf-8')

    assert 'has no ASKED half' in read_error('mm://template/engineer/task-02')


def test_an_absent_ticket_brief_or_status_is_an_error(repo: Path) -> None:
    assert 'no file at' in read_error('mm://ticket/ghost')
    assert 'no file at' in read_error('mm://ticket/ghost/brief/task-01')
    assert 'no ticket directory' in read_error('mm://ticket/ghost/status')


def test_a_traversal_parameter_is_rejected_before_a_path_is_built(repo: Path) -> None:
    assert 'Unknown resource' in read_error('mm://ref/../x/y')
    assert 'Unknown resource' in read_error('mm://agent/..')
    assert 'Unknown resource' in read_error('mm://ticket/../evil')
    assert 'Unknown resource' in read_error('mm://ticket/demo/brief/..')
    assert "contains '..'" in read_error('mm://ticket/a..b')
    assert "contains '..'" in read_error('mm://ticket/demo/brief/a..b')
