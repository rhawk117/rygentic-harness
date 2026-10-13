import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from mightymodels.core.database import DATABASE_NAME, SCHEMA_VERSION, Database
from mightymodels.core.declarative import REPORT_LIMIT
from mightymodels.core.repository_key import RepositoryKey, spool_file_prefix
from mightymodels.core.tests.support import GitRunner
from mightymodels.tools.similarity.spool import (
    REJECTED_DIRECTORY,
    SPOOL_DIRECTORY,
    SPOOL_FILE_BYTES,
)
from mightymodels.tools.similarity.tests.spooled_reports import (
    OTHER_KEY,
    SEARCH,
    named,
    rejected_files,
    report_for,
    scout_reports,
    spooled,
    words_of,
)
from mightymodels.tools.tests.support import StateServer, tree

CREDENTIALS = '://a:b@'


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
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
    ) -> tuple[Path, bytes, bool]:
        file = spooled(spool, named(similarity_own_key, 'a-bad'), request.param)
        spooled(spool, named(similarity_own_key, 'b-good'), report_for(similarity_own_key))
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
        self, spool: Path, repository_database: Database, similarity_own_key: str
    ) -> None:
        assert not spool.joinpath(named(similarity_own_key, 'b-good')).exists()
        assert len(scout_reports(repository_database)) == 1

    @pytest.mark.parametrize('beside_a_good_file', CASES[:1], indirect=True)
    @pytest.mark.usefixtures('beside_a_good_file')
    def test_is_kept_under_a_name_of_its_own_beside_one_set_aside_before(
        self, spool: Path, state_server: StateServer, similarity_own_key: str
    ) -> None:
        spooled(spool, named(similarity_own_key, 'a-bad'), b'not json again')

        state_server.call(SEARCH)

        assert sorted(kept.read_bytes() for kept in rejected_files(spool)) == [
            b'not json',
            b'not json again',
        ]

    def test_with_text_that_redaction_lengthens_past_its_column_is_set_aside(
        self,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        lengthened = words_of(REPORT_LIMIT - len(CREDENTIALS)) + CREDENTIALS
        file = spooled(
            spool,
            named(similarity_own_key, 'long'),
            report_for(similarity_own_key, report=lengthened),
        )

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
        self,
        similarity_own_key: str,
        spool: Path,
        state_server: StateServer,
        repository_database: Database,
    ) -> None:
        file = spooled(spool, named(similarity_own_key, 'misnamed'), report_for(OTHER_KEY))
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
        self, name: str, similarity_own_key: str, spool: Path, state_server: StateServer
    ) -> None:
        digest = spool_file_prefix(RepositoryKey(similarity_own_key)).removesuffix('-')
        file = spooled(spool, name.format(digest=digest), report_for(similarity_own_key))

        state_server.call(SEARCH)

        assert file.exists()


class TestNoRepositoryKeyIsEverInAPath:
    @pytest.fixture
    def after_every_kind_of_file(
        self, similarity_own_key: str, spool: Path, state_server: StateServer, data_directory: Path
    ) -> list[str]:
        spooled(spool, named(similarity_own_key, 'own'), report_for(similarity_own_key))
        spooled(spool, named(OTHER_KEY, 'other'), report_for(OTHER_KEY))
        spooled(spool, named(similarity_own_key, 'traversal'), report_for('../../escape'))
        spooled(spool, named(similarity_own_key, 'garbage'), b'garbage')
        state_server.call(SEARCH)
        return sorted(tree(data_directory.parent))

    def test_a_path_holds_the_data_directory_and_fixed_names_and_nothing_a_file_says(
        self, after_every_kind_of_file: list[str], similarity_own_key: str
    ) -> None:
        paths = ' '.join(after_every_kind_of_file)

        assert 'escape' not in paths
        assert similarity_own_key.removeprefix('local:') not in paths
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
        self, similarity_own_key: str, spool: Path, state_server: StateServer, tmp_path: Path
    ) -> None:
        outside = tmp_path.joinpath('outside.json')
        outside.write_text(json.dumps(report_for(similarity_own_key)), encoding='utf-8')
        spool.mkdir(parents=True)
        spool.joinpath(named(similarity_own_key, 'link')).symlink_to(outside)
        spool.joinpath(named(similarity_own_key, 'directory')).mkdir()

        (searched,) = state_server.call(SEARCH)

        assert not searched.is_error
        assert spool.joinpath(named(similarity_own_key, 'link')).is_symlink()
        assert spool.joinpath(named(similarity_own_key, 'directory')).is_dir()
        assert outside.exists()

    def test_a_file_that_does_not_end_in_json_is_not_read(
        self, similarity_own_key: str, spool: Path, state_server: StateServer
    ) -> None:
        file = spooled(
            spool,
            f'{spool_file_prefix(RepositoryKey(similarity_own_key))}half-written.tmp',
            report_for(similarity_own_key),
        )

        state_server.call(SEARCH)

        assert file.exists()


class TestAFileOfAnotherSchemaVersion:
    @pytest.fixture
    def refused_with_a_report_waiting(
        self, similarity_own_key: str, spool: Path, data_directory: Path
    ) -> dict[str, bytes]:
        data_directory.mkdir()
        with closing(sqlite3.connect(data_directory.joinpath(DATABASE_NAME))) as connection:
            connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION + 1}')
        spooled(spool, named(similarity_own_key, 'first'), report_for(similarity_own_key))
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
