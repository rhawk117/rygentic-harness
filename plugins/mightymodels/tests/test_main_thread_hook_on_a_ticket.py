"""The main-thread hook on a real repository and SQLite: which paths count as in a ticket
directory once they are resolved, and which calls open no state."""

from pathlib import Path

import pytest
from mightymodels_plugin.commands.tests.hook_inputs import ENGINEER, Hook, tool_call
from mightymodels_plugin.commands.tests.ticket_checkout import (
    NO_DECISION,
    OTHER_SLUG,
    SLUG,
    TicketCheckout,
    decision_of,
    shown,
)
from mightymodels_plugin.core.data_directory import PLUGIN_DATA_VARIABLE
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import STATE_DIRECTORY

EDIT_TOOLS = ('Edit', 'Write')
OUTSIDE = (
    pytest.param('src/queue.py', id='a-source-file'),
    pytest.param(f'{STATE_DIRECTORY}/{SLUG}/../../src/queue.py', id='dot-dot-out-of-the-ticket'),
    pytest.param(f'{STATE_DIRECTORY}/{SLUG}/out/queue.py', id='a-link-out-of-the-ticket'),
    pytest.param(f'{STATE_DIRECTORY}/archives/{SLUG}.md', id='the-archives'),
    pytest.param(f'{STATE_DIRECTORY}/notes.md', id='beside-the-ticket-directories'),
    pytest.param(f'{STATE_DIRECTORY}/{SLUG}', id='the-ticket-directory-itself'),
)
INSIDE = (
    pytest.param(f'{STATE_DIRECTORY}/{SLUG}/briefs/task-01.md', id='a-brief'),
    pytest.param(f'src/../{STATE_DIRECTORY}/{SLUG}/ticket.yml', id='dot-dot-into-the-ticket'),
    pytest.param('shortcut/briefs/task-01.md', id='a-link-into-the-ticket'),
    pytest.param(f'{STATE_DIRECTORY}/{OTHER_SLUG}/notes.md', id='another-ticket-directory'),
)


@pytest.fixture
def in_the_repository(hook_command: Hook) -> None:
    hook_command.monkeypatch.chdir(hook_command.repository)


@pytest.fixture
def links(hook_repository: Path) -> None:
    ticket_directory = hook_repository.joinpath(STATE_DIRECTORY, SLUG)
    source = hook_repository.joinpath('src')
    ticket_directory.mkdir(parents=True, exist_ok=True)
    source.mkdir()
    ticket_directory.joinpath('out').symlink_to(source, target_is_directory=True)
    hook_repository.joinpath('shortcut').symlink_to(ticket_directory, target_is_directory=True)


@pytest.mark.usefixtures('checked_out_ticket', 'links')
@pytest.mark.parametrize('tool', EDIT_TOOLS)
class TestEditWithATicketOnTheBranch:
    @pytest.mark.usefixtures('in_the_repository')
    @pytest.mark.parametrize('path', OUTSIDE)
    def test_a_relative_path_that_resolves_outside_the_ticket_directories_is_asked(
        self, tool: str, path: str, hook_command: Hook
    ) -> None:
        code, out, err = hook_command.run('main-thread-hook', tool_call(tool, file_path=path))
        decision, reason = decision_of(out)

        assert (code, err, decision) == (0, '', 'ask')
        assert reason.startswith(f'mightymodels: ticket {SLUG} is unclosed on the checked-out')
        assert f'this {tool} of {path} is outside the ticket directories' in reason

    @pytest.mark.parametrize('path', OUTSIDE)
    def test_an_absolute_path_that_resolves_outside_them_is_asked(
        self, tool: str, path: str, hook_command: Hook
    ) -> None:
        absolute = str(hook_command.repository.joinpath(path))

        _, out, _ = hook_command.run('main-thread-hook', tool_call(tool, file_path=absolute))

        assert decision_of(out)[0] == 'ask'

    @pytest.mark.usefixtures('in_the_repository')
    @pytest.mark.parametrize('path', INSIDE)
    def test_a_relative_path_that_resolves_into_a_ticket_directory_gets_no_decision(
        self, tool: str, path: str, hook_command: Hook
    ) -> None:
        assert hook_command.run('main-thread-hook', tool_call(tool, file_path=path)) == NO_DECISION

    @pytest.mark.parametrize('path', INSIDE)
    def test_an_absolute_path_that_resolves_into_one_is_decided_without_the_state(
        self, tool: str, path: str, hook_command: Hook
    ) -> None:
        absolute = str(hook_command.repository.joinpath(path))
        hook_command.monkeypatch.delenv(PLUGIN_DATA_VARIABLE)

        assert (
            hook_command.run('main-thread-hook', tool_call(tool, file_path=absolute)) == NO_DECISION
        )

    def test_when_the_state_cannot_be_read_it_goes_ahead_with_one_line_saying_why(
        self, tool: str, hook_command: Hook
    ) -> None:
        outside = str(hook_command.repository.joinpath('src', 'queue.py'))
        hook_command.monkeypatch.delenv(PLUGIN_DATA_VARIABLE)

        warning = shown(hook_command.run('main-thread-hook', tool_call(tool, file_path=outside)))

        assert warning.startswith(
            f'mightymodels did not check the {tool} of {outside} against an unclosed ticket: the '
            f'tickets on the checked-out branch could not be read ({PLUGIN_DATA_VARIABLE} is not '
        )

    def test_a_plugin_workers_edit_gets_no_decision(self, tool: str, hook_command: Hook) -> None:
        outside = str(hook_command.repository.joinpath('src', 'queue.py'))

        assert (
            hook_command.run('main-thread-hook', tool_call(tool, ENGINEER, file_path=outside))
            == NO_DECISION
        )

    def test_with_another_branch_checked_out_it_gets_no_decision(
        self, tool: str, hook_command: Hook, ticket_checkout: TicketCheckout
    ) -> None:
        outside = str(ticket_checkout.root.joinpath('src', 'queue.py'))
        ticket_checkout.git('symbolic-ref', 'HEAD', 'refs/heads/another')

        assert (
            hook_command.run('main-thread-hook', tool_call(tool, file_path=outside)) == NO_DECISION
        )

    def test_with_a_second_ticket_on_the_branch_it_gets_one_line_naming_both(
        self, tool: str, hook_command: Hook, ticket_checkout: TicketCheckout
    ) -> None:
        outside = str(ticket_checkout.root.joinpath('src', 'queue.py'))
        ticket_checkout.stage(Slug(OTHER_SLUG))

        warning = shown(hook_command.run('main-thread-hook', tool_call(tool, file_path=outside)))

        assert warning.endswith(
            f'the checked-out branch has 2 unclosed tickets ({SLUG}, {OTHER_SLUG}), and the hook '
            'acts only when it has one'
        )


