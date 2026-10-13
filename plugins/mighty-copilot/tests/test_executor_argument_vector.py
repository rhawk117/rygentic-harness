import pytest
from mightymodels.core.slug import Slug
from mightymodels.core.tests.support import RecordedCall, Recorder
from mightymodels.tools.contract.schema import ContractCommand, Phase
from mightymodels.tools.contract.service import ContractService, RunRequest

SLUG = Slug('retry-queue')
ARGUMENTS = ('--flag', 'two words', '$HOME', '*', 'a;b')


class TestExecutorArgumentVector:
    @pytest.fixture
    def recorded_run(self, contract_service: ContractService, recorder: Recorder) -> RecordedCall:
        command = ContractCommand(
            id='pin', argv=(recorder.executable, *ARGUMENTS), approved_by='user'
        )
        contract_service.approve(SLUG, [command])
        contract_service.run_approved(SLUG, RunRequest(ids=None, phase=Phase.TASK))
        (call,) = recorder.calls()
        return call

    def test_the_executor_passes_the_approved_argument_vector_word_for_word(
        self, recorded_run: RecordedCall, recorder: Recorder
    ) -> None:
        assert recorded_run.argv == [recorder.executable, *ARGUMENTS]

    def test_the_executor_runs_the_command_in_the_workspace_root(
        self, recorded_run: RecordedCall, contract_service: ContractService
    ) -> None:
        assert recorded_run.cwd == contract_service.workspace.root
