"""The Claude Code plugin layout contract for skills and agents."""

import json
import re
from pathlib import Path

import pytest
import yaml
from mightymodels_evals.paths import EVALS_ROOT

REPO_ROOT = EVALS_ROOT.parent
SKILL_NAME_PATTERN = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')
PORTABLE_SKILL_KEYS = frozenset({
    'name',
    'description',
    'license',
    'allowed-tools',
    'metadata',
    'disable-model-invocation',
})
REQUIRED_AGENT_KEYS = frozenset({'name', 'description', 'model', 'tools'})
# Claude Code subagent frontmatter keys; plugin agents may not carry
# hooks, mcpServers, or permissionMode, and skill-only keys are invalid here.
VALID_AGENT_KEYS = frozenset({
    'name',
    'description',
    'model',
    'tools',
    'disallowedTools',
    'effort',
    'maxTurns',
    'skills',
    'memory',
    'background',
    'isolation',
    'color',
    'initialPrompt',
    'experimental',
})
CANONICAL_TOOLS = frozenset({
    'Read',
    'Write',
    'Edit',
    'Bash',
    'Grep',
    'Glob',
    'WebFetch',
    'WebSearch',
    'Task',
})
AGENT_MODELS = frozenset({'claude-sonnet-5', 'claude-haiku-4-5', 'claude-opus-5'})
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---\n'):
        pytest.fail(f'{path}: no frontmatter block')
    body = text.split('---\n', 2)
    if len(body) < 3:
        pytest.fail(f'{path}: unterminated frontmatter block')
    loaded = yaml.safe_load(body[1])
    if not isinstance(loaded, dict):
        pytest.fail(f'{path}: frontmatter is not a mapping')
    return loaded


def _skill_dirs() -> list[Path]:
    return sorted(p for p in REPO_ROOT.joinpath('skills').iterdir() if p.is_dir())


def _agent_files() -> list[Path]:
    return sorted(REPO_ROOT.joinpath('agents').glob('*.md'))


def test_repo_has_the_expected_surface() -> None:
    assert len(_skill_dirs()) >= 18, 'skill roster shrank unexpectedly'
    assert len(_agent_files()) == 7, (
        'worker fleet is scout/engineer/budgetron/gitty-up/grumpy/sunny/wingman'
    )


@pytest.mark.parametrize('skill_dir', _skill_dirs(), ids=lambda p: p.name)
def test_skill_frontmatter_is_portable(skill_dir: Path) -> None:
    manifest = skill_dir.joinpath('SKILL.md')
    assert manifest.is_file(), f'{skill_dir.name}: SKILL.md missing'
    front = _frontmatter(manifest)

    name = front.get('name')
    assert name == skill_dir.name, (
        f'{skill_dir.name}: frontmatter name must match the directory'
    )
    assert isinstance(name, str)
    assert SKILL_NAME_PATTERN.fullmatch(name), f'{name}: must be lowercase-hyphen'
    assert len(name) <= MAX_NAME_LENGTH

    description = front.get('description')
    assert isinstance(description, str), f'{skill_dir.name}: description missing'
    assert description.strip(), f'{skill_dir.name}: description empty'
    assert len(description) <= MAX_DESCRIPTION_LENGTH, (
        f'{skill_dir.name}: description too long'
    )

    stray = set(front) - PORTABLE_SKILL_KEYS
    assert not stray, f'{skill_dir.name}: non-portable frontmatter keys {sorted(stray)}'
    assert 'allowed-tools' not in front, (
        f'{skill_dir.name}: pre-approved tools are banned here'
    )


@pytest.mark.parametrize('agent_file', _agent_files(), ids=lambda p: p.name)
def test_agent_frontmatter_is_complete(agent_file: Path) -> None:
    front = _frontmatter(agent_file)
    missing = REQUIRED_AGENT_KEYS - set(front)
    assert not missing, f'{agent_file.name}: missing keys {sorted(missing)}'
    stray = set(front) - VALID_AGENT_KEYS
    assert not stray, f'{agent_file.name}: invalid agent frontmatter keys {sorted(stray)}'

    expected_name = agent_file.name.removesuffix('.md')
    assert front['name'] == expected_name, f'{agent_file.name}: name must match the file'

    tools = front['tools']
    assert isinstance(tools, list), f'{agent_file.name}: tools must be a list'
    if agent_file.stem != 'wingman':
        assert tools, f'{agent_file.name}: tools list is empty'
    unknown_tools = set(tools) - CANONICAL_TOOLS
    assert not unknown_tools, (
        f'{agent_file.name}: unknown tool names {sorted(unknown_tools)}'
    )

    model = front['model']
    assert isinstance(model, str), f'{agent_file.name}: model pin missing'
    assert model in AGENT_MODELS, (
        f'{agent_file.name}: model {model!r} not in {sorted(AGENT_MODELS)}'
    )


def test_manifests_agree() -> None:
    plugin = json.loads(
        REPO_ROOT.joinpath('.claude-plugin/plugin.json').read_text('utf-8')
    )
    market = json.loads(
        REPO_ROOT.joinpath('.claude-plugin/marketplace.json').read_text('utf-8')
    )

    assert plugin['name'] == 'mightymodels'
    assert market['name'] == 'rygentic-harness'
    entry = market['plugins'][0]
    assert entry['name'] == plugin['name']
    assert entry['source'] == './'
    assert entry['version'] == plugin['version'], 'bump both manifests together'
