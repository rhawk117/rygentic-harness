from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pydantic import TypeAdapter, ValidationError

from mightymodels.clock import now
from mightymodels.core.errors import StateError
from mightymodels.core.slug import Slug
from mightymodels.core.tests.in_memory_git import InMemoryGit
from mightymodels.tools.contract.schema import ContractCommand, Phase, Receipt
from mightymodels.tools.contract.schema import Outcome as ReceiptOutcome
from mightymodels.tools.contract.service import ContractService
from mightymodels.tools.task.schema import (
    AnyTaskStart,
    TaskMark,
    TaskRecord,
    TaskStart,
    TaskVerification,
    TaskView,
    TooLargeTaskStart,
)
from mightymodels.tools.task.service import TaskService, records_of
from mightymodels.tools.task.tests.in_memory import InMemoryTaskStore
from mightymodels.tools.ticket.schema import TicketAnswers

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
EITHER_START = TypeAdapter[TaskStart | TooLargeTaskStart](AnyTaskStart)
CHANGES: Mapping[str, tuple[Callable[..., TaskView], Callable[[object], object]]] = (
    MappingProxyType(
        {
            'start': (TaskService.start, EITHER_START.validate_python),
            'verify': (TaskService.verify, TaskVerification.model_validate),
            'mark': (TaskService.mark, TaskMark.model_validate),
        }
    )
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
    service, validated = CHANGES[action]
    return service(tasks, TICKET, task_id, validated(change))


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
    return repo.run('start', 'T1', by=worker, owned=['src/queue.py'], acceptance=['AC-1'])
