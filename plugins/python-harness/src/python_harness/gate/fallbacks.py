"""Locations of the fallback ruff and ty configs packaged with the gate."""

from pathlib import Path

FALLBACK_CONFIGS = Path(__file__).parent / 'fallback_configs'
RUFF_CONFIG = FALLBACK_CONFIGS / 'ruff.toml'
TY_CONFIG = FALLBACK_CONFIGS / 'ty.toml'
