"""The main-thread hook's push hold on a real repository and SQLite: what the tasks and receipts
of the ticket on the checked-out branch make of a push, at the commit that is checked out."""

import pytest
from mightymodels_plugin.commands.tests.hook_inputs import ENGINEER, Hook, tool_call
from mightymodels_plugin.commands.tests.ticket_checkout import (
    COMMAND,
    NO_DECISION,
    OTHER_SLUG,
    SLUG,
    TicketCheckout,
    decision_of,
    shown,
)
from mightymodels_plugin.core.data_directory import PLUGIN_DATA_VARIABLE
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.contract.schema import Outcome, Phase
from mightymodels_plugin.tools.task.schema import Status

OLD = 'a' * 40
PUSHES = (
    pytest.param('git push', id='plain'),
    pytest.param('git -C ../checkout push', id='another-directory'),
    pytest.param('uv run pytest && git push origin HEAD', id='chained'),
    pytest.param('git push --force-with-lease -u origin fix/retry', id='options-first'),
)


@pytest.fixture
def approved_but_never_started(checked_out_ticket: TicketCheckout) -> None:
    checked_out_ticket.approve()


@pytest.fixture
def t1_in_progress(checked_out_ticket: TicketCheckout) -> None:
    checked_out_ticket.record_task('T1')


@pytest.fixture
def t1_failed(checked_out_ticket: TicketCheckout) -> None:
    checked_out_ticket.record_task('T1', Status.FAILED)


@pytest.fixture
def t1_blocked(checked_out_ticket: TicketCheckout) -> None:
    checked_out_ticket.record_task('T1', Status.BLOCKED)


@pytest.fixture
def t1_verified(checked_out_ticket: TicketCheckout) -> TicketCheckout:
    checked_out_ticket.record_task('T1', Status.VERIFIED)
    return checked_out_ticket


@pytest.fixture
def command_approved(t1_verified: TicketCheckout) -> TicketCheckout:
    t1_verified.approve()
    return t1_verified


@pytest.fixture
def passed_in_the_task_phase(command_approved: TicketCheckout) -> None:
    command_approved.record_receipt(Outcome.PASSED, Phase.TASK, command_approved.head())


@pytest.fixture
def passed_in_landing_at_another_commit(command_approved: TicketCheckout) -> None:
    command_approved.record_receipt(Outcome.PASSED, Phase.LANDING, OLD)


@pytest.fixture
def failed_in_landing(command_approved: TicketCheckout) -> None:
    command_approved.record_receipt(Outcome.FAILED, Phase.LANDING, command_approved.head())


@pytest.fixture
def proven_in_landing(command_approved: TicketCheckout) -> TicketCheckout:
    command_approved.record_receipt(Outcome.PASSED, Phase.LANDING, command_approved.head())
    return command_approved


@pytest.fixture
def a_commit_after_the_proof(proven_in_landing: TicketCheckout) -> TicketCheckout:
    proven_in_landing.commit()
    return proven_in_landing


@pytest.fixture
def proven_again_at_the_new_head(a_commit_after_the_proof: TicketCheckout) -> None:
    a_commit_after_the_proof.record_receipt(
        Outcome.PASSED, Phase.LANDING, a_commit_after_the_proof.head()
    )


