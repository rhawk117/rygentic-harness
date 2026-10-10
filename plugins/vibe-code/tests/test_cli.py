import pytest
from vibe_code_cli.cli import CommandGroups, build_parser, main


class TestTopLevelParser:
    def test_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            build_parser().parse_args(['--help'])

        assert exit_info.value.code == 0
        assert 'vibe-code' in capsys.readouterr().out

    def test_main_without_a_group_prints_usage_and_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([]) == 2
        assert 'usage: vibe-code' in capsys.readouterr().err


class TestCommandGroups:
    GROUPS = ('skill', 'hook', 'subagent', 'instruction', 'mcp', 'plugin', 'tune')

    def test_help_lists_the_seven_groups(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(['--help'])

        output = capsys.readouterr().out
        for group in self.GROUPS:
            assert group in output

    def test_parser_accepts_exactly_the_seven_groups(self) -> None:
        assert set(CommandGroups().dispatchers) == set(self.GROUPS)

    @pytest.mark.parametrize(
        'old_name',
        [
            pytest.param('create-skill', id='create-skill'),
            pytest.param('create-hooks', id='create-hooks'),
            pytest.param('create-subagent', id='create-subagent'),
            pytest.param('create-instructions', id='create-instructions'),
            pytest.param('create-mcp', id='create-mcp'),
            pytest.param('plan-plugin', id='plan-plugin'),
        ],
    )
    def test_old_group_names_fail_as_invalid_choices(
        self, old_name: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main([old_name, 'validate', '--help'])

        assert exit_info.value.code == 2
        assert 'invalid choice' in capsys.readouterr().err
