"""The ticket service on the stores kept in memory, with no repository and no database.

The tests that need a real checkout are in test_ticket_in_a_repository.py.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels.core.errors import StateError
from mightymodels.core.slug import Slug
from mightymodels.core.tests.in_memory_git import InMemoryGit
from mightymodels.tools.task.schema import Implementer, Status, TaskStart
from mightymodels.tools.task.service import TaskService
from mightymodels.tools.task.store import Transition
from mightymodels.tools.ticket.schema import (
    BranchChoice,
    TicketAnswers,
    TicketContext,
    TicketView,
    Tracker,
    WorkUnit,
)
from mightymodels.tools.ticket.service import DetachedHeadError, TicketService
from mightymodels.tools.ticket.tests.in_memory import InMemoryTicketStore
from mightymodels.tools.ticket.ticket_file import parse
from pydantic import ValidationError

type Command = Callable[[TicketService, object], TicketView]

REJECTED = 2
SLUG = 'retry-queue'
TICKET = Slug(SLUG)
CONTEXT = ['drain loop sleeps between batches', 'user: correlates with compaction']
ANSWERS = {
    'summary': 'Retry queue drains at a tenth of its rate after 2am',
    'scope': 'med',
    'compaction': False,
    'branch': 'fix/retry-queue',
    'context': CONTEXT,
    'issue': 42,
}
STARTED_INVESTIGATION = '20260928-inv-a'
LAST_HANDOFF_LINE = '  worktrees-okay: false'
FIRST_TASK_VERIFIED = Transition(
    task_id='T1',
    before=Status.IN_PROGRESS,
    after=Status.VERIFIED,
    reasons=(),
    head=None,
    at='2026-09-28T00:00:00+00:00',
)


def write(tickets: TicketService, answers: object) -> TicketView:
    return tickets.write(TICKET, TicketAnswers.model_validate(answers))


def validate(tickets: TicketService, _answers: object) -> TicketView:
    return tickets.validate(TICKET)


def show(tickets: TicketService, _answers: object) -> TicketView:
    return tickets.show(TICKET)


def update_context(tickets: TicketService, answers: object) -> TicketView:
    return tickets.update_context(TICKET, TicketContext.model_validate(answers))


COMMANDS: Mapping[str, Command] = MappingProxyType(
    {'write': write, 'validate': validate, 'show': show, 'update-context': update_context}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Outcome:
    code: int
    out: str
    err: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    tickets: TicketService
    tasks: TaskService

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

    def unit(self) -> WorkUnit:
        with self.tickets.store.transaction() as repository:
            return repository.staged_ticket(TICKET)

    def task_statuses(self) -> dict[str, str]:
        return {record.id: record.status for record in self.tasks.show(TICKET).tasks}

    def verify_first_task(self) -> None:
        change = TaskStart(by=Implementer.ENGINEER, owned=('src/queue.py',), acceptance=('AC-1',))
        self.tasks.start(TICKET, 'T1', change)
        with self.tasks.store.transaction() as repository:
            repository.record_verification(TICKET, FIRST_TASK_VERIFIED, 'HEAD')

    def edit(self, old: str, new: str) -> None:
        text = self.ticket.read_text(encoding='utf-8')
        self.ticket.write_text(text.replace(old, new), encoding='utf-8')


@pytest.fixture
def workspace(
    in_memory_ticket_service: TicketService, in_memory_task_service: TaskService
) -> Workspace:
    return Workspace(tickets=in_memory_ticket_service, tasks=in_memory_task_service)


@pytest.fixture
def started_investigation(in_memory_ticket_store: InMemoryTicketStore) -> None:
    in_memory_ticket_store.recorded_investigations.add(Slug(STARTED_INVESTIGATION))


@pytest.mark.parametrize(
    ('scope', 'models'),
    [
        ('sm', ('sonnet', 'opus')),
        ('med', ('sonnet', 'opus')),
        ('large', ('sonnet', 'opus')),
    ],
)
def test_write_derives_the_implementer_models_from_scope(
    workspace: Workspace, scope: str, models: tuple[str, str]
) -> None:
    engineer, architect = models
    outcome = workspace.run('write', {**ANSWERS, 'scope': scope})
    text = workspace.ticket.read_text(encoding='utf-8')
    assert outcome.code == 0
    assert f'  engineer: "{engineer}"' in text
    assert f'  architect: "{architect}"' in text


def test_write_derives_plan_first_from_the_compaction_answer(
    workspace: Workspace,
) -> None:
    workspace.run('write', {**ANSWERS, 'compaction': True})
    assert '  plan-first: true' in workspace.ticket.read_text(encoding='utf-8')


def test_write_refuses_to_overwrite_a_tweaked_ticket(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    outcome = workspace.run('write', ANSWERS)
    assert outcome.code == REJECTED
    assert 'edit it by hand' in outcome.err


def test_the_current_branch_cannot_be_named_on_a_detached_head(workspace: Workspace) -> None:
    detached = replace(workspace.tickets, git=InMemoryGit(branch=None))
    with pytest.raises(DetachedHeadError) as raised:
        detached.branch_named(BranchChoice.CURRENT, '')
    assert str(raised.value) == (
        'HEAD is detached, so there is no current branch; ask for a branch name'
    )


def test_write_rejects_incomplete_answers(workspace: Workspace) -> None:
    outcome = workspace.run('write', {'scope': 'sm'})
    assert outcome.code == REJECTED
    assert 'summary' in outcome.err
    assert not workspace.ticket.exists()


def test_validate_stages_the_work_unit(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    outcome = workspace.run('validate')
    unit = workspace.unit()
    assert 'status staged' in outcome.out
    assert (unit.status, unit.ticket.branch) == ('staged', 'fix/retry-queue')
    assert unit.ticket.tracker == Tracker(issue=42, jira=None)
    assert unit.ticket.models['uncle-bob'] == 'opus'


def test_hand_edits_inside_the_subset_validate(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    workspace.edit('  scope: "med"', '  scope: large   # bumped after review')
    outcome = workspace.run('validate')
    assert outcome.code == 0
    assert workspace.unit().ticket.scope == 'large'


def test_syntax_outside_the_subset_is_refused_with_its_line(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    workspace.edit('reference-urls:', 'reference-urls: [a, b]')
    outcome = workspace.run('validate')
    assert outcome.code == REJECTED
    assert 'ticket.yml:' in outcome.err
    assert 'unsupported YAML syntax' in outcome.err


def test_retired_worker_keys_are_refused(workspace: Workspace) -> None:
    workspace.run('write', ANSWERS)
    workspace.edit('subagent-models:\n', 'subagent-models:\n  scout: haiku\n')
    outcome = workspace.run('validate')
    assert outcome.code == REJECTED
    assert "unknown workers ['scout']" in outcome.err


def test_linked_investigations_must_exist(workspace: Workspace) -> None:
    outcome = workspace.run('write', {**ANSWERS, 'investigations': ['20260928-missing']})
    assert outcome.code == REJECTED
    assert 'investigation 20260928-missing has no ledger' in outcome.err
    assert 'ledger file' not in outcome.err


@pytest.mark.usefixtures('started_investigation')
def test_revalidation_keeps_progress_and_only_adds_links(workspace: Workspace) -> None:
    workspace.run('write', {**ANSWERS, 'investigations': [STARTED_INVESTIGATION]})
    workspace.run('validate')
    workspace.verify_first_task()
    workspace.run('validate')
    refreshed = workspace.unit()
    assert (refreshed.status, workspace.task_statuses()) == ('in-progress', {'T1': 'verified'})
    assert list(refreshed.investigations) == [STARTED_INVESTIGATION]


def test_hashes_and_colons_inside_quoted_values_survive(workspace: Workspace) -> None:
    summary = 'Quote "x" and colon: y # not a comment'
    workspace.run('write', {**ANSWERS, 'summary': summary, 'context': ['a: b', 'c # d']})
    workspace.edit('context:\n', 'context:   # rollup lines\n')
    outcome = workspace.run('validate')
    assert outcome.code == 0
    assert workspace.unit().ticket.summary == summary


class TestValidate:
    def test_validate_needs_a_written_ticket(self, workspace: Workspace) -> None:
        outcome = workspace.run('validate')

        assert outcome.code == REJECTED
        assert 'run write first' in outcome.err

    @pytest.mark.parametrize(
        ('old', 'new', 'problem'),
        [
            pytest.param(
                'issue-number: 42',
                'issue-number: "42"',
                'issue-number must be a number',
                id='issue',
            ),
            pytest.param('  jira-key:', '  jira-key: 7', 'tracker.jira', id='jira'),
            pytest.param(
                '  branch-name: "fix/retry-queue"', '  branch-name: 7', 'branch', id='branch'
            ),
            pytest.param(
                'investigations:',
                'investigations: none',
                'investigations must be a list',
                id='links',
            ),
            pytest.param('  plan-first: false', '  plan-first: no', 'plan-first', id='plan-first'),
            pytest.param(
                LAST_HANDOFF_LINE,
                f'{LAST_HANDOFF_LINE}\n  auto-escalate: yes',
                'auto-escalate must be a bool',
                id='auto-escalate-a-word',
            ),
            pytest.param(
                LAST_HANDOFF_LINE,
                f'{LAST_HANDOFF_LINE}\n  auto-escalate: 1',
                'auto-escalate must be a bool',
                id='auto-escalate-a-number',
            ),
            pytest.param(
                LAST_HANDOFF_LINE,
                f'{LAST_HANDOFF_LINE}\n  auto-escalate:',
                'auto-escalate must be a bool',
                id='auto-escalate-empty',
            ),
            pytest.param(
                'task: "retry-queue"', 'task: "other"', "task must be 'retry-queue'", id='task'
            ),
        ],
    )
    def test_a_hand_edit_of_the_wrong_type_is_refused_by_name(
        self, workspace: Workspace, old: str, new: str, problem: str
    ) -> None:
        workspace.run('write', ANSWERS)
        workspace.edit(old, new)

        outcome = workspace.run('validate')

        assert outcome.code == REJECTED
        assert problem in outcome.err
        assert workspace.run('show').code == REJECTED

    def test_a_ticket_without_auto_escalate_is_valid_and_reads_as_off(
        self, workspace: Workspace
    ) -> None:
        workspace.run('write', ANSWERS)

        outcome = workspace.run('validate')

        assert outcome.code == 0
        assert 'auto-escalate' not in workspace.ticket.read_text(encoding='utf-8')
        assert workspace.unit().ticket.auto_escalate is False

    @pytest.mark.parametrize(
        ('written', 'stored'),
        [pytest.param('true', True, id='on'), pytest.param('false', False, id='off')],
    )
    def test_auto_escalate_under_handoff_context_is_stored_as_it_is_written(
        self, workspace: Workspace, written: str, stored: bool
    ) -> None:
        workspace.run('write', ANSWERS)
        workspace.edit(LAST_HANDOFF_LINE, f'{LAST_HANDOFF_LINE}\n  auto-escalate: {written}')

        outcome = workspace.run('validate')

        assert outcome.code == 0
        assert workspace.unit().ticket.auto_escalate is stored

    def test_auto_escalate_taken_out_again_reads_as_off(self, workspace: Workspace) -> None:
        turned_on = f'{LAST_HANDOFF_LINE}\n  auto-escalate: true'
        workspace.run('write', ANSWERS)
        workspace.edit(LAST_HANDOFF_LINE, turned_on)
        workspace.run('validate')
        workspace.edit(turned_on, LAST_HANDOFF_LINE)

        workspace.run('validate')

        assert workspace.unit().ticket.auto_escalate is False


class TestUpdateContext:
    LINES = ('drain loop fixed in T1', 'user: ship behind the flag', 'T2 owns the metrics')

    @pytest.fixture
    def staged(self, workspace: Workspace) -> Workspace:
        workspace.run('write', ANSWERS)
        workspace.edit('  scope: "med"', '  scope: large   # bumped after review')
        workspace.run('validate')
        return workspace

    def test_update_context_updates_a_tickets_context_lines(self, staged: Workspace) -> None:
        outcome = staged.run('update-context', {'context': self.LINES})

        text = staged.ticket.read_text(encoding='utf-8')
        assert outcome.code == 0
        assert staged.unit().ticket.context == self.LINES
        assert parse(text)['context'] == list(self.LINES)
        assert CONTEXT[0] not in text

    def test_update_context_keeps_every_other_line_of_the_ticket(self, staged: Workspace) -> None:
        before = staged.ticket.read_text(encoding='utf-8').splitlines()

        staged.run('update-context', {'context': self.LINES})

        after = staged.ticket.read_text(encoding='utf-8').splitlines()
        assert [line for line in before if line not in after] == [
            f'  - "{line}"' for line in CONTEXT
        ]
        assert '  scope: large   # bumped after review' in after

    def test_update_context_refuses_more_lines_than_a_ticket_holds(self, staged: Workspace) -> None:
        before = staged.ticket.read_text(encoding='utf-8')

        outcome = staged.run('update-context', {'context': [f'line {n}' for n in range(7)]})

        assert outcome.code == REJECTED
        assert 'context must be a list of 1 to 6 lines' in outcome.err
        assert staged.ticket.read_text(encoding='utf-8') == before
        assert list(staged.unit().ticket.context) == CONTEXT

    def test_update_context_needs_a_written_ticket(self, workspace: Workspace) -> None:
        outcome = workspace.run('update-context', {'context': self.LINES})

        assert outcome.code == REJECTED
        assert 'run write first' in outcome.err

    def test_show_refuses_a_ticket_that_was_never_staged(self, workspace: Workspace) -> None:
        workspace.run('write', ANSWERS)

        outcome = workspace.run('show')

        assert outcome.code == REJECTED
        assert 'stage the ticket with open-ticket first' in outcome.err

    def test_show_reports_the_staged_ticket(self, staged: Workspace) -> None:
        assert staged.run('show').out == 'staged retry-queue (status staged, 0 investigations)\n'
