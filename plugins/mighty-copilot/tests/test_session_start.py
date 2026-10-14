"""The SessionStart command: it announces where the CLI and the plugin are and writes nothing."""

from pathlib import Path

import pytest
from mightymodels.cli import main
from mightymodels.core.codec import decode_text
from mightymodels.core.data_directory import PLUGIN_DATA_VARIABLE, SESSION_DATA_VARIABLE

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PLUGIN_ROOT.joinpath('bin', 'mightymodels')
SESSION_START = ('session-start',)


@pytest.fixture
def announced(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert main(SESSION_START) == 0
    document = decode_text(capsys.readouterr().out)
    assert isinstance(document, dict)
    return {str(key): value for key, value in document.items()}


class TestSessionStart:
    def test_it_prints_the_launcher_and_the_plugin_root_at_the_top_level(
        self, announced: dict[str, object]
    ) -> None:
        context = announced['additionalContext']

        assert isinstance(context, str)
        assert str(LAUNCHER) in context
        assert str(PLUGIN_ROOT) in context

    def test_it_prints_the_same_context_under_hook_specific_output(
        self, announced: dict[str, object]
    ) -> None:
        assert announced['hookSpecificOutput'] == {
            'hookEventName': 'SessionStart',
            'additionalContext': announced['additionalContext'],
        }

    def test_the_announced_launcher_is_an_absolute_path_to_a_file(self) -> None:
        assert LAUNCHER.is_absolute()
        assert LAUNCHER.is_file()

    def test_it_writes_no_file_and_needs_no_variable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        for variable in (PLUGIN_DATA_VARIABLE, SESSION_DATA_VARIABLE):
            monkeypatch.delenv(variable, raising=False)
        monkeypatch.chdir(tmp_path)

        assert main(SESSION_START) == 0
        assert capsys.readouterr().err == ''
        assert list(tmp_path.iterdir()) == []
