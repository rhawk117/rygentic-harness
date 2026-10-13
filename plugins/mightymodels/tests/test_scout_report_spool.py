"""The scout-report spool: files in the data directory that the next state tool call takes in."""

import json
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels_plugin.core.database import DATABASE_NAME, Database
from mightymodels_plugin.core.declarative import NAME_LIMIT, REPORT_LIMIT
from mightymodels_plugin.core.repository_key import (
    REPOSITORY_KEY_LIMIT,
    RepositoryKey,
    spool_file_prefix,
)
from mightymodels_plugin.tools.similarity.schema import SimilarityKind
from mightymodels_plugin.tools.similarity.spool import (
    CLOSING_PART,
    HANDBACK_PART,
    SPOOL_FILE_BYTES,
    SPOOL_FILES_PER_CALL,
)
from mightymodels_plugin.tools.similarity.tables import SimilarityRow
from mightymodels_plugin.tools.similarity.tests.spooled_reports import (
    OTHER_KEY,
    REPORT_TEXT,
    SEARCH,
    Report,
    named,
    rejected_files,
    report_for,
    scout_reports,
    spooled,
    words_of,
)
from mightymodels_plugin.tools.tests.support import StateServer, text_of, tree


def similarity_kinds(database: Database) -> list[str]:
    with database.transaction() as session:
        return list(session.scalars(sql.select(SimilarityRow.kind)))


