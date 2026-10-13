import pytest

CONCEPTS = (
    'core',
    'tools',
    'tools.ticket',
    'tools.task',
    'tools.contract',
    'tools.review',
    'tools.snapshot',
    'tools.close',
    'tools.investigation',
    'tools.crashout',
    'tools.similarity',
    'commands',
)
VARIABLES_GIT_GIVES_A_HOOK = ('GIT_INDEX_FILE', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_PREFIX')


def pytest_configure(config: pytest.Config) -> None:
    for concept in CONCEPTS:
        config.pluginmanager.import_plugin(f'mightymodels_plugin.{concept}.tests.support')


@pytest.fixture(autouse=True)  # ruff: ignore[pytest-fixture-autouse] - any test may run git
def without_the_variables_git_gives_a_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in VARIABLES_GIT_GIVES_A_HOOK:
        monkeypatch.delenv(variable, raising=False)
