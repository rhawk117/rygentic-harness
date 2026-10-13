import pytest
from mightymodels.commands.tests.support import (
    checked_out_ticket,
    hook_command,
    hook_repository,
    ticket_checkout,
)
from mightymodels.core.tests.support import (
    git,
    gitless_workspace,
    in_memory_git,
    recorder,
    repository,
)
from mightymodels.tools.close.tests.support import (
    close_repo,
    close_service,
    committed_close_repo,
    in_memory_close_service,
    in_memory_close_store,
    staged_close_repo,
)
from mightymodels.tools.contract.tests.support import (
    contract_service,
    in_memory_contract_service,
    in_memory_contract_store,
)
from mightymodels.tools.crashout.tests.support import (
    crashout_service,
    in_memory_crashout_service,
    in_memory_crashout_store,
)
from mightymodels.tools.investigation.tests.support import (
    in_memory_investigation_service,
    in_memory_investigation_store,
    investigation_service,
)
from mightymodels.tools.review.tests.support import (
    in_memory_review_service,
    in_memory_review_store,
    review_service,
    review_workspace,
)
from mightymodels.tools.similarity.tests.support import (
    in_memory_similarity_service,
    in_memory_similarity_store,
    similarity_own_key,
    similarity_service,
    spool,
)
from mightymodels.tools.snapshot.tests.support import (
    in_memory_snapshot_service,
    in_memory_snapshot_store,
    snapshot_service,
)
from mightymodels.tools.task.tests.support import (
    in_memory_task_service,
    in_memory_task_store,
    task_repo,
    task_repo_without_a_commit_or_a_ticket,
    task_service,
    unborn_task_repo,
    unstaged_task_repo,
)
from mightymodels.tools.tests.support import (
    connected_server,
    data_directory,
    database_activity,
    repository_database,
    repository_git,
    repository_workspace,
    session_in_the_repository,
    state_server,
    tree_after_the_connect,
)
from mightymodels.tools.ticket.tests.support import (
    in_memory_ticket_service,
    in_memory_ticket_store,
    ticket_service,
)

__all__ = (
    'checked_out_ticket',
    'close_repo',
    'close_service',
    'committed_close_repo',
    'connected_server',
    'contract_service',
    'crashout_service',
    'data_directory',
    'database_activity',
    'git',
    'gitless_workspace',
    'hook_command',
    'hook_repository',
    'in_memory_close_service',
    'in_memory_close_store',
    'in_memory_contract_service',
    'in_memory_contract_store',
    'in_memory_crashout_service',
    'in_memory_crashout_store',
    'in_memory_git',
    'in_memory_investigation_service',
    'in_memory_investigation_store',
    'in_memory_review_service',
    'in_memory_review_store',
    'in_memory_similarity_service',
    'in_memory_similarity_store',
    'in_memory_snapshot_service',
    'in_memory_snapshot_store',
    'in_memory_task_service',
    'in_memory_task_store',
    'in_memory_ticket_service',
    'in_memory_ticket_store',
    'investigation_service',
    'recorder',
    'repository',
    'repository_database',
    'repository_git',
    'repository_workspace',
    'review_service',
    'review_workspace',
    'session_in_the_repository',
    'similarity_own_key',
    'similarity_service',
    'snapshot_service',
    'spool',
    'staged_close_repo',
    'state_server',
    'task_repo',
    'task_repo_without_a_commit_or_a_ticket',
    'task_service',
    'ticket_checkout',
    'ticket_service',
    'tree_after_the_connect',
    'unborn_task_repo',
    'unstaged_task_repo',
)

VARIABLES_GIT_GIVES_A_HOOK = ('GIT_INDEX_FILE', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_PREFIX')


@pytest.fixture(autouse=True)  # ruff: ignore[pytest-fixture-autouse] - any test may run git
def without_the_variables_git_gives_a_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in VARIABLES_GIT_GIVES_A_HOOK:
        monkeypatch.delenv(variable, raising=False)
