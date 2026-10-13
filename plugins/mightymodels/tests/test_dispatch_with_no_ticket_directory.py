"""A repository with no ticket directory has no ticket, so the dispatch hook opens no state there:
the main thread's dispatch of an implementer gets no decision and the intern is refused for having
no task. A directory under `.mightymodels/` other than the archives is a ticket directory."""

from pathlib import Path

import pytest
from mightymodels_plugin.commands.tests.hook_inputs import Hook, dispatch
from mightymodels_plugin.core.data_directory import PLUGIN_DATA_VARIABLE
from mightymodels_plugin.core.workspace import STATE_DIRECTORY

SLUG = 'retry-queue'


class TestDispatchWithNoTicketDirectory:
    ENGINEER = 'mightymodels:workers:engineer'
    ARCHITECT = 'mightymodels:workers:architect'
    INTERN = 'mightymodels:workers:intern'

    @pytest.fixture
    def archives_only(self, hook_repository: Path) -> None:
        hook_repository.joinpath(STATE_DIRECTORY, 'archives').mkdir(parents=True)

    @pytest.fixture
    def ticket_directory(self, hook_repository: Path) -> None:
        hook_repository.joinpath(STATE_DIRECTORY, SLUG).mkdir(parents=True)

    @pytest.mark.parametrize('target', [ENGINEER, ARCHITECT])
    @pytest.mark.parametrize('layout', ['hook_repository', 'archives_only'])
    def test_an_implementer_dispatch_gets_no_decision_and_opens_no_state(
        self,
        target: str,
        layout: str,
        request: pytest.FixtureRequest,
        hook_command: Hook,
        data_directory: Path,
    ) -> None:
        request.getfixturevalue(layout)

        assert hook_command.run('dispatch-hook', dispatch(target)) == (0, '', '')
        assert not data_directory.exists()

    def test_it_gets_no_decision_even_where_the_state_could_not_be_read(
        self, hook_command: Hook
    ) -> None:
        hook_command.monkeypatch.delenv(PLUGIN_DATA_VARIABLE)

        assert hook_command.run('dispatch-hook', dispatch(self.ENGINEER)) == (0, '', '')

    def test_the_intern_is_refused_for_having_no_task_and_opens_no_state(
        self, hook_command: Hook, data_directory: Path
    ) -> None:
        _, out, _ = hook_command.run('dispatch-hook', dispatch(self.INTERN))

        assert 'no task is started for the intern' in out
        assert not data_directory.exists()

    @pytest.mark.usefixtures('ticket_directory')
    def test_with_a_ticket_directory_the_state_is_opened(
        self, hook_command: Hook, data_directory: Path
    ) -> None:
        assert hook_command.run('dispatch-hook', dispatch(self.ENGINEER)) == (0, '', '')
        assert data_directory.exists()

    @pytest.mark.usefixtures('ticket_directory')
    def test_with_a_ticket_directory_an_unreadable_state_refuses(self, hook_command: Hook) -> None:
        hook_command.monkeypatch.delenv(PLUGIN_DATA_VARIABLE)

        _, out, _ = hook_command.run('dispatch-hook', dispatch(self.ENGINEER))

        assert f'could not be read ({PLUGIN_DATA_VARIABLE} is not set' in out
