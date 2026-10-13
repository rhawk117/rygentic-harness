"""A revision shaped like an option is refused before git is asked about it.

This test moved whole from test_task_service.py, which runs the task service on the stores and the
git history kept in memory. The refusal it asserts is `Git`'s own, so it stands on a real
repository and a SQLite store.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

import pytest
from mightymodels.core.errors import StateError
from mightymodels.core.slug import Slug
from mightymodels.core.tests.support import GitRunner
from mightymodels.tools.contract.schema import ContractCommand
from mightymodels.tools.contract.service import ContractService
from mightymodels.tools.task.schema import TaskStart, TaskVerification, TaskView
from mightymodels.tools.task.service import TaskService
from mightymodels.tools.ticket.schema import TicketAnswers
from mightymodels.tools.ticket.service import TicketService
from pydantic import BaseModel, ValidationError

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
ADVANCED, BLOCKED, REJECTED = 0, 1, 2
IDENTITY = ('-c', 'user.name=test', '-c', 'user.email=test@example.com')
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': 'fix/retry-queue',
        'context': ['drain loop sleeps between batches'],
    }
)
CHANGES: Mapping[str, tuple[Callable[..., TaskView], type[BaseModel]]] = MappingProxyType(
    {'start': (TaskService.start, TaskStart), 'verify': (TaskService.verify, TaskVerification)}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Outcome:
    code: int
    out: str
    err: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Repo:
    tasks: TaskService
    contracts: ContractService

    def run(self, action: str, task_id: str, **change: object) -> Outcome:
        service, model = CHANGES[action]
        try:
            view = service(self.tasks, TICKET, task_id, model.model_validate(change))
        except (StateError, ValidationError) as error:
            return Outcome(code=REJECTED, out='', err=str(error))
        return Outcome(code=ADVANCED if view.advanced else BLOCKED, out=view.text, err='')

    def approve(self, *command_ids: str) -> None:
        commands = [
            ContractCommand(id=command_id, argv=('true',), approved_by='user')
            for command_id in command_ids
        ]
        self.contracts.approve(TICKET, commands)


@pytest.fixture
def repo(
    task_service: TaskService,
    ticket_service: TicketService,
    contract_service: ContractService,
    git: GitRunner,
) -> Repo:
    root = task_service.workspace.root
    root.joinpath('src').mkdir()
    root.joinpath('src', 'queue.py').write_text('base\n', encoding='utf-8')
    git(root, *IDENTITY, 'add', 'src/queue.py')
    git(root, *IDENTITY, 'commit', '-q', '-m', 'change src/queue.py')
    ticket_service.write(TICKET, ANSWERS)
    ticket_service.validate(TICKET)
    return Repo(tasks=task_service, contracts=contract_service)


def start(repo: Repo, worker: str = 'engineer') -> Outcome:
    return repo.run('start', 'T1', by=worker, owned=['src/queue.py'], acceptance=['AC-1'])


def test_option_shaped_revisions_are_refused(repo: Repo) -> None:
    repo.approve('T1.AC-1')
    start(repo)
    outcome = repo.run('verify', 'T1', commit='--output=/tmp/pwned')
    assert outcome.code == REJECTED
    assert 'is not a plain revision name' in outcome.err
