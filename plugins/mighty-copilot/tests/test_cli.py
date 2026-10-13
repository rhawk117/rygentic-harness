import pytest
from mightymodels.cli import build_parser, main
from pytest_mock import MockerFixture

SLUG = 'retry-queue'


class TestCli:
    def test_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            build_parser().parse_args(['--help'])

        assert exit_info.value.code == 0
        assert 'serve' in capsys.readouterr().out

    def test_a_command_is_required(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main([])

        assert exit_info.value.code == 2
        assert 'usage: mightymodels' in capsys.readouterr().err

    def test_serve_starts_the_server(self, mocker: MockerFixture) -> None:
        serve = mocker.patch('mightymodels.server.serve')

        assert main(['serve']) == 0
        serve.assert_called_once_with()


class TestVerifyRun:
    def test_help_shows_its_options(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['verify', 'run', '--help'])

        shown = capsys.readouterr().out
        assert exit_info.value.code == 0
        assert [option in shown for option in ('--slug', '--id', '--all', '--phase')] == [True] * 4

    @pytest.mark.parametrize(
        'arguments',
        [
            pytest.param(['--slug', SLUG], id='neither-ids-nor-all'),
            pytest.param(['--slug', SLUG, '--id', 'I1', '--all'], id='ids-and-all'),
            pytest.param(['--all'], id='no-slug'),
            pytest.param(['--slug', SLUG, '--all', '--phase', 'shipping'], id='unknown-phase'),
        ],
    )
    def test_refuses_a_command_line_it_does_not_define(
        self, arguments: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['verify', 'run', *arguments])

        assert exit_info.value.code == 2
        assert 'usage: mightymodels verify run' in capsys.readouterr().err


class TestReviewSignals:
    WINDOW_OPTIONS = ('--target', '--since', '--baseline-ref', '--max-commits', '--all-history')

    @pytest.mark.parametrize('report', ['code-churn', 'change-coupling', 'code-hotspots'])
    def test_help_shows_the_window_options_of_each_report(
        self, report: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['review-signals', report, '--help'])

        shown = capsys.readouterr().out
        assert exit_info.value.code == 0
        assert [option in shown for option in self.WINDOW_OPTIONS] == [True] * 5


class TestReviewMetrics:
    OPTIONS = ('--out', '--max-listed', '--package-depth')

    def test_help_shows_its_options(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['review-metrics', '--help'])

        shown = capsys.readouterr().out
        assert exit_info.value.code == 0
        assert [option in shown for option in self.OPTIONS] == [True] * 3
