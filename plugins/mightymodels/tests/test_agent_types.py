"""A worker's agent type is `mightymodels:<folder>:<name>`, the folder its agent file is in."""

import json
import re
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels_plugin.commands.dispatch_hook import DISPATCH_RULES, agent_type, worker_named
from mightymodels_plugin.commands.hook_context import plugin_worker
from mightymodels_plugin.core.routing import ROUTING, Worker

PLUGIN = Path(__file__).parent.parent
HOOKS = PLUGIN.joinpath('hooks', 'hooks.json')
AGENT_FILES = tuple(sorted(PLUGIN.joinpath('agents').glob('*/*.md')))
FOLDERS = frozenset(file.parent.name for file in AGENT_FILES)
PREFIX = 'mightymodels:'


def type_of(agent_file: Path) -> str:
    return f'{PREFIX}{agent_file.parent.name}:{agent_file.stem}'


def types_in_another_folder(agent_file: Path) -> list[str]:
    others = sorted(FOLDERS - {agent_file.parent.name})
    return [f'{PREFIX}{folder}:{agent_file.stem}' for folder in others]


def strays_of(agent_file: Path) -> list[str]:
    named = type_of(agent_file)
    return [
        f'{PREFIX}{agent_file.stem}',
        *types_in_another_folder(agent_file),
        f'other:{named}',
        f'x{named}',
        f'{named}x',
        f'{named}:x',
    ]


TYPES = frozenset(map(type_of, AGENT_FILES))
NO_WORKER = (
    *(f'{PREFIX}{file.stem}' for file in AGENT_FILES),
    *(named for file in AGENT_FILES for named in types_in_another_folder(file)),
    f'{PREFIX}stranger',
)


class TestTypesNamed:
    @pytest.mark.parametrize(
        'workers',
        [
            pytest.param(frozenset(ROUTING), id='routing-table'),
            pytest.param(
                frozenset(DISPATCH_RULES).union(*DISPATCH_RULES.values()), id='dispatch-rules'
            ),
        ],
    )
    def test_names_exactly_the_types_of_the_agent_files(self, workers: frozenset[Worker]) -> None:
        assert set(map(agent_type, workers)) == TYPES


class TestSubagentStopMatchers:
    SERVED = MappingProxyType(
        {
            'subagent-record': frozenset({'code-scout', 'web-scout'}),
            'completion-gate': frozenset({'engineer', 'architect', 'intern'}),
        }
    )

    @pytest.fixture
    def matchers(self) -> dict[str, re.Pattern[str]]:
        groups = json.loads(HOOKS.read_text(encoding='utf-8'))['hooks']['SubagentStop']
        return {
            entry['command'].split()[-1]: re.compile(group['matcher'])
            for group in groups
            for entry in group['hooks']
        }

    def test_each_matches_exactly_the_types_of_the_workers_it_serves(
        self, matchers: dict[str, re.Pattern[str]]
    ) -> None:
        matched = {
            command: frozenset(file.stem for file in AGENT_FILES if matcher.search(type_of(file)))
            for command, matcher in matchers.items()
        }

        assert matched == self.SERVED

    @pytest.mark.parametrize('agent_file', AGENT_FILES, ids=lambda file: file.stem)
    def test_none_matches_a_type_that_is_not_an_agent_files(
        self, matchers: dict[str, re.Pattern[str]], agent_file: Path
    ) -> None:
        matched = [
            (command, stray)
            for command, matcher in matchers.items()
            for stray in strays_of(agent_file)
            if matcher.search(stray)
        ]

        assert matched == []


class TestWorkerOfAType:
    @pytest.mark.parametrize('agent_file', AGENT_FILES, ids=lambda file: file.stem)
    def test_the_type_of_an_agent_file_is_its_worker(self, agent_file: Path) -> None:
        named = type_of(agent_file)

        assert worker_named(named) == Worker(agent_file.stem)
        assert plugin_worker({'agent_type': named}) == Worker(agent_file.stem)

    @pytest.mark.parametrize('named', NO_WORKER)
    def test_a_flat_type_or_one_in_another_folder_is_no_worker_like_an_unknown_name(
        self, named: str
    ) -> None:
        assert worker_named(named) is None
        assert plugin_worker({'agent_type': named}) is None
