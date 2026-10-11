from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ValidationError

from mightymodels_plugin.clock import now
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.tools.contract.schema import ContractCommand, Phase, Receipt
from mightymodels_plugin.tools.contract.schema import Outcome as ReceiptOutcome
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.task.schema import (
    TaskMark,
    TaskRecord,
    TaskStart,
    TaskVerification,
    TaskView,
)
from mightymodels_plugin.tools.task.service import TaskService, records_of
from mightymodels_plugin.tools.task.tests.in_memory import InMemoryTaskStore
from mightymodels_plugin.tools.ticket.schema import TicketAnswers

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
ADVANCED, BLOCKED, REJECTED = 0, 1, 2
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'med',
        'compaction': False,
        'branch': 'fix/retry-queue',
        'context': ['drain loop sleeps between batches'],
    }
)


LISTINGS: Mapping[str, Callable[..., TaskView]] = MappingProxyType(
    {'show': TaskService.show, 'ready': TaskService.ready}
)
CHANGES: Mapping[str, tuple[Callable[..., TaskView], type[BaseModel]]] = MappingProxyType(
    {
        'start': (TaskService.start, TaskStart),
        'verify': (TaskService.verify, TaskVerification),
        'mark': (TaskService.mark, TaskMark),
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskOutcome:
    code: int
    out: str
    err: str


def act(
    tasks: TaskService, action: str, task_id: str | None, change: dict[str, object]
) -> TaskView:
    if action in LISTINGS:
        return LISTINGS[action](tasks, TICKET)
    service, model = CHANGES[action]
    return service(tasks, TICKET, task_id, model.model_validate(change))


def record_receipt(
    contracts: ContractService, command_id: str, outcome: str, head: str | None
) -> None:
    entry = Receipt(
        id=command_id,
        argv=('true',),
        outcome=ReceiptOutcome(outcome),
        exit=0,
        duration_ms=0,
        stdout_tail='',
        stderr_tail='',
        digest='',
        head=head,
        phase=Phase.TASK,
        at=now(),
    )
    with contracts.store.transaction() as repository:
        repository.record(TICKET, [entry])


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskRepo:
    tasks: TaskService
    contracts: ContractService
    store: InMemoryTaskStore
    history: InMemoryGit

    @property
    def root(self) -> Path:
        return self.tasks.workspace.root

    def head(self) -> str:
        return self.history.commits[-1].sha

    def commit(self, relative: str, *, unrelated: bool = False) -> str:
        return self.history.commit(relative, unrelated=unrelated)

    def run(self, action: str, task_id: str | None = None, **change: object) -> TaskOutcome:
        try:
            view = act(self.tasks, action, task_id, change)
        except (StateError, ValidationError) as error:
            return TaskOutcome(code=REJECTED, out='', err=str(error))
        return TaskOutcome(code=ADVANCED if view.advanced else BLOCKED, out=view.text, err='')

    @property
    def ticket_dir(self) -> Path:
        return self.root.joinpath('.mightymodels', SLUG)

    def task(self, task_id: str) -> TaskRecord:
        with self.store.transaction() as repository:
            return records_of(repository, TICKET)[task_id]

    def transitions(self) -> list[tuple[str, str]]:
        return [
            (recorded.transition.before, recorded.transition.after)
            for recorded in self.store.transitions
        ]

    def approve(self, *command_ids: str) -> None:
        commands = [
            ContractCommand(id=command_id, argv=('true',), approved_by='user')
            for command_id in command_ids
        ]
        self.contracts.approve(TICKET, commands)

    def receipt(self, command_id: str, outcome: str, head: str) -> None:
        record_receipt(self.contracts, command_id, outcome, head)
        if command_id.startswith('T'):
            task_id = command_id.split('.', 1)[0]
            self.done(task_id, head)

    def done(self, task_id: str, head: str) -> None:
        brief = self.ticket_dir.joinpath('briefs', f'task-{int(task_id[1:]):02d}.md')
        brief.parent.mkdir(exist_ok=True)
        asked = brief.read_text().split('## DONE', 1)[0] if brief.exists() else '## ASKED\n'
        brief.write_text(f'{asked}\n## DONE\ncommit: {head}\n')


def start(repo: TaskRepo, worker: str = 'engineer') -> TaskOutcome:
    return repo.run('start', 'T1', by=worker, owned=['src/queue.py'])
