from pathlib import Path

import pytest
from plugin_evals.executors import CliExecutor, MissingSkillDirError, Variant


def _executor(plugins_root: Path) -> CliExecutor:
    return CliExecutor(
        command='echo {prompt_file}',
        fixtures_root=plugins_root,
        staging_root=plugins_root,
        plugins_root=plugins_root,
        variant=Variant.WITH_SKILL,
    )


def test_skill_dir_resolves_under_the_owning_plugin(tmp_path: Path) -> None:
    skill_dir = tmp_path.joinpath('ai-engineer', 'skills', 'build-an-agent')
    skill_dir.mkdir(parents=True)

    resolved = _executor(tmp_path)._skill_dir('build-an-agent')  # noqa: SLF001
    assert resolved == skill_dir


def test_skill_dir_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(MissingSkillDirError):
        _executor(tmp_path)._skill_dir('build-an-agent')  # noqa: SLF001
