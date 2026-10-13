"""The repository key: one per origin whatever the URL's form, the path hash for any other URL."""

import hashlib
import os
import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from mightymodels_plugin.core.database import DATABASE_NAME
from mightymodels_plugin.core.repository_key import (
    LOCAL_PREFIX,
    REPOSITORY_KEY_LIMIT,
    RepositoryKey,
    local_key,
    origin_key,
)
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.core.workspace import STATE_DIRECTORY, Checkout, git_at
from mightymodels_plugin.tools.tests.support import StateServer, ToolCall, text_of, tree

OWNER, NAME = 'acme', 'widgets'
KEY = RepositoryKey(f'{OWNER}/{NAME}')
PLAIN_KEY = re.compile(r'[a-z0-9._-]+/[a-z0-9._-]+')
PARENT_REFERENCES = {'.', '..'}
TOKEN = 'ghp_' + 'a' * 36
LONGEST_NAME = 'w' * (REPOSITORY_KEY_LIMIT - len(f'{OWNER}/'))
WRITE: ToolCall = (
    'ticket',
    {
        'request': {
            'action': 'write',
            'slug': 'retry-queue',
            'fields': {
                'summary': 'Retry queue drains slowly',
                'scope': 'med',
                'compaction': False,
                'branch': 'fix/retry-queue',
                'context': ['drain loop sleeps between batches'],
            },
        }
    },
)
URLS = st.one_of(
    st.text(),
    st.text().map('https://github.com/{}'.format),
    st.text().map('git@github.com:{}'.format),
    st.from_regex(r'[A-Za-z0-9._/%:@ -]{0,160}', fullmatch=True).map('ssh://host/{}'.format),
)


def is_two_plain_names_within_the_limit(key: RepositoryKey) -> bool:
    is_plain = PLAIN_KEY.fullmatch(key.root) is not None
    return (
        is_plain
        and len(key.root) <= REPOSITORY_KEY_LIMIT
        and PARENT_REFERENCES.isdisjoint(key.root.split('/'))
    )


def local_prefix_and_path_hash(toplevel: Path) -> str:
    return LOCAL_PREFIX + hashlib.sha256(os.fsencode(toplevel.resolve())).hexdigest()


def checkout_key(directory: Path) -> RepositoryKey:
    checkout = git_at(directory).checkout()
    assert isinstance(checkout, Checkout)
    return checkout.repository_key()


class TestOriginKey:
    @pytest.mark.parametrize(
        'url',
        [
            pytest.param('https://github.com/acme/widgets.git', id='https'),
            pytest.param('https://github.com/acme/widgets', id='https-without-the-suffix'),
            pytest.param('https://github.com/acme/widgets/', id='https-trailing-slash'),
            pytest.param('https://GitHub.com/Acme/Widgets.git', id='https-mixed-case'),
            pytest.param(
                f'https://user:{TOKEN}@github.com/acme/widgets.git', id='https-credential'
            ),
            pytest.param('http://github.com:8080/acme/widgets.git', id='http-with-a-port'),
            pytest.param('git@github.com:acme/widgets.git', id='scp'),
            pytest.param('github.com:acme/widgets', id='scp-without-a-user'),
            pytest.param('ssh://git@github.com/acme/widgets.git', id='ssh'),
            pytest.param('ssh://git@github.com:22/acme/widgets.git', id='ssh-with-a-port'),
            pytest.param('git://github.com/acme/widgets.git', id='git-protocol'),
        ],
    )
    def test_every_form_of_one_origin_gives_the_same_owner_and_name_key(self, url: str) -> None:
        assert origin_key(url) == KEY

    @pytest.mark.parametrize(
        'url',
        [
            pytest.param('https://gitlab.com/acme/widgets.git', id='https-on-another-host'),
            pytest.param('git@git.example.com:acme/widgets.git', id='scp-on-another-host'),
        ],
    )
    def test_the_same_owner_and_name_on_another_host_give_the_one_key(self, url: str) -> None:
        assert origin_key(url) == KEY

    @pytest.mark.parametrize(
        'url',
        [
            pytest.param('', id='empty'),
            pytest.param('../../etc/passwd', id='relative-path'),
            pytest.param('/srv/git/acme/widgets', id='local-path'),
            pytest.param('file:///srv/git/acme/widgets.git', id='file-url'),
            pytest.param('https://github.com/acme', id='one-name'),
            pytest.param('https://github.com/group/acme/widgets', id='three-names'),
            pytest.param('git@gitlab.com:group/sub/name.git', id='scp-three-names'),
            pytest.param('https://github.com/acme/..', id='parent-as-the-name'),
            pytest.param('https://github.com/../widgets', id='parent-as-the-owner'),
            pytest.param('https://github.com/acme/../../widgets', id='parents-in-the-path'),
            pytest.param('git@github.com:../widgets', id='scp-parent-as-the-owner'),
            pytest.param('https://github.com/acme/wid%2Fgets', id='encoded-separator'),
            pytest.param('https://github.com/acme/%2E%2E', id='encoded-parent'),
            pytest.param('https://github.com/acme\\widgets/x\\y', id='backslashes'),
            pytest.param('https://github.com/acme/wid gets', id='space'),
            pytest.param('https://github.com/acme/widgets\n', id='trailing-newline'),
            pytest.param('https://github.com/acme/widgets\x00', id='nul'),
            pytest.param('https://github.com/acme/widgets?ref=main', id='query'),
            pytest.param('https://github.com/acme/widgets#main', id='fragment'),
            pytest.param("https://github.com/acme/w'; DROP TABLE tickets; --", id='sql'),
            pytest.param('ext::sh -c touch% /tmp/pwned', id='remote-helper'),
            pytest.param('--upload-pack=touch /tmp/pwned', id='option'),
            pytest.param(f'https://github.com/{OWNER}/{LONGEST_NAME}w', id='over-the-limit'),
            pytest.param(f'https://github.com/{LOCAL_PREFIX}{"a" * 64}', id='the-reserved-prefix'),
        ],
    )
    def test_a_url_that_is_not_exactly_an_owner_and_a_name_has_no_key(self, url: str) -> None:
        assert origin_key(url) is None

    def test_a_key_of_exactly_the_limit_is_taken(self) -> None:
        key = origin_key(f'https://github.com/{OWNER}/{LONGEST_NAME}')

        assert isinstance(key, RepositoryKey)
        assert len(key.root) == REPOSITORY_KEY_LIMIT

    @given(url=URLS)
    def test_whatever_the_url_a_key_is_two_plain_names_it_spells_within_the_limit(
        self, url: str
    ) -> None:
        key = origin_key(url)

        assert key is None or is_two_plain_names_within_the_limit(key)
        assert key is None or key.root in url.lower()

    def test_a_key_is_neither_text_nor_a_path(self) -> None:
        assert not isinstance(KEY, (str, os.PathLike))