@pytest.mark.usefixtures('checked_out_ticket')
class TestPushWithATicketOnTheBranch:
    def refusal(self, hook_command: Hook, command: str = 'git push') -> str:
        code, out, err = hook_command.run('main-thread-hook', tool_call('Bash', command=command))
        decision, reason = decision_of(out)
        assert (code, err, decision) == (0, '', 'deny')
        return reason

    @pytest.mark.parametrize(
        ('layout', 'unproven'),
        [
            pytest.param('checked_out_ticket', 'no plan task has been started', id='no-plan-task'),
            pytest.param(
                'approved_but_never_started',
                'T1 has contract commands but was never started',
                id='pending',
            ),
            pytest.param('t1_in_progress', 'T1 is in-progress, not verified', id='in-progress'),
            pytest.param('t1_failed', 'T1 is failed, not verified', id='failed'),
            pytest.param('t1_blocked', 'T1 is blocked, not verified', id='blocked'),
            pytest.param(
                'command_approved', f'{COMMAND} has no receipt at the current HEAD', id='never-run'
            ),
            pytest.param(
                'passed_in_the_task_phase',
                f'{COMMAND} passed at HEAD in the task phase, not the landing phase',
                id='passed-in-the-task-phase',
            ),
            pytest.param(
                'passed_in_landing_at_another_commit',
                f'{COMMAND} has no receipt at the current HEAD',
                id='passed-at-another-commit',
            ),
            pytest.param('failed_in_landing', f'{COMMAND} fail at HEAD', id='failed-in-landing'),
            pytest.param(
                'a_commit_after_the_proof',
                f'{COMMAND} has no receipt at the current HEAD',
                id='a-commit-after-the-proof',
            ),
        ],
    )
    def test_it_is_denied_naming_what_keeps_the_ticket_from_landing_and_the_step_to_take(
        self, layout: str, unproven: str, request: pytest.FixtureRequest, hook_command: Hook
    ) -> None:
        request.getfixturevalue(layout)

        reason = self.refusal(hook_command)

        assert f'ticket {SLUG}, whose branch is checked out, is not ready to land: ' in reason
        assert unproven in reason
        assert '`stick-the-landing` skill' in reason
        assert f'`mightymodels verify run --slug {SLUG} --all --phase landing`' in reason

    @pytest.mark.parametrize('command', PUSHES)
    def test_each_spelling_of_a_push_is_denied(self, command: str, hook_command: Hook) -> None:
        assert self.refusal(hook_command, command).startswith('`git push` was refused: ticket')

    @pytest.mark.parametrize('command', PUSHES)
    @pytest.mark.parametrize(
        'layout',
        [
            pytest.param('proven_in_landing', id='proven-in-landing'),
            pytest.param('proven_again_at_the_new_head', id='proven-again-at-the-new-head'),
            pytest.param('t1_verified', id='verified-with-no-contract-command'),
        ],
    )
    def test_with_the_tasks_closed_and_the_landing_proven_at_head_it_gets_no_decision(
        self, layout: str, command: str, request: pytest.FixtureRequest, hook_command: Hook
    ) -> None:
        request.getfixturevalue(layout)

        assert hook_command.run('main-thread-hook', tool_call('Bash', command=command)) == (
            NO_DECISION
        )

    def test_when_the_state_cannot_be_read_it_is_denied_saying_why(
        self, hook_command: Hook
    ) -> None:
        hook_command.monkeypatch.delenv(PLUGIN_DATA_VARIABLE)

        assert self.refusal(hook_command).startswith(
            '`git push` was refused: the tasks and receipts of the ticket on the checked-out '
            f'branch could not be read ({PLUGIN_DATA_VARIABLE} is not set'
        )

    def test_a_plugin_workers_push_gets_no_decision(self, hook_command: Hook) -> None:
        assert (
            hook_command.run('main-thread-hook', tool_call('Bash', ENGINEER, command='git push'))
            == NO_DECISION
        )

    def test_a_commit_is_not_judged(self, hook_command: Hook) -> None:
        commit = tool_call('Bash', command='git commit -m "hold a git push"')

        assert hook_command.run('main-thread-hook', commit) == NO_DECISION

    def test_with_another_branch_checked_out_it_gets_no_decision(
        self, hook_command: Hook, ticket_checkout: TicketCheckout
    ) -> None:
        ticket_checkout.git('symbolic-ref', 'HEAD', 'refs/heads/another')

        assert (
            hook_command.run('main-thread-hook', tool_call('Bash', command='git push'))
            == NO_DECISION
        )

    def test_with_a_second_ticket_on_the_branch_it_gets_one_line_naming_both(
        self, hook_command: Hook, ticket_checkout: TicketCheckout
    ) -> None:
        ticket_checkout.stage(Slug(OTHER_SLUG))

        warning = shown(hook_command.run('main-thread-hook', tool_call('Bash', command='git push')))

        assert warning == (
            'mightymodels did not hold this `git push`: the checked-out branch has 2 unclosed '
            f'tickets ({SLUG}, {OTHER_SLUG}), and the hook acts only when it has one'
        )
