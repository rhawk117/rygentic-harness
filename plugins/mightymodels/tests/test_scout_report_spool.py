"""The scout-report spool: files in the data directory that the next state tool call takes in."""

import json
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels_plugin.core.database import DATABASE_NAME, SCHEMA_VERSION, Database
from mightymodels_plugin.core.declarative import NAME_LIMIT, REPORT_LIMIT
from mightymodels_plugin.core.repository_key import (
    REPOSITORY_KEY_LIMIT,
    RepositoryKey,
    spool_file_prefix,
)
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.similarity.schema import SimilarityKind
from mightymodels_plugin.tools.similarity.spool import (
    CLOSING_PART,
    HANDBACK_PART,
    REJECTED_DIRECTORY,
    SPOOL_DIRECTORY,
    SPOOL_FILE_BYTES,
    SPOOL_FILES_PER_CALL,
)
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow, SimilarityRow
from mightymodels_plugin.tools.tests.support import (
    StateServer,
    ToolCall,
    repository_key_of,
    text_of,
    tree,
)

type Report = Mapping[str, object]
type GitRunner = Callable[..., str]

OTHER_KEY = 'acme/gadgets'
REPORT_TEXT = 'the drain loop sleeps between every retry batch'
SEARCH: ToolCall = ('similarity', {'action': 'search', 'query': REPORT_TEXT})
CREDENTIALS = '://a:b@'
WORDS = 'the drain loop sleeps between every retry batch '