class TestARepositoryWithAnOrigin:
    HTTPS = 'https://github.com/acme/widgets.git'
    SSH = 'git@github.com:acme/widgets.git'
    NOT_EXACTLY_AN_OWNER_AND_A_NAME = (
        pytest.param('https://gitlab.com/group/sub/name.git', id='subgroup-path'),
        pytest.param('git@gitlab.com:group/sub/name.git', id='scp-subgroup-path'),
        pytest.param('https://git.example.com/name.git', id='one-name'),
        pytest.param('/srv/git/acme/widgets.git', id='local-path'),
        pytest.param('file:///srv/git/acme/widgets.git', id='file-url'),
        pytest.param(
            f'https://user:{TOKEN}@github.com/acme/../../widgets', id='parents-in-the-path'
        ),
        pytest.param(f'https://github.com/{LOCAL_PREFIX}{"a" * 64}', id='the-reserved-prefix'),
    )

    @pytest.fixture
    def origin(self) -> str:
        return self.HTTPS

    @pytest.fixture
    def repository(self, repository: Path, origin: str, git: GitRunner) -> Path:
        git(repository, 'remote', 'add', 'origin', origin)
        return repository

    @pytest.fixture
    def ssh_clone(self, tmp_path: Path, git: GitRunner) -> Path:
        clone = tmp_path.joinpath('ssh-clone')
        clone.mkdir()
        git(clone, 'init', '--quiet')
        git(clone, 'remote', 'add', 'origin', self.SSH)
        return clone

    @pytest.fixture
    def written_ticket_text(self, state_server: StateServer) -> str:
        (written,) = state_server.call(WRITE)
        return text_of(written)

    def test_an_https_clone_and_an_ssh_clone_of_one_origin_have_the_same_key(
        self, repository: Path, ssh_clone: Path
    ) -> None:
        assert checkout_key(repository) == checkout_key(ssh_clone) == KEY

    @pytest.mark.usefixtures('written_ticket_text')
    def test_no_file_or_directory_is_named_after_the_key(
        self, repository: Path, data_directory: Path
    ) -> None:
        state_files = tree(repository.joinpath(STATE_DIRECTORY))
        parts_of_state_paths = {part for path in state_files for part in Path(path).parts}

        assert state_files
        assert parts_of_state_paths.isdisjoint({OWNER, NAME})
        assert set(tree(data_directory)) == {DATABASE_NAME}

    @pytest.mark.parametrize('origin', NOT_EXACTLY_AN_OWNER_AND_A_NAME)
    def test_an_origin_that_is_not_exactly_an_owner_and_a_name_is_keyed_by_the_toplevel_path(
        self, repository: Path
    ) -> None:
        assert checkout_key(repository).root == local_prefix_and_path_hash(repository)


class TestARepositoryWithNoOrigin:
    @pytest.fixture
    def subdirectory(self, repository: Path) -> Path:
        below = repository.joinpath('src', 'queue')
        below.mkdir(parents=True)
        return below

    @pytest.fixture
    def another_repository(self, tmp_path: Path, git: GitRunner) -> Path:
        another = tmp_path.joinpath('another-repository')
        another.mkdir()
        git(another, 'init', '--quiet')
        return another

    def test_the_key_is_the_reserved_prefix_and_a_hash_of_the_toplevel_path(
        self, repository: Path
    ) -> None:
        assert checkout_key(repository).root == local_prefix_and_path_hash(repository)

    def test_the_key_is_the_same_from_a_subdirectory(
        self, repository: Path, subdirectory: Path
    ) -> None:
        assert checkout_key(subdirectory) == checkout_key(repository) == local_key(repository)

    def test_two_repositories_with_no_origin_have_different_keys(
        self, repository: Path, another_repository: Path
    ) -> None:
        assert checkout_key(repository) != checkout_key(another_repository)
