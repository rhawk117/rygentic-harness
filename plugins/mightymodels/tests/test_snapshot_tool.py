"""The snapshot tool through a connected server: what the boundary refuses before the service,
and that a snapshot it takes leaves every table with the rows it had."""

import pytest
import sqlalchemy as sql
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.tools.tests.support import StateServer, ToolCall, text_of

SLUG = 'retry-queue'
ANSWERS = {
    'summary': 'Retry queue drains slowly',
    'scope': 'med',
    'compaction': False,
    'branch': 'fix/retry-queue',
    'context': ['drain loop sleeps between batches'],
}
COMMAND = {'id': 'T1.AC-1', 'argv': ['true'], 'approved_by': 'user'}
START = {'by': 'engineer', 'owned': ['src/queue.py'], 'acceptance': ['AC-1']}

type RowsByTable = dict[str, list[tuple[object, ...]]]


def rows_of_every_table(database: Database) -> RowsByTable:
    stored = sql.MetaData()
    stored.reflect(database.engine)
    with database.transaction() as session:
        return {
            table.name: [tuple(row) for row in session.execute(sql.select(table))]
            for table in stored.sorted_tables
        }


class TestAnUnstagedTicket:
    def test_a_path_shaped_slug_is_refused(
        self, connected_server: StateServer, tree_after_the_connect: dict[str, bytes]
    ) -> None:
        (refused,) = connected_server.call(('snapshot', {'request': {'slug': '../../etc'}}))

        assert refused.is_error
        assert 'String should match pattern' in text_of(refused)
        assert connected_server.files_on_disk() == tree_after_the_connect


class TestATicketWithAStartedTask:
    RECORDED: tuple[ToolCall, ...] = (
        ('ticket', {'request': {'action': 'write', 'slug': SLUG, 'fields': ANSWERS}}),
        ('ticket', {'request': {'action': 'validate', 'slug': SLUG}}),
        ('contract', {'request': {'action': 'approve', 'slug': SLUG, 'commands': [COMMAND]}}),
        (
            'task',
            {
                'request': {
                    'action': 'start',
                    'slug': SLUG,
                    'payload': {'task_id': 'T1', 'change': START},
                }
            },
        ),
    )
    WRITTEN_TO = frozenset({'tickets', 'contract_commands', 'tasks', 'task_attempts'})

    @pytest.fixture
    def rows_before(
        self, connected_server: StateServer, repository_database: Database
    ) -> RowsByTable:
        recorded = connected_server.call(*self.RECORDED)
        assert [result.is_error for result in recorded] == [False] * len(self.RECORDED)
        return rows_of_every_table(repository_database)

    def test_the_tables_hold_rows_for_a_snapshot_to_read(self, rows_before: RowsByTable) -> None:
        assert {table for table, rows in rows_before.items() if rows} >= self.WRITTEN_TO

    def test_a_snapshot_leaves_every_table_with_the_rows_it_had(
        self,
        connected_server: StateServer,
        repository_database: Database,
        rows_before: RowsByTable,
    ) -> None:
        (taken,) = connected_server.call(('snapshot', {'request': {'slug': SLUG}}))

        assert not taken.is_error
        assert rows_of_every_table(repository_database) == rows_before
