"""Fallback configs: both files ship inside the gate package."""

from importlib.resources import files
from pathlib import Path

import pytest
import tomllib
from python_harness.gate.fallbacks import RUFF_CONFIG, TY_CONFIG

SKILL_RUFF_CONFIG = (
    Path(__file__).parents[2] / 'skills' / 'what-would-ryan-say' / 'assets' / 'ruff.toml'
)


class TestPackagedFallbackConfigs:
    @pytest.mark.parametrize(
        ('path', 'name'), [(RUFF_CONFIG, 'ruff.toml'), (TY_CONFIG, 'ty.toml')], ids=['ruff', 'ty']
    )
    def test_file_is_read_through_the_installed_package(self, path: Path, name: str) -> None:
        packaged = files('python_harness.gate').joinpath('fallback_configs', name)

        assert tomllib.loads(packaged.read_text(encoding='utf-8')) == tomllib.loads(
            path.read_text(encoding='utf-8')
        )

    def test_ruff_fallback_matches_the_skill_asset(self) -> None:
        assert RUFF_CONFIG.read_bytes() == SKILL_RUFF_CONFIG.read_bytes()

    def test_ty_fallback_includes_python_files_in_any_layout(self) -> None:
        config = tomllib.loads(TY_CONFIG.read_text(encoding='utf-8'))

        assert config['src']['include'] == ['**/*.py']