def words_of(length: int) -> str:
    return (WORDS * (length // len(WORDS) + 1))[:length]


def report_for(key: str, **given: object) -> Report:
    return {
        'repository_key': key,
        'scout': 'code-scout',
        'target': 'the drain loop',
        'report': REPORT_TEXT,
    } | given


def named(key: str, unique: str) -> str:
    return f'{spool_file_prefix(RepositoryKey(key))}{unique}.json'


def spooled(spool: Path, name: str, content: Report | bytes) -> Path:
    spool.mkdir(parents=True, exist_ok=True)
    file = spool.joinpath(name)
    file.write_bytes(content if isinstance(content, bytes) else json.dumps(content).encode())
    return file


def rejected_files(spool: Path) -> list[Path]:
    return sorted(spool.joinpath(REJECTED_DIRECTORY).glob('*'))


def scout_reports(database: Database) -> list[ScoutReportRow]:
    with database.transaction() as session:
        rows = list(session.scalars(sql.select(ScoutReportRow)))
        session.expunge_all()
    return rows


def similarity_kinds(database: Database) -> list[str]:
    with database.transaction() as session:
        return list(session.scalars(sql.select(SimilarityRow.kind)))


@pytest.fixture
def own_key(repository_workspace: Workspace) -> str:
    return repository_key_of(repository_workspace).root


class TestAReportFileOfThisRepository:
    @pytest.fixture
    def after_the_next_call(
        self, own_key: str, spool: Path, state_server: StateServer
    ) -> tuple[Path, str]:
        file = spooled(spool, named(own_key, 'first'), report_for(own_key))
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
        self, own_key: str, spool: Path, state_server: StateServer, repository_database: Database
    ) -> None:
        spooled(spool, named(own_key, 'first'), report_for(own_key))

        state_server.call(('crashout', {'action': 'stats'}))
        state_server.call(SEARCH)

        assert len(scout_reports(repository_database)) == 1

    def test_has_its_secrets_redacted_before_it_is_stored(
        self, own_key: str, spool: Path, state_server: StateServer, repository_database: Database
    ) -> None:
        leaking = report_for(own_key, report='drain password=hunter2', target='token=abc123')
        spooled(spool, named(own_key, 'leaking'), leaking)

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert 'hunter2' not in stored.report
        assert 'abc123' not in stored.target

    def test_several_files_are_taken_in_by_one_call(
        self, own_key: str, spool: Path, state_server: StateServer, repository_database: Database
    ) -> None:
        spooled(spool, named(own_key, 'first'), report_for(own_key))
        spooled(spool, named(own_key, 'second'), report_for(own_key, report=f'{REPORT_TEXT}s'))

        state_server.call(SEARCH)

        assert len(scout_reports(repository_database)) == 2

    def test_is_not_taken_in_when_the_call_is_refused_before_it_runs(
        self, own_key: str, spool: Path, state_server: StateServer
    ) -> None:
        file = spooled(spool, named(own_key, 'first'), report_for(own_key))

        (refused,) = state_server.call(('similarity', {'action': 'delete'}))

        assert refused.is_error
        assert file.exists()


class TestAMalformedFile:
    CASES = (
        pytest.param(b'not json', id='not-json'),
        pytest.param(b'', id='empty'),
        pytest.param(b'\xff\xfe', id='not-text'),
        pytest.param(b'[]', id='not-an-object'),
        pytest.param(json.dumps(report_for(OTHER_KEY, report='  ')).encode(), id='blank-report'),
        pytest.param(json.dumps(report_for(OTHER_KEY, scout='primary')).encode(), id='other-scout'),
        pytest.param(json.dumps(report_for(OTHER_KEY, extra=1)).encode(), id='extra-field'),
        pytest.param(json.dumps(report_for('../../escape')).encode(), id='key-with-separators'),
        pytest.param(json.dumps(report_for('')).encode(), id='empty-key'),
        pytest.param(
            json.dumps(report_for(OTHER_KEY, report=words_of(REPORT_LIMIT + 1))).encode(),
            id='report-over-its-column',
        ),
        pytest.param(b' ' * (SPOOL_FILE_BYTES + 1), id='over-the-file-size'),
    )

    @pytest.fixture
    def beside_a_good_file(
        self,
        request: pytest.FixtureRequest,
        own_key: str,
        spool: Path,
        state_server: StateServer,
    ) -> tuple[Path, bytes, bool]:
        file = spooled(spool, named(own_key, 'a-bad'), request.param)
        spooled(spool, named(own_key, 'b-good'), report_for(own_key))
        (searched,) = state_server.call(SEARCH)
        return file, request.param, searched.is_error

    @pytest.mark.parametrize('beside_a_good_file', CASES, indirect=True)
    def test_is_set_aside_with_its_bytes_and_the_call_succeeds(
        self, beside_a_good_file: tuple[Path, bytes, bool], spool: Path
    ) -> None:
        file, content, is_error = beside_a_good_file

        assert not is_error
        assert not file.exists()
        assert [kept.read_bytes() for kept in rejected_files(spool)] == [content]

    @pytest.mark.parametrize('beside_a_good_file', CASES, indirect=True)
    @pytest.mark.usefixtures('beside_a_good_file')
    def test_does_not_keep_the_good_file_beside_it_from_being_taken_in(
        self, spool: Path, repository_database: Database, own_key: str
    ) -> None:
        assert not spool.joinpath(named(own_key, 'b-good')).exists()
        assert len(scout_reports(repository_database)) == 1

    @pytest.mark.parametrize('beside_a_good_file', CASES[:1], indirect=True)
    @pytest.mark.usefixtures('beside_a_good_file')
    def test_is_kept_under_a_name_of_its_own_beside_one_set_aside_before(
        self, spool: Path, state_server: StateServer, own_key: str
    ) -> None:
        spooled(spool, named(own_key, 'a-bad'), b'not json again')

        state_server.call(SEARCH)

        assert sorted(kept.read_bytes() for kept in rejected_files(spool)) == [
            b'not json',
            b'not json again',
        ]

    def test_with_text_that_redaction_lengthens_past_its_column_is_set_aside(
        self, own_key: str, spool: Path, state_server: StateServer, repository_database: Database
    ) -> None:
        lengthened = words_of(REPORT_LIMIT - len(CREDENTIALS)) + CREDENTIALS
        file = spooled(spool, named(own_key, 'long'), report_for(own_key, report=lengthened))

        (searched,) = state_server.call(SEARCH)

        assert not searched.is_error
        assert not file.exists()
        assert len(rejected_files(spool)) == 1
        assert scout_reports(repository_database) == []


class TestAFileOfAnotherRepository:
    @pytest.fixture
    def gadgets(self, tmp_path: Path, data_directory: Path, git: GitRunner) -> StateServer:
        checkout = tmp_path.joinpath('gadgets')
        checkout.mkdir()
        git(checkout, 'init', '--quiet')
        git(checkout, 'remote', 'add', 'origin', 'git@github.com:acme/gadgets.git')
        return StateServer(root=checkout, data_directory=data_directory)

    @pytest.fixture
    def file_of_the_other(self, spool: Path) -> tuple[Path, bytes]:
        file = spooled(spool, named(OTHER_KEY, 'other'), report_for(OTHER_KEY))
        return file, file.read_bytes()

    @pytest.fixture
    def after_the_next_call(
        self, file_of_the_other: tuple[Path, bytes], state_server: StateServer
    ) -> tuple[Path, bytes]:
        state_server.call(SEARCH)
        return file_of_the_other

    def test_is_left_where_it_is_as_it_was(self, after_the_next_call: tuple[Path, bytes]) -> None:
        file, content = after_the_next_call

        assert file.read_bytes() == content

    @pytest.mark.usefixtures('after_the_next_call')
    def test_is_not_stored_for_this_repository(
        self, repository_database: Database, spool: Path
    ) -> None:
        assert scout_reports(repository_database) == []
        assert not spool.joinpath(REJECTED_DIRECTORY).exists()

    def test_is_taken_in_by_the_server_of_that_repository(
        self, after_the_next_call: tuple[Path, bytes], gadgets: StateServer
    ) -> None:
        gadgets.call(SEARCH)

        assert not after_the_next_call[0].exists()

    def test_under_a_name_of_that_repository_is_not_opened(
        self, spool: Path, state_server: StateServer
    ) -> None:
        unreadable = spooled(spool, named(OTHER_KEY, 'garbage'), b'garbage')

        state_server.call(SEARCH)

        assert unreadable.read_bytes() == b'garbage'
        assert not spool.joinpath(REJECTED_DIRECTORY).exists()


class TestAFileUnderTheDigestOfThisRepositoryThatNamesAnother:
    def test_is_set_aside_with_its_bytes(
        self, own_key: str, spool: Path, state_server: StateServer, repository_database: Database
    ) -> None:
        file = spooled(spool, named(own_key, 'misnamed'), report_for(OTHER_KEY))
        content = file.read_bytes()

        state_server.call(SEARCH)

        assert not file.exists()
        assert [kept.read_bytes() for kept in rejected_files(spool)] == [content]
        assert scout_reports(repository_database) == []


class TestAFileUnderAnyOtherName:
    @pytest.mark.parametrize(
        'name',
        [
            pytest.param('plain.json', id='no-digest'),
            pytest.param('{digest}.json', id='digest-without-separator'),
            pytest.param('x{digest}-late.json', id='digest-not-first'),
        ],
    )
    def test_is_never_read(
        self, name: str, own_key: str, spool: Path, state_server: StateServer
    ) -> None:
        digest = spool_file_prefix(RepositoryKey(own_key)).removesuffix('-')
        file = spooled(spool, name.format(digest=digest), report_for(own_key))

        state_server.call(SEARCH)

        assert file.exists()


class TestNoRepositoryKeyIsEverInAPath:
    @pytest.fixture
    def after_every_kind_of_file(
        self, own_key: str, spool: Path, state_server: StateServer, data_directory: Path
    ) -> list[str]:
        spooled(spool, named(own_key, 'own'), report_for(own_key))
        spooled(spool, named(OTHER_KEY, 'other'), report_for(OTHER_KEY))
        spooled(spool, named(own_key, 'traversal'), report_for('../../escape'))
        spooled(spool, named(own_key, 'garbage'), b'garbage')
        state_server.call(SEARCH)
        return sorted(tree(data_directory.parent))

    def test_a_path_holds_the_data_directory_and_fixed_names_and_nothing_a_file_says(
        self, after_every_kind_of_file: list[str], own_key: str
    ) -> None:
        paths = ' '.join(after_every_kind_of_file)

        assert 'escape' not in paths
        assert own_key.removeprefix('local:') not in paths
        assert 'gadgets' not in paths

    def test_the_file_naming_a_traversal_is_set_aside_inside_the_spool(
        self, after_every_kind_of_file: list[str], data_directory: Path
    ) -> None:
        set_aside = [path for path in after_every_kind_of_file if path.endswith('traversal.json')]

        assert len(set_aside) == 1
        assert Path(set_aside[0]).parent.parts[-2:] == (SPOOL_DIRECTORY, REJECTED_DIRECTORY)
        assert Path(set_aside[0]).parent.parent.parent.name == data_directory.name


class TestAFileThatIsNotARegularFile:
    def test_a_symlink_and_a_directory_are_left_alone(
        self, own_key: str, spool: Path, state_server: StateServer, tmp_path: Path
    ) -> None:
        outside = tmp_path.joinpath('outside.json')
        outside.write_text(json.dumps(report_for(own_key)), encoding='utf-8')
        spool.mkdir(parents=True)
        spool.joinpath(named(own_key, 'link')).symlink_to(outside)
        spool.joinpath(named(own_key, 'directory')).mkdir()

        (searched,) = state_server.call(SEARCH)

        assert not searched.is_error
        assert spool.joinpath(named(own_key, 'link')).is_symlink()
        assert spool.joinpath(named(own_key, 'directory')).is_dir()
        assert outside.exists()

    def test_a_file_that_does_not_end_in_json_is_not_read(
        self, own_key: str, spool: Path, state_server: StateServer
    ) -> None:
        file = spooled(
            spool,
            f'{spool_file_prefix(RepositoryKey(own_key))}half-written.tmp',
            report_for(own_key),
        )

        state_server.call(SEARCH)

        assert file.exists()


class TestTheBoundOnAFileCount:
    @pytest.fixture
    def more_files_than_a_call_takes(self, own_key: str, spool: Path) -> int:
        count = SPOOL_FILES_PER_CALL + 2
        for number in range(count):
            spooled(
                spool,
                named(own_key, f'{number:04}'),
                report_for(own_key, report=f'{REPORT_TEXT} {number}'),
            )
        return count

    def test_a_call_takes_in_that_many_and_the_next_call_the_rest(
        self,
        more_files_than_a_call_takes: int,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        state_server.call(('crashout', {'action': 'stats'}))
        after_one = len(scout_reports(repository_database))
        state_server.call(('crashout', {'action': 'stats'}))

        assert after_one == SPOOL_FILES_PER_CALL
        assert len(scout_reports(repository_database)) == more_files_than_a_call_takes
        assert list(spool.glob('*.json')) == []


class TestFilesOfAnotherRepositoryWaitingBeyondTheBound:
    @pytest.fixture
    def own_file(self, own_key: str, spool: Path) -> Path:
        for number in range(SPOOL_FILES_PER_CALL + 2):
            name = f'{"0" * 64}-{number:04}.json'
            spooled(spool, name, report_for(OTHER_KEY, report=f'{REPORT_TEXT} {number}'))
        return spooled(spool, named(own_key, 'mine'), report_for(own_key))

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
        self, own_key: str, spool: Path, state_server: StateServer
    ) -> tuple[Path, Report]:
        report = report_for(own_key, report=words_of(REPORT_LIMIT))
        file = spooled(spool, named(own_key, 'long'), report)
        state_server.call(SEARCH)
        return file, report

    @pytest.fixture
    def over_the_limit(self, own_key: str, spool: Path, state_server: StateServer) -> Path:
        file = spooled(
            spool, named(own_key, 'longer'), report_for(own_key, report=words_of(REPORT_LIMIT + 1))
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
        own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        report = (shape * REPORT_LIMIT)[:REPORT_LIMIT]
        file = spooled(spool, named(own_key, 'shaped'), report_for(own_key, report=report))

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
        connected_server.call(('crashout', {'action': 'stats'}), SEARCH)

        assert not spool.exists()
        assert sorted(tree(data_directory)) <= sorted(
            {DATABASE_NAME, f'{DATABASE_NAME}-wal', f'{DATABASE_NAME}-shm'}
        )


class TestAFileOfAnotherSchemaVersion:
    @pytest.fixture
    def refused_with_a_report_waiting(
        self, own_key: str, spool: Path, data_directory: Path
    ) -> dict[str, bytes]:
        data_directory.mkdir()
        with closing(sqlite3.connect(data_directory.joinpath(DATABASE_NAME))) as connection:
            connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION + 1}')
        spooled(spool, named(own_key, 'first'), report_for(own_key))
        return tree(data_directory)

    def test_leaves_the_database_and_the_spool_as_they_were(
        self,
        refused_with_a_report_waiting: dict[str, bytes],
        state_server: StateServer,
        data_directory: Path,
    ) -> None:
        (refused,) = state_server.call(SEARCH)

        assert refused.is_error
        assert tree(data_directory) == refused_with_a_report_waiting


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
        own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        stopped = self.stop(own_key, spool, unique='0')
        handed_back = self.hand_back(own_key, spool, unique='9')

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert min(stopped, handed_back) == handed_back
        assert stored.report == REPORT_TEXT
        assert list(spool.glob('*.json')) == []
        assert rejected_files(spool) == []

    def test_taken_in_before_the_stop_arrives_it_is_the_one_report(
        self,
        own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        self.hand_back(own_key, spool)
        state_server.call(SEARCH)
        self.stop(own_key, spool)

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert stored.report == REPORT_TEXT
        assert list(spool.glob('*.json')) == []
        assert similarity_kinds(repository_database) == [SimilarityKind.SCOUT_REPORT]

    def test_a_stop_with_no_hand_back_is_stored(
        self,
        own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        self.stop(own_key, spool)

        state_server.call(SEARCH)
        (stored,) = scout_reports(repository_database)

        assert stored.report == self.CLOSING

    def test_two_agents_give_two_reports(
        self,
        own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        self.hand_back(own_key, spool)
        self.stop(own_key, spool)
        self.stop(own_key, spool, unique='two', target='code-scout b2')

        state_server.call(SEARCH)

        assert sorted(row.target for row in scout_reports(repository_database)) == [
            'code-scout a1',
            'code-scout b2',
        ]
