"""The completion gate on a residual, on a real repository and SQLite: an in-progress `R` task
holds the implementer that started it on a commit, its receipts and its owned files, and asks for
no brief. A `C` task is let through as before."""

import json
from dataclasses import dataclass

import pytest
from mightymodels_plugin.commands.tests.hook_inputs import Hook, implementer_stop
from mightymodels_plugin.commands.tests.ticket_checkout import (
    NO_DECISION,
    SLUG,
    TICKET,
    TicketCheckout,
)
from mightymodels_plugin.tools.contract.schema import ContractCommand, Outcome, Phase
from mightymodels_plugin.tools.contract.service import ContractService, RunRequest
from mightymodels_plugin.tools.task.schema import Implementer, TaskStart
from mightymodels_plugin.tools.task.service import TaskService

OWNED = 'src/queue.py'
OUTSIDE = 'src/drain.py'
VERIFY = 'R1.AC-1'
PASSING = ('true',)
FAILING = ('false',)
NO_RECEIPT = f'{VERIFY} has no receipt at the current HEAD'
HELD = (
    pytest.param('nothing_committed', 'no commit follows its base', id='no-commit'),
    pytest.param('fixed_without_a_receipt', NO_RECEIPT, id='no-receipt'),
    pytest.param('proven_before_the_fix', NO_RECEIPT, id='receipt-at-an-older-commit'),
    pytest.param('fixed_and_failing', f'{VERIFY} {Outcome.FAILED} at HEAD', id='failed-receipt'),
    pytest.param(
        'fixed_outside_the_owned_set',
        f'changed outside the owned set: {OUTSIDE}',
        id='outside-the-owned-set',
    ),
)
LET_THROUGH = (
    pytest.param('fixed_and_proven', id='committed-proven-and-inside-the-owned-set'),
    pytest.param('fixed_with_no_contract_command', id='no-contract-command'),
)
IMPLEMENTERS = tuple(pytest.param(implementer, id=implementer) for implementer in Implementer)


@dataclass(slots=True, kw_only=True, frozen=True)
class ResidualFix:
    checkout: TicketCheckout
    tasks: TaskService
    contracts: ContractService

    def start(self, task_id: str, by: Implementer = Implementer.ENGINEER) -> None:
        self.tasks.start(TICKET, task_id, TaskStart(by=by, owned=(OWNED,), acceptance=('AC-1',)))

    def approve(self, argv: tuple[str, ...]) -> None:
        self.contracts.approve(TICKET, [ContractCommand(id=VERIFY, argv=argv, approved_by='user')])

    def commit(self, path: str) -> None:
        changed = self.checkout.root.joinpath(path)
        changed.parent.mkdir(parents=True, exist_ok=True)
        changed.write_text('drained\n', encoding='utf-8')
        self.checkout.git('add', path)
        self.checkout.git('commit', '--quiet', '-m', 'fix')

    def take_receipts(self) -> None:
        self.contracts.run_approved(TICKET, RunRequest(ids=(VERIFY,), phase=Phase.REVIEW))


@pytest.fixture
def residual_fix(
    checked_out_ticket: TicketCheckout, task_service: TaskService, contract_service: ContractService
) -> ResidualFix:
    return ResidualFix(checkout=checked_out_ticket, tasks=task_service, contracts=contract_service)


@pytest.fixture
def nothing_committed(residual_fix: ResidualFix) -> ResidualFix:
    residual_fix.start('R1')
    return residual_fix


@pytest.fixture
def fixed_with_no_contract_command(nothing_committed: ResidualFix) -> None:
    nothing_committed.commit(OWNED)


@pytest.fixture
def fixed_without_a_receipt(nothing_committed: ResidualFix) -> ResidualFix:
    nothing_committed.approve(PASSING)
    nothing_committed.commit(OWNED)
    return nothing_committed


@pytest.fixture
def fixed_and_proven(fixed_without_a_receipt: ResidualFix) -> None:
    fixed_without_a_receipt.take_receipts()


