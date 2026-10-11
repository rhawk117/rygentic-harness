"""The `crashout` tool on a served repository: what it refuses and what it answers."""

import pytest
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.crashout.schema import CrashoutEntry, Severity, Verdict
from mightymodels_plugin.tools.tests.support import (
    ActivityKind,
    DatabaseActivity,
    StateServer,
    text_of,
)
from pydantic import ValidationError

SKIPPED_TESTS = CrashoutEntry(
    ticket=Slug('retry-queue'),
    branch='fix/retry-queue',
    severity=Severity.HEATED,
    verdict=Verdict.DESERVED,
    rant='WHY did you skip the tests\r\n  AGAIN   \r\r\n',
    failures=('skipped the tests', 'claimed done'),
    root_cause='  optimised for speed  ',
    corrective_action='run the gate  before reporting',
    barked_back=False,
)
ENTRY = SKIPPED_TESTS.model_dump(mode='json')


class TestRefusals:
    @pytest.mark.parametrize(
        'entry',
        [
            pytest.param({**ENTRY, 'at': '2026-01-01T00:00:00Z'}, id='its-own-timestamp'),
            pytest.param({**ENTRY, 'mood': 'bad'}, id='unknown-key'),
            pytest.param({**ENTRY, 'severity': 'furious'}, id='unknown-severity'),
            pytest.param({**ENTRY, 'verdict': 'guilty'}, id='unknown-verdict'),
            pytest.param({**ENTRY, 'failures': []}, id='no-failures'),
            pytest.param({**ENTRY, 'failures': ['skipped', '  ']}, id='blank-failure'),
            pytest.param({**ENTRY, 'rant': ' \n '}, id='blank-rant'),
            pytest.param({**ENTRY, 'root_cause': '  '}, id='blank-root-cause'),
            pytest.param({**ENTRY, 'corrective_action': ''}, id='blank-corrective-action'),
            pytest.param({**ENTRY, 'barked_back': 'loudly'}, id='barked-back-not-a-bool'),
            pytest.param({**ENTRY, 'ticket': '../outside'}, id='path-shaped-ticket'),
            pytest.param(
                {key: value for key, value in ENTRY.items() if key != 'rant'}, id='no-rant'
            ),
        ],
    )
    def test_an_entry_outside_the_schema_is_refused_and_nothing_is_stored(
        self,
        entry: dict[str, object],
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (refused,) = connected_server.call(('crashout', {'action': 'add', 'entry': entry}))

        with pytest.raises(ValidationError):
            CrashoutEntry.model_validate(entry)
        assert refused.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert connected_server.files_on_disk() == tree_after_the_connect

    def test_add_without_an_entry_says_what_it_needs(
        self, connected_server: StateServer, database_activity: DatabaseActivity
    ) -> None:
        (refused,) = connected_server.call(('crashout', {'action': 'add'}))

        assert refused.is_error
        assert 'add needs an entry holding the crashout' in text_of(refused)
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()

    def test_an_unknown_action_is_refused(self, connected_server: StateServer) -> None:
        (refused,) = connected_server.call(('crashout', {'action': 'prune'}))

        assert refused.is_error


class TestTheTool:
    def test_a_crashout_is_journaled_read_back_and_counted_through_the_tool(
        self, state_server: StateServer
    ) -> None:
        added, last, stats = state_server.call(
            ('crashout', {'action': 'add', 'entry': ENTRY}),
            ('crashout', {'action': 'last'}),
            ('crashout', {'action': 'stats'}),
        )

        assert added.structured_content == {'text': 'journaled crashout #1\n', 'entry': None}
        assert last.structured_content['entry'] == {
            **ENTRY,
            'at': last.structured_content['entry']['at'],
            'rant': 'WHY did you skip the tests\n  AGAIN',
            'root_cause': 'optimised for speed',
        }
        assert stats.structured_content['text'].startswith('entries: 1\nseverity: heated=1\n')
