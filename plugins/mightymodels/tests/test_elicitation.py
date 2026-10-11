"""The questions the state tools put to the user, driven the way a host drives them.

A scripted host stands in for Claude Code: it receives the input-required result of a tool call,
answers each question, and retries the same call with the answers, which is what the host does on
protocol 2026-07-28. `Context.elicit` is never used because that host has no back-channel for it.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from operator import attrgetter
from pathlib import Path
from typing import Literal

import pytest
from mcp.types import CallToolResult, ElicitResult
from mightymodels_plugin.core.declarative import NAME_LIMIT, PROSE_LIMIT
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.tools.contract.tables import CommandRow
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.review.tables import ReviewDispositionRow
from mightymodels_plugin.tools.tests.scripted_host import (
    SLUG,
    TICKET_INTERVIEW,
    Arguments,
    Exchange,
    Replies,
    Stored,
    exchange_with,
    review_runs,
    rows_read,
    said,
    ticket_handoff,
    unanswered,
)
from mightymodels_plugin.tools.tests.support import StateServer, text_of

type Content = dict[str, str | int | float | bool | list[str] | None]
SOURCE_DIRECTORY = Path(__file__).parent.parent.joinpath('src')
REPORT = Path(__file__).parent.joinpath('fixtures', 'merge-vader-report.md')
DRAIN = 'the drain loop'
NO_ONE_ANSWERED = 'needs input: no one answered; ask the user, then call again'


def contract_rows(server: StateServer) -> object:
    return rows_read(server, CommandRow, attrgetter('command_id', 'approved_by'))


def dispositions(server: StateServer) -> object:
    return rows_read(
        server,
        ReviewDispositionRow,
        attrgetter('finding_id', 'decision', 'reason', 'by'),
    )


def investigation_targets(server: StateServer) -> object:
    return rows_read(server, LedgerEntryRow, attrgetter('kind', 'text', 'cite'))


@dataclass(slots=True, kw_only=True, frozen=True)
class Row:
    id: str
    tool: str
    bare: Arguments
    carrying: Arguments
    outside: Arguments
    reply: Content
    shown: Mapping[str, list[str] | str]
    question: str
    argument: str
    stored: Stored
    expected: object
    needs_findings: bool = False


def with_payload(base: Arguments, **given: object) -> Arguments:
    payload = base['payload']
    assert isinstance(payload, dict)
    return base | {'payload': payload | given}


def with_fields(base: Arguments, **given: object) -> Arguments:
    fields = base['fields']
    assert isinstance(fields, dict)
    return base | {'fields': fields | given}


APPROVE: Arguments = {'action': 'approve', 'slug': SLUG}
COMMAND: Arguments = {'id': 'T1.AC-1', 'argv': ['true']}
START: Arguments = {'action': 'start', 'payload': {}}
DISPOSE: Arguments = {'action': 'dispose', 'payload': {'by': 'user', 'finding': 'F1'}}
INVESTIGATE: Arguments = {'action': 'start', 'payload': {'request': {'target': DRAIN}}}
WRITE: Arguments = {'action': 'write', 'slug': SLUG, 'fields': TICKET_INTERVIEW}

APPROVAL = Row(
    id='A1',
    tool='contract',
    bare=APPROVE | {'commands': [COMMAND]},
    carrying=APPROVE | {'commands': [COMMAND | {'approved_by': 'user'}]},
    outside=APPROVE | {'commands': [COMMAND | {'approved_by': 'x' * (NAME_LIMIT + 1)}]},
    reply={'choice': 'approve'},
    shown={'enum': ['approve', 'remove', 'edit'], 'type': 'string'},
    question='Approve these verification commands?\nT1.AC-1: true',
    argument='approved_by "user" on each command',
    stored=contract_rows,
    expected=[('T1.AC-1', 'user')],
)
SCOPE_OF_A_REVIEW = Row(
    id='A5',
    tool='review',
    bare=with_payload(START, depth='deep', emphasis='balanced'),
    carrying=with_payload(START, scope='codebase', depth='deep', emphasis='balanced'),
    outside=with_payload(START, scope='galaxy', depth='deep', emphasis='balanced'),
    reply={'choice': 'codebase'},
    shown={'enum': ['diff', 'branch', 'ticket', 'codebase'], 'type': 'string'},
    question='What should the review cover?',
    argument='request.payload.scope',
    stored=review_runs,
    expected=[('codebase', 'deep', 'balanced')],
)
DEPTH_OF_A_REVIEW = Row(
    id='A6',
    tool='review',
    bare=with_payload(START, scope='codebase', emphasis='balanced'),
    carrying=with_payload(START, scope='codebase', depth='deep', emphasis='balanced'),
    outside=with_payload(START, scope='codebase', depth='abyss', emphasis='balanced'),
    reply={'choice': 'deep'},
    shown={'enum': ['quick', 'standard', 'deep'], 'type': 'string'},
    question='How deep should the review go?',
    argument='request.payload.depth',
    stored=review_runs,
    expected=[('codebase', 'deep', 'balanced')],
)
EMPHASIS_OF_A_REVIEW = Row(
    id='A7',
    tool='review',
    bare=with_payload(START, scope='codebase', depth='deep'),
    carrying=with_payload(START, scope='codebase', depth='deep', emphasis='balanced'),
    outside=with_payload(START, scope='codebase', depth='deep', emphasis='whatever'),
    reply={'choice': 'balanced'},
    shown={
        'enum': ['release-readiness', 'maintainability', 'balanced', 'custom'],
        'type': 'string',
    },
    question='What should the review emphasize?',
    argument='request.payload.emphasis',
    stored=review_runs,
    expected=[('codebase', 'deep', 'balanced')],
)
DISPOSITION = Row(
    id='A9',
    tool='review',
    bare=DISPOSE,
    carrying=with_payload(DISPOSE, decisions={'F1': {'decision': 'fix'}}) | {'run_id': ''},
    outside=with_payload(DISPOSE, decisions={'F1': {'decision': 'nuke'}}),
    reply={'choice': 'fix'},
    shown={'enum': ['fix', 'defer', 'accept-risk', 'dismiss'], 'type': 'string'},
    question='What should happen to F1? accept-risk and dismiss need a reason.',
    argument='request.payload.decisions {"F1"',
    stored=dispositions,
    expected=[('F1', 'fix', '', 'user')],
    needs_findings=True,
)
KIND_OF_A_TARGET = Row(
    id='A10',
    tool='investigation',
    bare=INVESTIGATE,
    carrying={
        'action': 'start',
        'payload': {'request': {'target': DRAIN, 'kind': 'behavior'}},
    },
    outside={'action': 'start', 'payload': {'request': {'target': DRAIN, 'kind': 'rumor'}}},
    reply={'choice': 'behavior'},
    shown={'enum': ['behavior', 'claim', 'research', 'change'], 'type': 'string'},
    question=f'What kind of target is this? {DRAIN}',
    argument='request.payload.request.kind',
    stored=investigation_targets,
    expected=[('target', DRAIN, 'behavior')],
)
SCOPE_OF_THE_WORK = Row(
    id='A11',
    tool='ticket',
    bare=with_fields(WRITE, compaction=True, branch='fix/retry-queue'),
    carrying=with_fields(WRITE, scope='large', compaction=True, branch='fix/retry-queue'),
    outside=with_fields(WRITE, scope='huge', compaction=True, branch='fix/retry-queue'),
    reply={'choice': 'large'},
    shown={'enum': ['sm', 'med', 'large'], 'type': 'string'},
    question='What is the scope of each anticipated task?',
    argument='request.fields.scope',
    stored=ticket_handoff,
    expected=[('scope', '"large"'), ('plan-first', 'true'), ('branch-name', '"fix/retry-queue"')],
)
COMPACTION = Row(
    id='A12',
    tool='ticket',
    bare=with_fields(WRITE, scope='large', branch='fix/retry-queue'),
    carrying=with_fields(WRITE, scope='large', compaction=False, branch='fix/retry-queue'),
    outside=with_fields(WRITE, scope='large', compaction='sometimes', branch='fix/retry-queue'),
    reply={'choice': False},
    shown={'title': 'Choice', 'type': 'boolean'},
    question='Would implementing this likely cause at least one compaction?',
    argument='request.fields.compaction',
    stored=ticket_handoff,
    expected=[('scope', '"large"'), ('plan-first', 'false'), ('branch-name', '"fix/retry-queue"')],
)
BRANCH = Row(
    id='A13',
    tool='ticket',
    bare=with_fields(WRITE, scope='large', compaction=True),
    carrying=with_fields(WRITE, scope='large', compaction=True, branch='fix/drain'),
    outside=with_fields(WRITE, scope='large', compaction=True, branch='x' * (NAME_LIMIT + 1)),
    reply={'choice': 'new', 'name': 'fix/drain'},
    shown={'enum': ['current', 'new'], 'type': 'string'},
    question='Run the work on the current branch, or on a new one? A new one needs a name.',
    argument='request.fields.branch',
    stored=ticket_handoff,
    expected=[('scope', '"large"'), ('plan-first', 'true'), ('branch-name', '"fix/drain"')],
)
ROWS = (
    pytest.param(APPROVAL, id='A1-A2'),
    pytest.param(SCOPE_OF_A_REVIEW, id='A5'),
    pytest.param(DEPTH_OF_A_REVIEW, id='A6'),
    pytest.param(EMPHASIS_OF_A_REVIEW, id='A7'),
    pytest.param(DISPOSITION, id='A9'),
    pytest.param(KIND_OF_A_TARGET, id='A10'),
    pytest.param(SCOPE_OF_THE_WORK, id='A11'),
    pytest.param(COMPACTION, id='A12'),
    pytest.param(BRANCH, id='A13'),
)


def asked_with(
    server: StateServer, row: Row, replies: Replies | None, arguments: Arguments | None = None
) -> Exchange:
    given = row.bare if arguments is None else arguments
    return asyncio.run(exchange_with(server, row.tool, given, row.stored, replies))


def accepted(content: Content) -> Replies:
    return Replies(fallback=ElicitResult(action='accept', content=content))


def shown_choices(row: Row) -> list[object]:
    return list(row.shown.get('enum', ['true', 'false']))


def row_in_a_run(server: StateServer, row: Row) -> Row:
    if not row.needs_findings:
        return row
    (started,) = server.call(
        (
            'review',
            {
                'request': {
                    'action': 'start',
                    'payload': {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'},
                }
            },
        )
    )
    run = str(started.structured_content['run_id'])
    directory = server.root.joinpath('.mightymodels', '.runtime', 'reviews', run)
    directory.joinpath('MERGE-VADER-REPORT.md').write_text(
        REPORT.read_text(encoding='utf-8'), encoding='utf-8'
    )
    add: Arguments = {'action': 'add', 'run_id': run, 'payload': {'persona': 'merge-vader'}}
    (added,) = server.call(('review', {'request': add}))
    assert not added.is_error
    given = {'run_id': run}
    return replace(
        row, bare=row.bare | given, carrying=row.carrying | given, outside=row.outside | given
    )


@pytest.fixture(params=ROWS)
def row(request: pytest.FixtureRequest, state_server: StateServer) -> Row:
    return row_in_a_run(state_server, request.param)


class TestEachQuestion:
    def test_a_call_that_leaves_the_value_out_asks_one_question_through_the_host(
        self, row: Row, state_server: StateServer
    ) -> None:
        question = asked_with(state_server, row, None).question()

        assert question.message == row.question
        assert question.requested_schema['properties']['choice'] == row.shown
        assert question.requested_schema['required'] == ['choice']

    def test_the_call_that_asks_stores_nothing(self, row: Row, state_server: StateServer) -> None:
        done = asked_with(state_server, row, None)

        assert done.between == done.before
        assert done.after == done.before

    def test_the_retried_call_that_carries_the_answer_stores_it(
        self, row: Row, state_server: StateServer
    ) -> None:
        done = asked_with(state_server, row, accepted(row.reply))

        assert not done.result().is_error, text_of(done.result())
        assert done.between == done.before
        assert done.after == row.expected

    def test_a_call_that_already_carries_the_value_asks_nothing(
        self, row: Row, state_server: StateServer
    ) -> None:
        done = asked_with(state_server, row, None, row.carrying)

        assert isinstance(done.first, CallToolResult)
        assert not done.first.is_error, text_of(done.first)
        assert done.after == row.expected

    def test_an_answer_outside_the_choices_is_refused_before_any_write(
        self, row: Row, state_server: StateServer
    ) -> None:
        done = asked_with(state_server, row, accepted({'choice': 'nonsense'}))

        assert done.refused().is_error
        assert done.after == done.before

    def test_an_argument_outside_the_choices_is_refused_before_any_write(
        self, row: Row, state_server: StateServer
    ) -> None:
        done = asked_with(state_server, row, None, row.outside)

        assert done.refused().is_error
        assert done.after == done.before

    @pytest.mark.parametrize('action', ['cancel', 'decline'])
    def test_no_answer_stores_nothing_and_returns_what_to_ask_and_pass(
        self, action: Literal['cancel', 'decline'], row: Row, state_server: StateServer
    ) -> None:
        done = asked_with(state_server, row, unanswered(action))
        result = done.result()
        text = said(result)

        assert not result.is_error
        assert text.startswith(f'{NO_ONE_ANSWERED} with the argument shown\n{row.question}\n')
        assert f'\nchoices: {", ".join(map(str, shown_choices(row)))}\n' in text
        assert f'\npass: {row.argument}' in text
        assert done.after == done.before


class TestWhatOnlyOneQuestionNeeds:
    def test_a_user_who_chooses_to_remove_or_edit_approves_nothing(
        self, state_server: StateServer
    ) -> None:
        for choice in ('remove', 'edit'):
            done = asked_with(state_server, APPROVAL, accepted({'choice': choice}))

            assert not done.result().is_error
            assert said(done.result()).startswith(f'not approved: the user chose to {choice}')
            assert done.after == []

    def test_a_reason_is_asked_of_the_choices_that_need_one_and_refused_when_missing(
        self, state_server: StateServer
    ) -> None:
        row = row_in_a_run(state_server, DISPOSITION)

        done = asked_with(state_server, row, accepted({'choice': 'accept-risk'}))

        assert done.refused().is_error
        assert done.after == []

    def test_a_reason_is_stored_with_the_decision(self, state_server: StateServer) -> None:
        row = row_in_a_run(state_server, DISPOSITION)
        content: Content = {'choice': 'defer', 'reason': 'ticketed for later'}

        done = asked_with(state_server, row, accepted(content))

        assert done.after == [('F1', 'defer', 'ticketed for later', 'user')]

    def test_a_reason_over_the_length_of_an_argument_is_refused_before_any_write(
        self, state_server: StateServer
    ) -> None:
        row = row_in_a_run(state_server, DISPOSITION)
        content: Content = {'choice': 'dismiss', 'reason': 'x' * (PROSE_LIMIT + 1)}

        done = asked_with(state_server, row, accepted(content))

        assert done.refused().is_error
        assert done.after == []

    def test_the_current_branch_is_recorded_under_its_own_name(
        self, state_server: StateServer, git: GitRunner
    ) -> None:
        current = git(state_server.root, 'symbolic-ref', '--short', 'HEAD').strip()

        done = asked_with(state_server, BRANCH, accepted({'choice': 'current'}))

        assert done.after == [
            ('scope', '"large"'),
            ('plan-first', 'true'),
            ('branch-name', f'"{current}"'),
        ]

    def test_a_new_branch_without_a_name_is_refused_before_any_write(
        self, state_server: StateServer
    ) -> None:
        done = asked_with(state_server, BRANCH, accepted({'choice': 'new', 'name': ' '}))

        assert done.refused().is_error
        assert done.after == []

    def test_a_branch_name_over_the_length_of_an_argument_is_refused_before_any_write(
        self, state_server: StateServer
    ) -> None:
        content: Content = {'choice': 'new', 'name': 'x' * (NAME_LIMIT + 1)}

        done = asked_with(state_server, BRANCH, accepted(content))

        assert done.refused().is_error
        assert done.after == []


class TestNothingUsesContextElicit:
    def test_no_tool_source_calls_elicit_on_a_context(self) -> None:
        sources = SOURCE_DIRECTORY.rglob('*.py')

        assert [path.name for path in sources if '.elicit(' in path.read_text()] == []