@pytest.fixture
def proven_before_the_fix(nothing_committed: ResidualFix) -> None:
    nothing_committed.approve(PASSING)
    nothing_committed.take_receipts()
    nothing_committed.commit(OWNED)


@pytest.fixture
def fixed_and_failing(nothing_committed: ResidualFix) -> None:
    nothing_committed.approve(FAILING)
    nothing_committed.commit(OWNED)
    nothing_committed.take_receipts()


@pytest.fixture
def fixed_outside_the_owned_set(fixed_without_a_receipt: ResidualFix) -> None:
    fixed_without_a_receipt.commit(OUTSIDE)
    fixed_without_a_receipt.take_receipts()


@pytest.fixture
def a_plan_task_beside_the_residual(nothing_committed: ResidualFix) -> None:
    nothing_committed.start('T1')


@pytest.fixture
def stopping(request: pytest.FixtureRequest, residual_fix: ResidualFix) -> str:
    residual_fix.start('R1', request.param)
    return f'mightymodels:workers:{request.param}'


@pytest.fixture
def check_fix_with_nothing_committed(residual_fix: ResidualFix) -> None:
    residual_fix.start('C1')


def held(hook_command: Hook, agent_type: str = 'mightymodels:workers:engineer') -> str:
    code, out, err = hook_command.run('completion-gate', implementer_stop(agent_type))
    decision = json.loads(out)

    assert (code, err, decision['decision']) == (0, '', 'block')
    return decision['reason']


class TestCompletionGateOnAResidual:
    @pytest.mark.parametrize(('state', 'lack'), HELD)
    def test_it_holds_the_stop_naming_what_the_residual_lacks_and_no_brief(
        self, state: str, lack: str, request: pytest.FixtureRequest, hook_command: Hook
    ) -> None:
        request.getfixturevalue(state)

        reason = held(hook_command)

        assert f'R1 is in progress and {lack}' in reason
        assert f'mightymodels verify run --slug {SLUG} --id' in reason
        assert 'brief' not in reason
        assert '## DONE' not in reason

    @pytest.mark.parametrize('state', LET_THROUGH)
    def test_it_lets_the_stop_through_with_no_brief_written(
        self, state: str, request: pytest.FixtureRequest, hook_command: Hook
    ) -> None:
        request.getfixturevalue(state)

        assert hook_command.run('completion-gate', implementer_stop()) == NO_DECISION
        assert not hook_command.repository.joinpath('.mightymodels', SLUG, 'briefs').exists()

    @pytest.mark.parametrize('stopping', IMPLEMENTERS, indirect=True)
    def test_it_holds_whichever_implementer_started_the_residual(
        self, stopping: str, hook_command: Hook
    ) -> None:
        assert 'R1 is in progress and no commit follows its base' in held(hook_command, stopping)

    @pytest.mark.usefixtures('nothing_committed')
    def test_an_implementer_that_did_not_start_it_is_let_through(self, hook_command: Hook) -> None:
        stop = implementer_stop('mightymodels:workers:architect')

        assert hook_command.run('completion-gate', stop) == NO_DECISION

    @pytest.mark.usefixtures('nothing_committed')
    def test_a_second_stop_after_the_block_is_let_through(self, hook_command: Hook) -> None:
        stop = implementer_stop(stop_hook_active=True)

        assert hook_command.run('completion-gate', stop) == NO_DECISION

    @pytest.mark.usefixtures('a_plan_task_beside_the_residual')
    def test_beside_a_plan_task_it_names_both_and_what_finishes_each(
        self, hook_command: Hook
    ) -> None:
        reason = held(hook_command)

        assert 'T1 is in progress and its brief' in reason
        assert 'R1 is in progress and no commit follows its base' in reason
        assert 'Append the `## DONE` half' in reason
        assert f'mightymodels verify run --slug {SLUG} --id' in reason


@pytest.mark.usefixtures('check_fix_with_nothing_committed')
class TestCompletionGateOnACheckFix:
    def test_it_is_let_through_as_before(self, hook_command: Hook) -> None:
        assert hook_command.run('completion-gate', implementer_stop()) == NO_DECISION
