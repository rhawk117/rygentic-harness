"""The `investigation` tool on a served repository: what it refuses and what it answers."""

import pytest
from mightymodels.core.slug import Slug
from mightymodels.core.tests.support import GitRunner
from mightymodels.tools.investigation.ledger import recorded_ledger
from mightymodels.tools.investigation.service import InvestigationService
from mightymodels.tools.investigation.store import LedgerRecord
from mightymodels.tools.tests.support import (
    ActivityKind,
    DatabaseActivity,
    StateServer,
    text_of,
)

START_REQUEST = {'target': 'Queue drains slowly', 'kind': 'behavior'}
VALID_ENTRY = {'kind': 'known', 'text': 'first', 'cite': 'a.py:1', 'source': 'code-scout'}


def stored(investigations: InvestigationService, investigation: Slug) -> tuple[LedgerRecord, ...]:
    with investigations.store.transaction() as repository:
        return recorded_ledger(repository, investigation).records


class TestTheTool:
    UNKNOWN_KIND = "Input should be 'target', 'known', 'open', 'decision', 'resource' or 'next'"

    @pytest.fixture
    def started_through_the_tool(self, state_server: StateServer) -> Slug:
        (started,) = state_server.call(
            (
                'investigation',
                {'request': {'action': 'start', 'payload': {'request': START_REQUEST}}},
            )
        )
        return Slug(started.structured_content['investigation_id'])

    def test_a_ledger_in_a_repository_is_never_tracked(
        self, state_server: StateServer, started_through_the_tool: Slug, git: GitRunner
    ) -> None:
        exclude = state_server.root.joinpath('.git', 'info', 'exclude')

        assert started_through_the_tool.root.endswith('queue-drains-slowly')
        assert '.mightymodels/' in exclude.read_text(encoding='utf-8').splitlines()
        assert git(state_server.root, 'status', '--porcelain') == ''

    @pytest.mark.parametrize(
        ('entry', 'reason'),
        [
            pytest.param(
                {'kind': 'known', 'text': 'no cite', 'source': 'code-scout'},
                'needs a cite',
                id='no-cite',
            ),
            pytest.param(
                {'kind': 'decision', 'text': 'use v2', 'source': 'primary'},
                'cannot come from primary',
                id='decision-from-primary',
            ),
            pytest.param(
                {'kind': 'target', 'text': 'x', 'source': 'user'}, 'written by start', id='target'
            ),
            pytest.param(
                {'kind': 'open', 'text': '  ', 'source': 'user'}, 'text is empty', id='blank-text'
            ),
            pytest.param(
                {'kind': 'nonsense', 'text': 'x', 'source': 'user'}, UNKNOWN_KIND, id='unknown-kind'
            ),
            pytest.param(
                {'kind': 'next', 'text': 'look again', 'source': 'primary'},
                'a next entry cannot come from primary',
                id='next-from-primary',
            ),
            pytest.param(
                {'kind': 'resource', 'text': 'the runbook', 'source': 'user'},
                'a resource entry needs a cite',
                id='resource-without-a-cite',
            ),
        ],
    )
    def test_invalid_entry_is_rejected_without_writing(
        self,
        entry: dict[str, str],
        reason: str,
        state_server: StateServer,
        started_through_the_tool: Slug,
        investigation_service: InvestigationService,
    ) -> None:
        before = stored(investigation_service, started_through_the_tool)
        (refused,) = state_server.call(
            (
                'investigation',
                {
                    'request': {
                        'action': 'add',
                        'investigation_id': started_through_the_tool.root,
                        'payload': {'entries': [VALID_ENTRY, entry], 'request': {'round': 1}},
                    }
                },
            )
        )
        after = stored(investigation_service, started_through_the_tool)

        assert refused.is_error
        assert reason in text_of(refused)
        assert before == after

    def test_a_round_is_added_rendered_and_listed_through_the_tool(
        self, state_server: StateServer, started_through_the_tool: Slug
    ) -> None:
        investigation = started_through_the_tool.root
        added, rendered, knowns, listed = state_server.call(
            (
                'investigation',
                {
                    'request': {
                        'action': 'add',
                        'investigation_id': investigation,
                        'payload': {'entries': [VALID_ENTRY], 'request': {'round': 1}},
                    }
                },
            ),
            ('investigation', {'request': {'action': 'render', 'investigation_id': investigation}}),
            (
                'investigation',
                {
                    'request': {
                        'action': 'knowns',
                        'investigation_id': investigation,
                        'payload': {'request': {'kinds': ['open'], 'limit': 5}},
                    }
                },
            ),
            ('investigation', {'request': {'action': 'list'}}),
        )

        assert added.structured_content == {
            'text': f'saved e2 to {investigation} (0 redacted)\n',
            'investigation_id': investigation,
        }
        assert '- e2: first [a.py:1] (code-scout, round 1)' in rendered.structured_content['text']
        assert '| e2 |' not in knowns.structured_content['text']
        assert listed.structured_content == {
            'text': f'{investigation}\tround 1\n',
            'investigation_id': None,
        }

    def test_knowns_without_a_request_shows_the_whole_table(
        self, state_server: StateServer, started_through_the_tool: Slug
    ) -> None:
        investigation = started_through_the_tool.root
        _, knowns = state_server.call(
            (
                'investigation',
                {
                    'request': {
                        'action': 'add',
                        'investigation_id': investigation,
                        'payload': {'entries': [VALID_ENTRY], 'request': {'round': 1}},
                    }
                },
            ),
            ('investigation', {'request': {'action': 'knowns', 'investigation_id': investigation}}),
        )

        assert (
            '| e2 | known | first | a.py:1 | code-scout | 1 | lead |'
            in (knowns.structured_content['text'])
        )

    @pytest.mark.parametrize(
        ('arguments', 'needs'),
        [
            pytest.param(
                {'action': 'start'},
                'request.start.payload\n  Field required',
                id='start-without-a-request',
            ),
            pytest.param(
                {'action': 'start', 'payload': {'request': {'round': 1}}},
                'request.start.payload.request.round\n  Extra inputs are not permitted',
                id='start-with-a-round',
            ),
            pytest.param(
                {'action': 'add', 'payload': {'entries': [], 'request': {'round': 1}}},
                'request.add.investigation_id\n  Field required',
                id='add-without-an-investigation',
            ),
            pytest.param(
                {'action': 'add', 'investigation_id': 'a', 'payload': {'request': {'round': 1}}},
                'request.add.payload.entries\n  Field required',
                id='add-without-entries',
            ),
            pytest.param(
                {'action': 'add', 'investigation_id': 'a', 'payload': {'entries': []}},
                'request.add.payload.request\n  Field required',
                id='add-without-a-round',
            ),
            pytest.param(
                {'action': 'render'},
                'request.render.investigation_id\n  Field required',
                id='render-of-nothing',
            ),
            pytest.param(
                {'action': 'knowns'},
                'request.knowns.investigation_id\n  Field required',
                id='knowns-of-nothing',
            ),
            pytest.param(
                {'action': 'knowns', 'investigation_id': 'a', 'payload': {'request': {'round': 1}}},
                'request.knowns.payload.request.round\n  Extra inputs are not permitted',
                id='knowns-with-a-round',
            ),
        ],
    )
    def test_an_action_missing_its_part_says_what_it_needs(
        self,
        arguments: dict[str, object],
        needs: str,
        connected_server: StateServer,
        database_activity: DatabaseActivity,
    ) -> None:
        (refused,) = connected_server.call(('investigation', {'request': arguments}))

        assert refused.is_error
        assert needs in text_of(refused)
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()

    @pytest.mark.parametrize(
        'arguments',
        [
            pytest.param({'action': 'delete'}, id='unknown-action'),
            pytest.param(
                {'action': 'render', 'investigation_id': '../outside'}, id='path-shaped-id'
            ),
            pytest.param(
                {'action': 'start', 'payload': {'request': {'target': 'x', 'kind': 'hunch'}}},
                id='unknown-target-kind',
            ),
            pytest.param(
                {
                    'action': 'start',
                    'payload': {'request': {**START_REQUEST, 'path': 'ledger.jsonl'}},
                },
                id='unknown-request-field',
            ),
            pytest.param(
                {'action': 'knowns', 'investigation_id': 'a', 'payload': {'request': {'limit': 0}}},
                id='knowns-limit-zero',
            ),
            pytest.param(
                {
                    'action': 'knowns',
                    'investigation_id': 'a',
                    'payload': {'request': {'kinds': ['target']}},
                },
                id='knowns-of-the-target',
            ),
            pytest.param(
                {
                    'action': 'knowns',
                    'investigation_id': 'a',
                    'payload': {'request': {'kinds': []}},
                },
                id='knowns-of-no-kind',
            ),
            pytest.param(
                {
                    'action': 'add',
                    'investigation_id': 'a',
                    'payload': {'request': {'round': 1}, 'entries': [{**VALID_ENTRY, 'seq': 7}]},
                },
                id='entry-numbering-itself',
            ),
            pytest.param(
                {
                    'action': 'add',
                    'investigation_id': 'a',
                    'payload': {
                        'request': {'round': 1},
                        'entries': [{**VALID_ENTRY, 'cite': '  '}],
                    },
                },
                id='blank-cite',
            ),
        ],
    )
    def test_arguments_outside_the_schema_are_refused(
        self,
        arguments: dict[str, object],
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (refused,) = connected_server.call(('investigation', {'request': arguments}))

        assert refused.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert connected_server.files_on_disk() == tree_after_the_connect
