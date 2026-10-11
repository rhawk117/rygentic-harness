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
)


def pytest_configure(config: pytest.Config) -> None:
    for concept in CONCEPTS:
        config.pluginmanager.import_plugin(f'mightymodels_plugin.{concept}.tests.support')
