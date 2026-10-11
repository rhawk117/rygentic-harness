"""The ruff version option: its manifest declaration, its default and how the server gets it."""

import json
from pathlib import Path

import pytest
from python_harness.gate.domain import (
    DEFAULT_RUFF_VERSION,
    RUFF_VERSION_OPTION,
    RUFF_VERSION_VARIABLE,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SERVER_NAME = 'python-harness'


@pytest.fixture(scope='module')
def user_config() -> dict[str, dict[str, str]]:
    manifest = json.loads(
        PLUGIN_ROOT.joinpath('.claude-plugin', 'plugin.json').read_text(encoding='utf-8')
    )
    return manifest['userConfig']


@pytest.fixture(scope='module')
def server_env() -> dict[str, str]:
    declared = json.loads(PLUGIN_ROOT.joinpath('.mcp.json').read_text(encoding='utf-8'))
    return declared['mcpServers'][SERVER_NAME]['env']


class TestRuffVersionOption:
    def test_the_manifest_declares_that_one_option(
        self, user_config: dict[str, dict[str, str]]
    ) -> None:
        assert list(user_config) == [RUFF_VERSION_OPTION]

    def test_the_option_is_a_described_string(self, user_config: dict[str, dict[str, str]]) -> None:
        option = user_config[RUFF_VERSION_OPTION]

        assert (option['type'], bool(option['title']), bool(option['description'])) == (
            'string',
            True,
            True,
        )

    def test_the_manifest_default_is_the_default_the_gate_runs(
        self, user_config: dict[str, dict[str, str]]
    ) -> None:
        assert user_config[RUFF_VERSION_OPTION]['default'] == DEFAULT_RUFF_VERSION.text

    def test_the_server_receives_the_option_in_its_environment(
        self, server_env: dict[str, str]
    ) -> None:
        assert server_env[RUFF_VERSION_VARIABLE] == f'${{user_config.{RUFF_VERSION_OPTION}}}'
