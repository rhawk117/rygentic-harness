from pathlib import Path

import pytest
import yaml
from mightymcp.routing import Scope
from mightymcp.ticket import (
    CompanionDocs,
    HandoffContext,
    Ticket,
    resolve_model,
    ticket_create,
    ticket_read,
    ticket_update_context,
)

CONTEXT = ['the api is sync', 'retries are capped at three', 'the fixture is shared']
SCHEMA_KEYS = [
    'task',
    'summary',
    'triaged-at',
    'context',
    'companion-docs',
    'subagent-models',
    'handoff-context',
]


def handoff(scope: Scope = 'med', *, plan_first: bool = False) -> HandoffContext:
    return HandoffContext(scope=scope, plan_first=plan_first, branch_name='feat/demo')


def create(slug: str = 'demo', context: list[str] | None = None) -> Ticket:
    written = ticket_create(slug, 'Ship the thing', context or CONTEXT, handoff())
    assert written.refusals == []
    assert written.ticket is not None
    return written.ticket


def read_yaml(repo: Path, slug: str = 'demo') -> dict:
    path = repo.joinpath('.mightymodels', slug, 'ticket.yml')
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def test_create_writes_the_ticket_and_its_subdirectories(repo: Path) -> None:
    ticket = create()
    directory = repo.joinpath('.mightymodels', 'demo')

    assert ticket.task == 'demo'
    assert directory.joinpath('handoffs').is_dir()
    assert directory.joinpath('briefs').is_dir()
    assert directory.joinpath('ticket.yml').is_file()


def test_the_written_yaml_keeps_the_schema_field_order(repo: Path) -> None:
    create()
    assert list(read_yaml(repo)) == SCHEMA_KEYS


def test_create_fills_the_model_block_from_the_defaults(repo: Path) -> None:
    create()
    models = read_yaml(repo)['subagent-models']

    assert models['scout'] == 'claude-haiku-4-5'
    assert models['budgetron'] == 'claude-sonnet-5'
    assert models['uncle-bob'] == 'claude-opus-5'
    assert models['engineer'] == 'claude-sonnet-5'
    assert models['primary-agent'] is None


def test_create_records_the_companion_docs_it_was_given(repo: Path) -> None:
    written = ticket_create(
        'demo',
        'Ship the thing',
        CONTEXT,
        handoff(),
        CompanionDocs(issue_number=7, jira_key='PROJ-1'),
    )

    assert written.refusals == []
    docs = read_yaml(repo)['companion-docs']
    assert docs['issue-number'] == 7
    assert docs['jira-key'] == 'PROJ-1'


def test_create_runs_the_ignore_ritual_once(repo: Path) -> None:
    create('demo')
    create('second')

    exclude = repo.joinpath('.git', 'info', 'exclude').read_text(encoding='utf-8')
    assert exclude.splitlines().count('.mightymodels/') == 1


def test_create_refuses_a_slug_that_already_exists(repo: Path) -> None:
    create()
    written = ticket_create('demo', 'Ship it again', CONTEXT, handoff())

    assert written.ticket is None
    assert 'already exists' in written.refusals[0]
    assert read_yaml(repo)['summary'] == 'Ship the thing'


def test_create_refuses_an_unsafe_slug(repo: Path) -> None:
    written = ticket_create('../evil', 'Ship the thing', CONTEXT, handoff())

    assert written.ticket is None
    assert "contains '/'" in written.refusals[0]


@pytest.mark.parametrize(
    'context',
    [
        ['one', 'two'],
        ['one'],
        [],
        ['one', 'two', 'three', 'four', 'five', 'six', 'seven'],
    ],
)
def test_create_refuses_a_context_outside_three_to_six_lines(
    context: list[str], repo: Path
) -> None:
    written = ticket_create('demo', 'Ship the thing', context, handoff())

    assert 'the schema allows 3-6' in written.refusals[0]
    assert not repo.joinpath('.mightymodels', 'demo').exists()


@pytest.mark.parametrize(
    'line',
    ['see src/api/limits.py:88', 'plugins/a/b.md:3 is the contract', 'client.py:1'],
)
def test_create_refuses_a_context_carrying_a_citation(line: str, repo: Path) -> None:
    written = ticket_create('demo', 'Ship the thing', [*CONTEXT[:2], line], handoff())

    assert 'file:line citation' in written.refusals[0]
    assert not repo.joinpath('.mightymodels', 'demo').exists()


def test_read_returns_the_parsed_ticket(repo: Path) -> None:
    create()
    read = ticket_read('demo')

    assert read.refusals == []
    assert read.ticket is not None
    assert read.ticket.summary == 'Ship the thing'
    assert read.ticket.context == CONTEXT
    assert read.ticket.handoff_context.branch_name == 'feat/demo'


def test_read_refuses_a_missing_ticket(repo: Path) -> None:
    read = ticket_read('demo')

    assert read.ticket is None
    assert 'no ticket.yml at' in read.refusals[0]


def test_read_refuses_an_unsafe_slug(repo: Path) -> None:
    read = ticket_read('a/b')

    assert read.ticket is None
    assert read.refusals[0].startswith('name')