class TestCallsThatOpenNoState:
    OUTSIDE_EDIT = tool_call('Edit', file_path='/work/checkout/src/queue.py')
    PUSH = tool_call('Bash', command='git push')

    @pytest.fixture
    def ticket_directory(self, hook_repository: Path) -> Path:
        directory = hook_repository.joinpath(STATE_DIRECTORY, SLUG)
        directory.mkdir(parents=True)
        return directory

    @pytest.fixture
    def archives_only(self, hook_repository: Path) -> None:
        hook_repository.joinpath(STATE_DIRECTORY, 'archives').mkdir(parents=True)

    @pytest.mark.parametrize('layout', ['hook_repository', 'archives_only'])
    @pytest.mark.parametrize(
        'call',
        [
            pytest.param(OUTSIDE_EDIT, id='edit'),
            pytest.param(tool_call('Write', file_path='/work/checkout/src/queue.py'), id='write'),
            pytest.param(PUSH, id='push'),
        ],
    )
    def test_in_a_repository_with_no_ticket_directory_nothing_is_decided_or_opened(
        self,
        layout: str,
        call: str,
        request: pytest.FixtureRequest,
        hook_command: Hook,
        data_directory: Path,
    ) -> None:
        request.getfixturevalue(layout)

        assert hook_command.run('main-thread-hook', call) == NO_DECISION
        assert not data_directory.exists()

    @pytest.mark.parametrize('tool', EDIT_TOOLS)
    def test_an_edit_in_the_ticket_directory_is_decided_before_the_state_is_opened(
        self, tool: str, ticket_directory: Path, hook_command: Hook, data_directory: Path
    ) -> None:
        inside = str(ticket_directory.joinpath('briefs', 'task-01.md'))

        assert hook_command.run('main-thread-hook', tool_call(tool, file_path=inside)) == (
            NO_DECISION
        )
        assert not data_directory.exists()

    @pytest.mark.usefixtures('ticket_directory')
    @pytest.mark.parametrize(
        'call',
        [
            pytest.param(tool_call('Bash', command='uv run pytest'), id='bash-with-no-push'),
            pytest.param(tool_call('Bash', command='echo "git push"'), id='the-text-of-a-push'),
            pytest.param(tool_call('Bash', command='git pushd'), id='a-longer-word'),
            pytest.param(tool_call('Bash', command='git commit -m done'), id='a-commit'),
            pytest.param(tool_call('Bash', ENGINEER, command='git push'), id='a-workers-push'),
            pytest.param(
                tool_call('Edit', ENGINEER, file_path='/work/checkout/src/queue.py'),
                id='a-workers-edit',
            ),
            pytest.param(
                tool_call('Write', ENGINEER, file_path='/work/checkout/src/queue.py'),
                id='a-workers-write',
            ),
            pytest.param(tool_call('Read', file_path='/work/checkout/src/queue.py'), id='a-read'),
        ],
    )
    def test_with_a_ticket_directory_these_calls_are_decided_before_the_state_is_opened(
        self, call: str, hook_command: Hook, data_directory: Path
    ) -> None:
        assert hook_command.run('main-thread-hook', call) == NO_DECISION
        assert not data_directory.exists()

    @pytest.mark.usefixtures('ticket_directory')
    @pytest.mark.parametrize(
        'call', [pytest.param(OUTSIDE_EDIT, id='edit'), pytest.param(PUSH, id='push')]
    )
    def test_with_a_ticket_directory_an_outside_edit_and_a_push_open_the_state(
        self, call: str, hook_command: Hook, data_directory: Path
    ) -> None:
        assert hook_command.run('main-thread-hook', call) == NO_DECISION
        assert data_directory.exists()
