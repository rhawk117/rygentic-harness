"""The ticket service in a real checkout: the state directory kept out of git.

These three tests moved whole from test_ticket_service.py, which runs on the stores kept in
memory. They read `.git/info/exclude`, a worktree and a directory that is no repository, so they
stand on a real repository and a SQLite store.
"""

from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.tools.ticket.schema import TicketAnswers, TicketView
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.tools.ticket.tests.support import ticket_service_at
from pydantic import ValidationError

type Command = Callable[[TicketService, object], TicketView]

REJECTED = 2
SLUG = 'retry-queue'
TICKET = Slug(SLUG)
ANSWERS = {
    'summary': 'Retry queue drains at a tenth of its rate after 2am',
    'scope': 'med',
    'compaction': False,
    'branch': 'fix/retry-queue',
    'context': ['drain loop sleeps between batches', 'user: correlates with compaction'],
    'issue': 42,
}


def write(tickets: TicketService, answers: object) -> TicketView:
    return tickets.write(TICKET, TicketAnswers.model_validate(answers))


def validate(tickets: TicketService, _answers: object) -> TicketView:
    return tickets.validate(TICKET)


COMMANDS: Mapping[str, Command] = MappingProxyType({'write': write, 'validate': validate})


@dataclass(frozen=True, slots=True, kw_only=True)
class Outcome:
    code: int
    out: str
    err: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    tickets: TicketService

    @property
    def root(self) -> Path:
        return self.tickets.workspace.root

    def run(self, command: str, answers: object = None) -> Outcome:
        try:
            view = COMMANDS[command](self.tickets, answers)
        except (StateError, ValidationError) as error:
            return Outcome(code=REJECTED, out='', err=str(error))
        return Outcome(code=0, out=view.text, err='')

    @property
    def ticket(self) -> Path:
        return self.root.joinpath('.mightymodels', SLUG, 'ticket.yml')


@pytest.fixture
def workspace(ticket_service: TicketService) -> Workspace:
    return Workspace(tickets=ticket_service)


@pytest.fixture
def worktree_workspace(
    repository: Path, tmp_path: Path, data_directory: Path, git: GitRunner
) -> Generator[Workspace]:
    identity = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
    git(repository, *identity, 'commit', '--quiet', '--allow-empty', '-m', 'base')
    worktree = tmp_path.joinpath('feature')
    git(repository, 'worktree', 'add', '--quiet', str(worktree), '-b', 'feature')
    repository.joinpath('.git', 'info', 'exclude').unlink(missing_ok=True)
    with ticket_service_at(worktree, data_directory) as tickets:
        yield Workspace(tickets=tickets)


@pytest.fixture
def workspace_outside_a_repository(tmp_path: Path, data_directory: Path) -> Generator[Workspace]:
    directory = tmp_path.joinpath('plain-directory')
    directory.mkdir()
    with ticket_service_at(directory, data_directory) as tickets:
        yield Workspace(tickets=tickets)


def test_write_keeps_mightymodels_out_of_git_once(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    workspace.run('validate')
    exclude = workspace.root.joinpath('.git', 'info', 'exclude')
    assert exclude.read_text(encoding='utf-8').splitlines().count('.mightymodels/') == 1


def test_exclude_goes_to_the_common_dir_from_a_worktree(
    worktree_workspace: Workspace, repository: Path
) -> None:
    worktree_workspace.run('write', ANSWERS)
    exclude = repository.joinpath('.git', 'info', 'exclude')
    assert exclude.read_text(encoding='utf-8') == '.mightymodels/\n'


def test_outside_a_repository_the_ticket_is_still_written(
    workspace_outside_a_repository: Workspace,
) -> None:
    outcome = workspace_outside_a_repository.run('write', ANSWERS)
    assert outcome.code == 0
    assert workspace_outside_a_repository.ticket.is_file()
    assert not workspace_outside_a_repository.root.joinpath('.git').exists()