def test_read_refuses_malformed_yaml_with_the_parser_error(ticket_root: Path) -> None:
    ticket_root.joinpath('ticket.yml').write_text('task: [demo\n', encoding='utf-8')
    read = ticket_read('demo')

    assert read.ticket is None
    assert 'is not valid YAML' in read.refusals[0]
    assert 'expected' in read.refusals[0]


def test_read_refuses_a_file_that_is_not_a_mapping(ticket_root: Path) -> None:
    ticket_root.joinpath('ticket.yml').write_text('- one\n- two\n', encoding='utf-8')
    read = ticket_read('demo')

    assert read.ticket is None
    assert 'not a YAML mapping' in read.refusals[0]


def test_read_refuses_a_ticket_that_misses_schema_fields(ticket_root: Path) -> None:
    ticket_root.joinpath('ticket.yml').write_text('task: demo\n', encoding='utf-8')
    read = ticket_read('demo')

    assert read.ticket is None
    assert 'does not match the ticket schema' in read.refusals[0]


def test_update_context_replaces_the_rollup(repo: Path) -> None:
    create()
    replacement = ['first fact', 'second fact', 'third fact', 'fourth fact']
    written = ticket_update_context('demo', replacement)

    assert written.refusals == []
    assert written.ticket is not None
    assert written.ticket.context == replacement
    assert read_yaml(repo)['context'] == replacement


def test_update_context_keeps_hand_added_keys(repo: Path) -> None:
    create()
    path = repo.joinpath('.mightymodels', 'demo', 'ticket.yml')
    raw = read_yaml(repo)
    raw['notes'] = 'added by hand'
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding='utf-8')

    assert ticket_update_context('demo', ['a fact', 'b fact', 'c fact']).refusals == []
    assert read_yaml(repo)['notes'] == 'added by hand'


@pytest.mark.parametrize(
    'context',
    [['one', 'two'], ['1', '2', '3', '4', '5', '6', '7'], ['a', 'b', 'src/x.py:4']],
)
def test_update_context_refuses_and_leaves_the_file_alone(
    context: list[str], repo: Path
) -> None:
    create()
    written = ticket_update_context('demo', context)

    assert written.ticket is None
    assert written.refusals
    assert read_yaml(repo)['context'] == CONTEXT


def test_update_context_refuses_an_unsafe_slug(repo: Path) -> None:
    written = ticket_update_context('a/b', ['a fact', 'b fact', 'c fact'])

    assert written.ticket is None
    assert written.refusals[0].startswith('name')


def test_update_context_refuses_a_ticket_that_breaks_the_schema(
    ticket_root: Path,
) -> None:
    path = ticket_root.joinpath('ticket.yml')
    path.write_text('task: demo\n', encoding='utf-8')
    written = ticket_update_context('demo', ['a fact', 'b fact', 'c fact'])

    assert written.ticket is None
    assert 'does not match the ticket schema' in written.refusals[0]
    assert path.read_text(encoding='utf-8') == 'task: demo\n'


def test_update_context_refuses_a_missing_ticket(repo: Path) -> None:
    written = ticket_update_context('demo', ['a fact', 'b fact', 'c fact'])

    assert written.ticket is None
    assert 'no ticket.yml at' in written.refusals[0]


def test_resolve_model_without_a_slug_uses_the_defaults() -> None:
    choice = resolve_model('scout')

    assert choice.model == 'claude-haiku-4-5'
    assert choice.source == 'default'
    assert choice.rule == 'default for scout'


def test_resolve_model_reads_the_ticket_pin(repo: Path) -> None:
    create()
    choice = resolve_model('scout', 'demo')

    assert choice.model == 'claude-haiku-4-5'
    assert choice.source == 'ticket'
    assert choice.rule == 'ticket pins scout'


@pytest.mark.parametrize(
    'row',
    [('large', 'claude-opus-5'), ('med', 'claude-sonnet-5'), ('sm', 'claude-sonnet-5')],
)
def test_resolve_model_derives_the_engineer_from_scope(
    row: tuple[str, str], repo: Path
) -> None:
    scope, expected = row
    create()
    path = repo.joinpath('.mightymodels', 'demo', 'ticket.yml')
    raw = read_yaml(repo)
    del raw['subagent-models']['engineer']
    raw['handoff-context']['scope'] = scope
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding='utf-8')

    choice = resolve_model('engineer', 'demo')
    assert choice.model == expected
    assert choice.source == 'default'
    assert choice.rule == f'engineer derived from scope {scope}'


def test_resolve_model_refuses_an_unknown_role(repo: Path) -> None:
    create()
    choice = resolve_model('nobody', 'demo')

    assert choice.model is None
    assert choice.source == 'none'
    assert "unknown role 'nobody'" in choice.refusals[0]


def test_resolve_model_refuses_a_missing_ticket(repo: Path) -> None:
    choice = resolve_model('scout', 'demo')

    assert choice.model is None
    assert choice.source == 'none'
    assert 'no ticket.yml at' in choice.refusals[0]
