"""Fallback configs: both files ship inside the gate package."""

from importlib.resources import files
from pathlib import Path

import pytest
import tomllib
from python_harness.gate.fallbacks import RUFF_CONFIG, TY_CONFIG

SKILL_ASSETS = Path(__file__).parents[2] / 'skills' / 'tactical-slop-review' / 'assets'
FALLBACK_CONFIGS = pytest.mark.parametrize(
    ('path', 'name'), [(RUFF_CONFIG, 'ruff.toml'), (TY_CONFIG, 'ty.toml')], ids=['ruff', 'ty']
)


class TestPackagedFallbackConfigs:
    @FALLBACK_CONFIGS
    def test_file_is_read_through_the_installed_package(self, path: Path, name: str) -> None:
        packaged = files('python_harness.gate').joinpath('fallback_configs', name)

        assert tomllib.loads(packaged.read_text(encoding='utf-8')) == tomllib.loads(
            path.read_text(encoding='utf-8')
        )

    @FALLBACK_CONFIGS
    def test_fallback_matches_the_skill_asset(self, path: Path, name: str) -> None:
        assert path.read_bytes() == SKILL_ASSETS.joinpath(name).read_bytes()

    def test_ty_fallback_includes_python_files_in_any_layout(self) -> None:
        config = tomllib.loads(TY_CONFIG.read_text(encoding='utf-8'))

        assert config['src']['include'] == ['**/*.py']
