"""The contract service on the store and the git history kept in memory.

`run` is `ContractService.run_approved`, what `verify run` calls, and its commands are launched for
real. The test of the command line itself is in test_verify_run_command_line.py.
"""

import errno
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.process import ProcessRunner, RunOutcome
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit, RecordedCommit
from mightymodels_plugin.tools.contract.schema import ContractCommand, Phase
from mightymodels_plugin.tools.contract.service import ContractService, RunRequest
from mightymodels_plugin.tools.contract.tests.in_memory import InMemoryContractStore
from pydantic import ValidationError

SLUG = 'retry-queue'
OTHER_SLUG = 'cache-warmup'
PASSED, FAILED, REJECTED = 0, 1, 2
PYTHON = sys.executable
SHA_A = 'a' * 40
SHA_B = 'b' * 40
SHA256_HEX = 64


def python(code: str, *args: str) -> list[str]:
    return [PYTHON, '-c', code, *args]


@dataclass(frozen=True, slots=True, kw_only=True)
class Outcome:
    code: int
    out: str
    err: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Recorded:
    slug: str
    id: str
    argv: list[str]
    outcome: str
    exit: int | None
    head: str | None
    phase: str
    stdout_tail: str
    stderr_tail: str
    digest: str


def moved_to(history: InMemoryGit, sha: str) -> RecordedCommit:
    return RecordedCommit(sha=sha, parent=history.resolve_head(), changed=frozenset())


@dataclass(frozen=True, slots=True, kw_only=True)
class HeadMovingRunner:
    history: InMemoryGit
    to: str
    launcher: ProcessRunner

    def run(self, argv: Sequence[str], *, timeout: float, cwd: Path | None = None) -> RunOutcome:
        outcome = self.launcher.run(argv, timeout=timeout, cwd=cwd)
        self.history.commits.append(moved_to(self.history, self.to))
        return outcome


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    contracts: ContractService
    store: InMemoryContractStore
    history: InMemoryGit

    @property
    def root(self) -> Path:
        return self.contracts.workspace.root

    def run(self, *ids: str, phase: Phase = Phase.TASK, slug: str = SLUG) -> Outcome:
        request = RunRequest(ids=ids or None, phase=phase)
        try:
            result = self.contracts.run_approved(Slug(slug), request)
        except StateError as error:
            return Outcome(code=REJECTED, out='', err=str(error))
        return Outcome(code=PASSED if result.passed else FAILED, out=result.text, err='')

    def approve(self, *commands: Mapping[str, object], slug: str = SLUG) -> Outcome:
        try:
            approved = [
                ContractCommand.model_validate({'approved_by': 'user', **command})
                for command in commands
            ]
            view = self.contracts.approve(Slug(slug), approved)
        except (StateError, ValidationError) as error:
            return Outcome(code=REJECTED, out='', err=str(error))
        return Outcome(code=PASSED, out=view.text, err='')

    def status(self) -> Outcome:
        view = self.contracts.status(Slug(SLUG))
        return Outcome(code=PASSED if view.passing else FAILED, out=view.text, err='')

    def receipts(self) -> list[Recorded]:
        return [
            Recorded(
                slug=recorded.slug.root,
                id=recorded.receipt.id,
                argv=list(recorded.receipt.argv),
                outcome=recorded.receipt.outcome,
                exit=recorded.receipt.exit,
                head=recorded.receipt.head,
                phase=recorded.receipt.phase,
                stdout_tail=recorded.receipt.stdout_tail,
                stderr_tail=recorded.receipt.stderr_tail,
                digest=recorded.receipt.digest,
            )
            for recorded in self.store.receipts
        ]

    def planned(self) -> dict[str, str | None]:
        return {
            record.command.id: record.command.task_id for record in self.store.approved.values()
        }

    def point_head(self, sha: str) -> None:
        self.history.commits.append(moved_to(self.history, sha))


@pytest.fixture
def workspace(
    in_memory_contract_service: ContractService,
    in_memory_contract_store: InMemoryContractStore,
    in_memory_git: InMemoryGit,
) -> Workspace:
    space = Workspace(
        contracts=in_memory_contract_service, store=in_memory_contract_store, history=in_memory_git
    )
    space.point_head(SHA_A)
    return space


@pytest.fixture
def workspace_whose_head_moves(workspace: Workspace) -> Workspace:
    moving = HeadMovingRunner(
        history=workspace.history, to=SHA_B, launcher=workspace.contracts.processes
    )
    return replace(workspace, contracts=replace(workspace.contracts, processes=moving))


