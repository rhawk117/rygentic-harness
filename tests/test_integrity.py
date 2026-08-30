"""Deterministic repository-integrity checks.

The eval suite scores protocol behavior; these tests check that the repository
can execute its own protocol: every skill or agent referenced in docs, skills,
the README, and the issue templates exists on disk in some plugin, the
documented inventories match the directories, the eval datasets name real
skills, and the ramp routing table covers every (scope, plan-first) state.
Reference scans span every plugin under `plugins/`; the inventory-count and
routing checks are scoped to the mightymodels plugin whose docs they verify.
No LLM calls, no network.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT.joinpath('plugins')
MIGHTYMODELS_ROOT = PLUGINS_ROOT.joinpath('mightymodels')

# Backticked kebab-case tokens that are neither skills nor agents but are
# legitimately referenced in prose: config keys, model ids, external tools.
# Grows only through review — a typo'd skill name must not end up here.
ALLOWED_TOKENS = {
    'allowed-tools',
    'claude-haiku-4-5',
    'claude-opus-5',
    'claude-sonnet-5',
    'continue-on-error',
    'disable-model-invocation',
    'files-in-scope',
    'full-meltdown',  # crashout journal severity, not a skill
    'mild-tilt',  # crashout journal severity, not a skill
    'plan-first',
    'review-weight',
    'subagent-models',
    'triaged-at',
}

# Mermaid flowchart node labels that are prose, not inventory names.
ALLOWED_NODE_LABELS = {'human review'}

NUMBER_WORDS = {'two': 2, 'four': 4, 'five': 5, 'seven': 7, 'ten': 10, 'twenty': 20}

BACKTICK_KEBAB = re.compile(r'`([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`')
KEBAB = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)+')


def skill_names() -> set[str]:
    """Skill names across every plugin in the marketplace."""
    return {p.name for p in PLUGINS_ROOT.glob('*/skills/*') if p.is_dir()}


def agent_names() -> set[str]:
    """Agent names across every plugin in the marketplace."""
    return {p.name.removesuffix('.md') for p in PLUGINS_ROOT.glob('*/agents/*.md')}


def mightymodels_skill_names() -> set[str]:
    return {p.name for p in MIGHTYMODELS_ROOT.joinpath('skills').iterdir() if p.is_dir()}


def mightymodels_agent_names() -> set[str]:
    return {
        p.name.removesuffix('.md')
        for p in MIGHTYMODELS_ROOT.joinpath('agents').glob('*.md')
    }


def _reference_surface() -> list[Path]:
    return [
        REPO_ROOT.joinpath('README.md'),
        *sorted(REPO_ROOT.glob('docs/*.md')),
        *sorted(REPO_ROOT.glob('.github/ISSUE_TEMPLATE/*.md')),
        *sorted(PLUGINS_ROOT.glob('*/skills/*/SKILL.md')),
    ]


@pytest.mark.parametrize(
    'doc', _reference_surface(), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_backticked_names_exist_on_disk(doc: Path) -> None:
    inventory = skill_names() | agent_names() | ALLOWED_TOKENS
    unknown = {
        token
        for token in BACKTICK_KEBAB.findall(doc.read_text(encoding='utf-8'))
        if token not in inventory
    }
    assert not unknown, (
        f'{doc.relative_to(REPO_ROOT)} references names absent from skills/ and '
        f'agents/: {sorted(unknown)} (rename the reference, restore the asset, or '
        f'allowlist a genuine non-inventory token)'
    )


def _mermaid_node_labels(text: str) -> set[str]:
    labels = set()
    for block in re.findall(r'```mermaid\n(.*?)```', text, flags=re.DOTALL):
        if 'flowchart' not in block:
            continue
        for label in re.findall(r'\["([^"\]]+)"?\]', block):
            labels.add(label.split('\\n')[0].strip())
    return labels


@pytest.mark.parametrize('doc', ['README.md', 'docs/workflow.md'])
def test_workflow_diagram_nodes_are_real_skills_or_agents(doc: str) -> None:
    inventory = skill_names() | agent_names()
    labels = _mermaid_node_labels(REPO_ROOT.joinpath(doc).read_text(encoding='utf-8'))
    named = {
        label
        for label in labels
        if label not in ALLOWED_NODE_LABELS and KEBAB.fullmatch(label)
    }
    unknown = named - inventory
    if doc == 'docs/workflow.md':
        assert named, f'{doc}: expected flowchart nodes naming skills or agents'
    assert not unknown, f'{doc}: flowchart routes to nonexistent stages {sorted(unknown)}'


def test_eval_dataset_dirs_name_existing_skills() -> None:
    datasets = {
        p.name for p in REPO_ROOT.joinpath('evals/datasets').iterdir() if p.is_dir()
    }
    unknown = datasets - skill_names()
    assert not unknown, f'eval dataset dirs for absent skills: {sorted(unknown)}'


def test_eval_case_specs_name_existing_skills() -> None:
    from mightymodels_evals.registry import all_specs

    specs = all_specs()
    unknown = {spec.skill for spec in specs} - skill_names()
    assert not unknown, f'eval case specs target absent skills: {sorted(unknown)}'

    absent_plugins = {
        spec.plugin for spec in specs if not PLUGINS_ROOT.joinpath(spec.plugin).is_dir()
    }
    assert not absent_plugins, (
        f'eval case specs name absent plugins: {sorted(absent_plugins)}'
    )


def test_documented_skill_inventory_matches_disk() -> None:
    text = REPO_ROOT.joinpath('docs/skills.md').read_text(encoding='utf-8')
    names = mightymodels_skill_names()
    missing = {name for name in names if name not in text}
    assert not missing, (
        f'skills on disk but absent from docs/skills.md: {sorted(missing)}'
    )

    claim = re.search(r'^(\w+) skills ship', text, flags=re.MULTILINE)
    assert claim, 'docs/skills.md no longer states its skill count'
    count_word = claim.group(1).lower()
    assert NUMBER_WORDS.get(count_word) == len(names), (
        f'docs/skills.md claims "{count_word}" skills; mightymodels holds {len(names)}'
    )


def test_documented_agent_inventory_matches_disk() -> None:
    text = REPO_ROOT.joinpath('docs/agents.md').read_text(encoding='utf-8')
    names = mightymodels_agent_names()
    headings = set(re.findall(r'^## ([a-z][a-z0-9-]*)$', text, flags=re.MULTILINE))
    assert headings == names, (
        f'docs/agents.md sections {sorted(headings)} != mightymodels agents on disk '
        f'{sorted(names)}'
    )

    claim = re.search(r'^(\w+) workers live', text, flags=re.MULTILINE)
    assert claim, 'docs/agents.md no longer states its worker count'
    count_word = claim.group(1).lower()
    assert NUMBER_WORDS.get(count_word) == len(names), (
        f'docs/agents.md claims "{count_word}" workers; disk holds {len(names)}'
    )


def test_ramp_routing_table_covers_every_state() -> None:
    text = REPO_ROOT.joinpath('docs/workflow.md').read_text(encoding='utf-8')
    rows = re.findall(
        r'^\|\s*(sm|med|large)\s*\|\s*(true|false)\s*\|\s*`([a-z0-9-]+)`\s*\|\s*$',
        text,
        flags=re.MULTILINE,
    )
    covered = {(scope, flag): ramp for scope, flag, ramp in rows}

    every_state = {
        (scope, flag) for scope in ('sm', 'med', 'large') for flag in ('true', 'false')
    }
    uncovered = every_state - set(covered)
    assert not uncovered, (
        f'ramp routing table leaves states uncovered: {sorted(uncovered)}'
    )

    unknown_ramps = set(covered.values()) - mightymodels_skill_names()
    assert not unknown_ramps, (
        f'routing table targets absent skills: {sorted(unknown_ramps)}'
    )
