"""A state database whose `tickets` table was made before `auto_escalate` was added to it: the
open adds the column, and a ticket staged before reads with it off."""

import sqlite3
from collections.abc import Generator
from contextlib import closing
from pathlib import Path

import pytest
from mightymodels_plugin.core.database import (
    DATABASE_NAME,
    SCHEMA_VERSION,
    Database,
    open_database,
)
from mightymodels_plugin.core.repository_key import local_key
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.tests.support import table_of
from mightymodels_plugin.tools.ticket.repository import ticket_store
from mightymodels_plugin.tools.ticket.schema import TicketStatus
from mightymodels_plugin.tools.ticket.tables import TicketRow


class TestAFileMadeBeforeAutoEscalate:
    TICKET = Slug('retry-queue')
    TICKETS_AS_FIRST_MADE = (
        'CREATE TABLE tickets ('
        'repository_key VARCHAR(140) NOT NULL, '
        'slug VARCHAR(64) NOT NULL, '
        "status VARCHAR(32) DEFAULT 'staged' NOT NULL, "
        'ticket VARCHAR(255) NOT NULL, '
        'summary VARCHAR(4000) NOT NULL, '
        'branch VARCHAR(255) NOT NULL, '
        'scope VARCHAR(32) NOT NULL, '
        'plan_first BOOLEAN NOT NULL, '
        'issue INTEGER, '
        'jira VARCHAR(255), '
        'models JSON NOT NULL, '
        'context JSON NOT NULL, '
        "investigations JSON DEFAULT '[]' NOT NULL, "
        "validated_at VARCHAR(25) DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')) NOT NULL, "
        'CONSTRAINT pk_tickets PRIMARY KEY (repository_key, slug), '
        'CONSTRAINT uq_tickets_repository_key UNIQUE (repository_key, ticket))'
    )
    STAGED_THEN = (
        'INSERT INTO tickets '
        '(repository_key, slug, ticket, summary, branch, scope, plan_first, models, context) '
        "VALUES (?, ?, '.mightymodels/retry-queue/ticket.yml', 'Retry queue drains slowly', "
        "'fix/retry-queue', 'med', 0, '{}', '[]')"
    )
    COLUMNS_STORED = "SELECT name FROM pragma_table_info('tickets')"

    @pytest.fixture
    def made_before_the_column(self, tmp_path: Path) -> Path:
        database_file = tmp_path.joinpath(DATABASE_NAME)
        with closing(sqlite3.connect(database_file)) as connection:
            connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
            connection.execute(self.TICKETS_AS_FIRST_MADE)
            connection.execute(self.STAGED_THEN, (local_key(tmp_path).root, self.TICKET.root))
            connection.commit()
        return database_file

    @pytest.fixture
    def opened(self, made_before_the_column: Path, tmp_path: Path) -> Generator[Database]:
        with open_database(made_before_the_column, local_key(tmp_path), ROW_TYPES) as database:
            yield database

    def test_the_ticket_staged_in_it_reads_with_auto_escalate_off(self, opened: Database) -> None:
        with ticket_store(opened).transaction() as repository:
            staged = repository.staged_ticket(self.TICKET)

        assert (staged.status, staged.ticket.auto_escalate) == (TicketStatus.STAGED, False)

    def test_a_ticket_restaged_in_it_keeps_auto_escalate_on(self, opened: Database) -> None:
        with ticket_store(opened).transaction() as repository:
            section = repository.staged_ticket(self.TICKET).ticket
            repository.stage(self.TICKET, section.model_copy(update={'auto_escalate': True}), [])

        with ticket_store(opened).transaction() as repository:
            assert repository.staged_ticket(self.TICKET).ticket.auto_escalate is True

    @pytest.mark.usefixtures('opened')
    def test_opened_again_it_holds_the_columns_a_new_file_holds_in_their_order(
        self, made_before_the_column: Path, tmp_path: Path
    ) -> None:
        opening = open_database(made_before_the_column, local_key(tmp_path), ROW_TYPES)
        with opening as opened_again, opened_again.engine.connect() as connection:
            stored = list(connection.exec_driver_sql(self.COLUMNS_STORED).scalars())

        assert stored == [column.name for column in table_of(TicketRow).columns]