class TestAReportFileOfThisRepository:
    @pytest.fixture
    def after_the_next_call(
        self, similarity_own_key: str, spool: Path, state_server: StateServer
    ) -> tuple[Path, str]:
        file = spooled(spool, named(similarity_own_key, 'first'), report_for(similarity_own_key))
        (searched,) = state_server.call(SEARCH)
        assert not searched.is_error
        return file, text_of(searched)

    def test_is_gone_from_the_spool(self, after_the_next_call: tuple[Path, str]) -> None:
        assert not after_the_next_call[0].exists()

    def test_is_found_by_the_search_of_that_call(
        self, after_the_next_call: tuple[Path, str]
    ) -> None:
        assert 'scout-report ' in after_the_next_call[1]

    @pytest.mark.usefixtures('after_the_next_call')
    def test_is_a_stored_scout_report_and_a_similarity_row(
        self, repository_database: Database
    ) -> None:
        (stored,) = scout_reports(repository_database)

        assert (stored.scout, stored.target, stored.report) == (
            'code-scout',
            'the drain loop',
            REPORT_TEXT,
        )
        assert similarity_kinds(repository_database) == [SimilarityKind.SCOUT_REPORT]

    def test_is_taken_in_by_any_tool_and_only_once(
        self,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        spooled(spool, named(similarity_own_key, 'first'), report_for(similarity_own_key))

        state_server.call(('crashout', {'request': {'action': 'stats'}}))
        state_server.call(SEARCH)

        assert len(scout_reports(repository_database)) == 1

    def test_has_its_secrets_redacted_before_it_is_stored(
        self,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        leaking = report_for(
            similarity_own_key, report='drain password=hunter2', target='token=abc123'
        )
        spooled(spool, named(similarity_own_key, 'leaking'), leaking)

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert 'hunter2' not in stored.report
        assert 'abc123' not in stored.target

    def test_several_files_are_taken_in_by_one_call(
        self,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        spooled(spool, named(similarity_own_key, 'first'), report_for(similarity_own_key))
        spooled(
            spool,
            named(similarity_own_key, 'second'),
            report_for(similarity_own_key, report=f'{REPORT_TEXT}s'),
        )

        state_server.call(SEARCH)

        assert len(scout_reports(repository_database)) == 2

    def test_is_not_taken_in_when_the_call_is_refused_before_it_runs(
        self, similarity_own_key: str, spool: Path, state_server: StateServer
    ) -> None:
        file = spooled(spool, named(similarity_own_key, 'first'), report_for(similarity_own_key))

        (refused,) = state_server.call(('similarity', {'request': {'action': 'delete'}}))

        assert refused.is_error
        assert file.exists()


class TestTheBoundOnAFileCount:
    @pytest.fixture
    def more_files_than_a_call_takes(self, similarity_own_key: str, spool: Path) -> int:
        count = SPOOL_FILES_PER_CALL + 2
        for number in range(count):
            spooled(
                spool,
                named(similarity_own_key, f'{number:04}'),
                report_for(similarity_own_key, report=f'{REPORT_TEXT} {number}'),
            )
        return count

    def test_a_call_takes_in_that_many_and_the_next_call_the_rest(
        self,
        more_files_than_a_call_takes: int,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        state_server.call(('crashout', {'request': {'action': 'stats'}}))
        after_one = len(scout_reports(repository_database))
        state_server.call(('crashout', {'request': {'action': 'stats'}}))

        assert after_one == SPOOL_FILES_PER_CALL
        assert len(scout_reports(repository_database)) == more_files_than_a_call_takes
        assert list(spool.glob('*.json')) == []


class TestFilesOfAnotherRepositoryWaitingBeyondTheBound:
    @pytest.fixture
    def own_file(self, similarity_own_key: str, spool: Path) -> Path:
        for number in range(SPOOL_FILES_PER_CALL + 2):
            name = f'{"0" * 64}-{number:04}.json'
            spooled(spool, name, report_for(OTHER_KEY, report=f'{REPORT_TEXT} {number}'))
        return spooled(spool, named(similarity_own_key, 'mine'), report_for(similarity_own_key))

    def test_do_not_keep_the_file_of_this_one_from_the_next_call(
        self,
        own_file: Path,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        assert min(spool.glob('*.json')) != own_file

        state_server.call(SEARCH)

        assert not own_file.exists()
        assert len(scout_reports(repository_database)) == 1
        assert len(list(spool.glob('*.json'))) == SPOOL_FILES_PER_CALL + 2


class TestALongReport:
    @pytest.fixture(params=['a\n"', '\U0001f600', '\u20ac', '\x01'], ids=ascii)
    def shape(self, request: pytest.FixtureRequest) -> str:
        return request.param

    @pytest.fixture
    def at_the_limit(
        self, similarity_own_key: str, spool: Path, state_server: StateServer
    ) -> tuple[Path, Report]:
        report = report_for(similarity_own_key, report=words_of(REPORT_LIMIT))
        file = spooled(spool, named(similarity_own_key, 'long'), report)
        state_server.call(SEARCH)
        return file, report

    @pytest.fixture
    def over_the_limit(
        self, similarity_own_key: str, spool: Path, state_server: StateServer
    ) -> Path:
        file = spooled(
            spool,
            named(similarity_own_key, 'longer'),
            report_for(similarity_own_key, report=words_of(REPORT_LIMIT + 1)),
        )
        state_server.call(SEARCH)
        return file

    def test_the_cap_leaves_room_in_the_file_for_the_longest_key_and_target_and_report(
        self, shape: str
    ) -> None:
        longest = report_for(
            'a' * REPOSITORY_KEY_LIMIT, target='t' * NAME_LIMIT, report=shape * REPORT_LIMIT
        )

        assert len(json.dumps(longest)) <= SPOOL_FILE_BYTES

    def test_a_report_of_the_limit_in_the_shape_is_stored_whole(
        self,
        shape: str,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        report = (shape * REPORT_LIMIT)[:REPORT_LIMIT]
        file = spooled(
            spool,
            named(similarity_own_key, 'shaped'),
            report_for(similarity_own_key, report=report),
        )

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert not file.exists()
        assert stored.report == report

    def test_at_the_limit_it_is_stored_whole(
        self, at_the_limit: tuple[Path, Report], repository_database: Database
    ) -> None:
        file, report = at_the_limit
        (stored,) = scout_reports(repository_database)

        assert not file.exists()
        assert stored.report == report['report']
        assert similarity_kinds(repository_database) == [SimilarityKind.SCOUT_REPORT]

    def test_over_the_limit_it_is_set_aside_and_stores_nothing(
        self, over_the_limit: Path, spool: Path, repository_database: Database
    ) -> None:
        assert not over_the_limit.exists()
        assert len(rejected_files(spool)) == 1
        assert scout_reports(repository_database) == []


class TestTheSpoolFileNamePrefix:
    WIDGETS_DIGEST = 'd782c874402305a00adcd10a58001c708039c0d0e86a047a74cc3616dd1fc713'

    def test_is_the_sha256_hex_of_the_key_followed_by_a_dash(self) -> None:
        assert spool_file_prefix(RepositoryKey('acme/widgets')) == f'{self.WIDGETS_DIGEST}-'


class TestWhereNothingIsToBeTakenIn:
    def test_a_call_creates_no_spool(
        self, connected_server: StateServer, data_directory: Path, spool: Path
    ) -> None:
        connected_server.call(('crashout', {'request': {'action': 'stats'}}), SEARCH)

        assert not spool.exists()
        assert sorted(tree(data_directory)) <= sorted(
            {DATABASE_NAME, f'{DATABASE_NAME}-wal', f'{DATABASE_NAME}-shm'}
        )


class TestAScoutThatHandedBackAndThenStopped:
    CLOSING = 'All done, the report is above.'

    def hand_back(self, own_key: str, spool: Path, unique: str = 'one') -> Path:
        return spooled(
            spool,
            named(own_key, f'{HANDBACK_PART}{unique}'),
            report_for(own_key, target='code-scout a1', report=REPORT_TEXT),
        )

    def stop(
        self, own_key: str, spool: Path, unique: str = 'one', target: str = 'code-scout a1'
    ) -> Path:
        return spooled(
            spool,
            named(own_key, f'{CLOSING_PART}{unique}'),
            report_for(own_key, target=target, report=self.CLOSING),
        )

    def test_waiting_together_one_report_is_stored_and_it_is_the_handed_back_one(
        self,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        stopped = self.stop(similarity_own_key, spool, unique='0')
        handed_back = self.hand_back(similarity_own_key, spool, unique='9')

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert min(stopped, handed_back) == handed_back
        assert stored.report == REPORT_TEXT
        assert list(spool.glob('*.json')) == []
        assert rejected_files(spool) == []

    def test_taken_in_before_the_stop_arrives_it_is_the_one_report(
        self,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        self.hand_back(similarity_own_key, spool)
        state_server.call(SEARCH)
        self.stop(similarity_own_key, spool)

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert stored.report == REPORT_TEXT
        assert list(spool.glob('*.json')) == []
        assert similarity_kinds(repository_database) == [SimilarityKind.SCOUT_REPORT]

    def test_a_stop_with_no_hand_back_is_stored(
        self,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        self.stop(similarity_own_key, spool)

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert stored.report == self.CLOSING

    def test_two_agents_give_two_reports(
        self,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        self.hand_back(similarity_own_key, spool)
        self.stop(similarity_own_key, spool)
        self.stop(similarity_own_key, spool, unique='two', target='code-scout b2')

        state_server.call(SEARCH)

        assert sorted(row.target for row in scout_reports(repository_database)) == [
            'code-scout a1',
            'code-scout b2',
        ]