def test_contract_requires_a_named_approver(workspace: Workspace) -> None:
    outcome = workspace.approve({'id': 'T1.AC-1', 'argv': python('print(1)'), 'approved_by': ' '})
    assert outcome.code == REJECTED
    assert 'approved_by is required' in outcome.err


def test_a_shell_string_is_refused(workspace: Workspace) -> None:
    outcome = workspace.approve({'id': 'T1.AC-1', 'argv': 'pytest -q && rm -rf /'})
    assert outcome.code == REJECTED
    assert 'no shell string' in outcome.err


def test_an_approved_command_runs_and_leaves_a_receipt(workspace: Workspace) -> None:
    workspace.approve({'id': 'T1.AC-1', 'argv': python('print("ok")')})
    outcome = workspace.run('T1.AC-1')
    receipt = workspace.receipts()[0]
    assert outcome.code == PASSED
    assert outcome.out.startswith('T1.AC-1 pass exit=0')
    assert (receipt.outcome, receipt.head, receipt.stdout_tail) == (
        'pass',
        SHA_A,
        'ok',
    )


def test_ids_outside_the_contract_never_run(workspace: Workspace) -> None:
    workspace.approve({'id': 'T1.AC-1', 'argv': python('print(1)')})
    outcome = workspace.run('T1.AC-1', 'rm-everything')
    assert outcome.code == REJECTED
    assert "not in the contract: ['rm-everything']" in outcome.err
    assert workspace.receipts() == []


def test_arguments_reach_the_command_without_a_shell(workspace: Workspace) -> None:
    code = 'import sys; print(sys.argv[1])'
    workspace.approve({'id': 'I1', 'argv': python(code, '$HOME; echo pwned')})
    workspace.run('I1')
    assert workspace.receipts()[0].stdout_tail == '$HOME; echo pwned'


def test_a_failing_command_reports_its_tail(workspace: Workspace) -> None:
    code = 'import sys; sys.stderr.write("boom\\n"); sys.exit(3)'
    workspace.approve({'id': 'T2.AC-1', 'argv': python(code)})
    outcome = workspace.run('T2.AC-1')
    assert outcome.code == FAILED
    assert 'T2.AC-1 fail exit=3' in outcome.out
    assert '  | boom' in outcome.out


def test_an_expected_red_command_passes_at_planning(workspace: Workspace) -> None:
    code = 'import sys; sys.exit(1)'
    workspace.approve({'id': 'T3.AC-1', 'argv': python(code), 'expect_exit': 1})
    outcome = workspace.run('T3.AC-1', phase=Phase.PLANNING)
    assert outcome.code == PASSED
    assert workspace.receipts()[0].phase == 'planning'


def test_a_hung_command_times_out(workspace: Workspace) -> None:
    code = 'import time; time.sleep(10)'
    workspace.approve({'id': 'slow', 'argv': python(code), 'timeout': 1})
    outcome = workspace.run('slow')
    assert outcome.code == FAILED
    assert workspace.receipts()[0].outcome == 'timeout'


def test_a_missing_program_is_reported_not_raised(workspace: Workspace) -> None:
    workspace.approve({'id': 'gone', 'argv': ['no-such-program-xyz']})
    outcome = workspace.run('gone')
    assert outcome.code == FAILED
    assert workspace.receipts()[0].outcome == 'not-found'


def test_head_changes_during_a_command_cannot_produce_a_passing_receipt(
    workspace_whose_head_moves: Workspace,
) -> None:
    workspace_whose_head_moves.approve({'id': 'T1.AC-1', 'argv': python('print(1)')})
    outcome = workspace_whose_head_moves.run('T1.AC-1')
    receipt = workspace_whose_head_moves.receipts()[0]
    assert outcome.code == FAILED
    assert (receipt.outcome, receipt.head) == ('fail', SHA_A)
    assert 'HEAD changed during verification' in receipt.stderr_tail


def test_an_approved_id_cannot_change_its_argv(workspace: Workspace) -> None:
    workspace.approve({'id': 'T1.AC-1', 'argv': python('print(1)')})
    outcome = workspace.approve({'id': 'T1.AC-1', 'argv': python('print(2)')})
    assert outcome.code == REJECTED
    assert 'give it a new id' in outcome.err


def test_output_is_bounded_but_digested_whole(workspace: Workspace) -> None:
    code = 'print("\\n".join(str(n) for n in range(100)))'
    workspace.approve({'id': 'loud', 'argv': python(code)})
    workspace.run('loud')
    receipt = workspace.receipts()[0]
    assert receipt.stdout_tail.splitlines() == [str(n) for n in range(60, 100)]
    assert len(receipt.digest) == SHA256_HEX


