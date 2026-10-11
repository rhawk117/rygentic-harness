from pathlib import Path

import pytest

from mightymodels_plugin.commands.tests.hook_inputs import Hook
from mightymodels_plugin.core.data_directory import PLUGIN_DATA_VARIABLE
from mightymodels_plugin.core.workspace import PROJECT_DIR_VARIABLE


@pytest.fixture
def hook(
    in_the_repository: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Hook:
    return Hook(repository=in_the_repository, monkeypatch=monkeypatch, capsys=capsys)


@pytest.fixture
def in_the_repository(
    repository: Path, data_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setenv(PLUGIN_DATA_VARIABLE, str(data_directory))
    monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(repository))
    return repository