def test_status_marks_results_from_an_older_head_stale(workspace: Workspace) -> None:
    workspace.approve(
        {'id': 'T1.AC-1', 'argv': python('print(1)')},
        {'id': 'T1.AC-2', 'argv': python('print(2)')},
    )
    workspace.run('T1.AC-1')
    workspace.point_head(SHA_B)
    outcome = workspace.status()
    assert f'T1.AC-1 stale (pass at {SHA_A[:12]})' in outcome.out
    assert 'T1.AC-2 never-run' in outcome.out
    assert outcome.code == FAILED


def test_status_passes_when_every_command_passed_at_head(workspace: Workspace) -> None:
    workspace.approve({'id': 'T1.AC-1', 'argv': python('print(1)')})
    workspace.run('T1.AC-1')
    outcome = workspace.status()
    assert outcome.code == PASSED
    assert 'T1.AC-1 pass task expect=0' in outcome.out


def test_all_runs_every_approved_command_at_head(workspace: Workspace) -> None:
    workspace.approve(
        {'id': 'I1', 'argv': python('print(1)')},
        {'id': 'T1.AC-1', 'argv': python('print(2)')},
    )
    outcome = workspace.run(phase=Phase.LANDING)
    receipts = workspace.receipts()
    assert outcome.code == PASSED
    assert [(r.id, r.phase) for r in receipts] == [
        ('I1', 'landing'),
        ('T1.AC-1', 'landing'),
    ]


class TestApprove:
    def test_contract_approve_takes_the_plans_task_ids_and_commands_once(
        self, workspace: Workspace
    ) -> None:
        plan = (
            {'id': 'I1', 'argv': python('print(0)')},
            {'id': 'T1.AC-1', 'argv': python('print(1)')},
            {'id': 'T1.AC-2', 'argv': python('print(2)')},
            {'id': 'T2.AC-1', 'argv': python('print(3)'), 'expect_exit': 1},
        )

        first = workspace.approve(*plan)
        again = workspace.approve(*plan)

        assert first.out == 'contract: 4 commands (4 new)\n'
        assert again.out == 'contract: 4 commands (0 new)\n'
        assert workspace.planned() == {
            'I1': None,
            'T1.AC-1': 'T1',
            'T1.AC-2': 'T1',
            'T2.AC-1': 'T2',
        }

    def test_a_later_approval_adds_only_the_new_commands(self, workspace: Workspace) -> None:
        workspace.approve({'id': 'T1.AC-1', 'argv': python('print(1)')})

        outcome = workspace.approve(
            {'id': 'T1.AC-1', 'argv': python('print(1)')},
            {'id': 'C1.AC-1', 'argv': python('print(2)')},
        )

        assert outcome.out == 'contract: 2 commands (1 new)\n'
        assert workspace.planned() == {'C1.AC-1': 'C1', 'T1.AC-1': 'T1'}

    def test_one_approval_cannot_give_an_id_two_argvs(self, workspace: Workspace) -> None:
        outcome = workspace.approve(
            {'id': 'T1.AC-1', 'argv': python('print(1)')},
            {'id': 'T1.AC-1', 'argv': python('print(2)')},
        )

        assert outcome.code == REJECTED
        assert workspace.planned() == {}

    @pytest.mark.parametrize(
        'command',
        [
            pytest.param({'id': 'T1.AC-1', 'argv': []}, id='empty-argv'),
            pytest.param({'id': 'T1.AC-1', 'argv': ['echo', 1]}, id='non-string-argument'),
            pytest.param({'id': 'T1 AC', 'argv': ['true']}, id='spaced-id'),
            pytest.param({'id': 'T1.AC-1', 'argv': ['true'], 'timeout': 0}, id='no-timeout'),
            pytest.param({'id': 'T1.AC-1', 'argv': ['true'], 'shell': True}, id='unknown-field'),
        ],
    )
    def test_a_malformed_command_is_refused(
        self, workspace: Workspace, command: dict[str, object]
    ) -> None:
        assert workspace.approve(command).code == REJECTED
        assert workspace.planned() == {}

    def test_status_of_an_empty_contract_passes_with_nothing_to_show(
        self, workspace: Workspace
    ) -> None:
        assert workspace.status().out == f'HEAD {SHA_A[:12]}\nno matching commands\n'


class TestVerifyRunAllowlist:
    MARKER = 'ran.txt'

    def touch(self, *arguments: str) -> list[str]:
        code = (
            'import sys; from pathlib import Path; '
            f'Path({self.MARKER!r}).write_text(" ".join(sys.argv[1:]))'
        )
        return python(code, *arguments)

    def test_verify_run_allowlist_refuses_an_id_approved_for_another_ticket(
        self, workspace: Workspace
    ) -> None:
        workspace.approve({'id': 'I1', 'argv': python('print(1)')})
        workspace.approve({'id': 'T1.AC-1', 'argv': self.touch()}, slug=OTHER_SLUG)

        outcome = workspace.run('T1.AC-1')

        assert outcome.code == REJECTED
        assert "not in the contract: ['T1.AC-1']" in outcome.err
        assert not workspace.root.joinpath(self.MARKER).exists()
        assert workspace.receipts() == []

    def test_verify_run_allowlist_refuses_a_ticket_with_no_contract(
        self, workspace: Workspace
    ) -> None:
        workspace.approve({'id': 'T1.AC-1', 'argv': self.touch()}, slug=OTHER_SLUG)

        outcome = workspace.run()

        assert outcome.code == REJECTED
        assert 'retry-queue has no approved commands' in outcome.err
        assert not workspace.root.joinpath(self.MARKER).exists()

    def test_verify_run_allowlist_runs_nothing_when_one_id_is_not_approved(
        self, workspace: Workspace
    ) -> None:
        workspace.approve({'id': 'T1.AC-1', 'argv': self.touch()})

        outcome = workspace.run('T1.AC-1', 'T1.AC-2')

        assert outcome.code == REJECTED
        assert not workspace.root.joinpath(self.MARKER).exists()
        assert workspace.receipts() == []

    def test_verify_run_allowlist_executes_the_recorded_argv_and_stores_its_receipt(
        self, workspace: Workspace
    ) -> None:
        argv = self.touch('$(id)', '; echo pwned')
        workspace.approve({'id': 'T1.AC-1', 'argv': argv})
        workspace.approve({'id': 'T1.AC-1', 'argv': python('print("other")')}, slug=OTHER_SLUG)

        outcome = workspace.run('T1.AC-1')

        receipt = workspace.receipts()[0]
        assert outcome.code == PASSED
        assert workspace.root.joinpath(self.MARKER).read_text() == '$(id) ; echo pwned'
        assert (receipt.slug, receipt.id, receipt.argv) == (SLUG, 'T1.AC-1', argv)
        assert (receipt.outcome, receipt.head, receipt.phase) == ('pass', SHA_A, 'task')
        assert len(workspace.receipts()) == 1


class TestLaunchAndDecodeFailures:
    NOT_TEXT = 'import sys; sys.stdout.buffer.write(bytes([255, 254]))'
    STORED = (
        ('1-passes', 'pass'),
        ('2-not-executable', 'refused'),
        ('3-not-text', 'undecodable'),
        ('4-nul-in-argument', 'refused'),
        ('5-passes', 'pass'),
    )

    @pytest.fixture
    def approved(self, workspace: Workspace, tmp_path: Path) -> Outcome:
        not_executable = tmp_path.joinpath('not-executable')
        not_executable.write_text('not executable\n', encoding='utf-8')
        return workspace.approve(
            {'id': '1-passes', 'argv': python('print(1)')},
            {'id': '2-not-executable', 'argv': [str(not_executable)]},
            {'id': '3-not-text', 'argv': python(self.NOT_TEXT)},
            {'id': '4-nul-in-argument', 'argv': python('print(1)', 'a\0b')},
            {'id': '5-passes', 'argv': python('print(2)')},
        )

    @pytest.mark.usefixtures('approved')
    @pytest.mark.parametrize(
        ('command_id', 'stored', 'cause'),
        [
            pytest.param(
                '2-not-executable', 'refused', os.strerror(errno.EACCES), id='refused-launch'
            ),
            pytest.param(
                '3-not-text', 'undecodable', "can't decode byte 0xff", id='undecodable-output'
            ),
        ],
    )
    def test_a_command_that_cannot_launch_or_decode_is_stored_as_an_outcome_of_its_own(
        self, workspace: Workspace, command_id: str, stored: str, cause: str
    ) -> None:
        outcome = workspace.run(command_id)

        receipt = workspace.receipts()[0]
        assert (outcome.code, receipt.outcome, receipt.exit) == (FAILED, stored, None)
        assert cause in receipt.stderr_tail.splitlines()[-1]

    @pytest.mark.usefixtures('approved')
    def test_one_batch_stores_a_receipt_for_every_command_around_the_ones_that_cannot_run(
        self, workspace: Workspace
    ) -> None:
        outcome = workspace.run()

        assert outcome.code == FAILED
        assert [(receipt.id, receipt.outcome) for receipt in workspace.receipts()] == list(
            self.STORED
        )
