import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

PACKAGE_DIR = Path(__file__).resolve().parent
# src/mightymcp -> src -> plugins/mightymodels
BUNDLED_PLUGIN_ROOT = PACKAGE_DIR.parents[1]
FRONTMATTER_FENCE = '---\n'
# the one fleet vocabulary: the agent files under agents/, in the order load_fleet
# reads them; routing, hooks.guard, and worker_reports key their role tables off it
FLEET_ROLES = (
    'budgetron',
    'engineer',
    'gitty-up',
    'grumpy',
    'scout',
    'sunny',
    'wingman',
)


class Worker(BaseModel):
    name: str = Field(description='Agent name, as Claude Code dispatches it')
    job: str = Field(description='What the agent is for, in one sentence')
    model: str = Field(description='Model the agent is pinned to by default')


class Fleet(BaseModel):
    workers: list[Worker] = Field(description='Every agent the plugin ships')


def plugin_root() -> Path:
    override = os.environ.get('CLAUDE_PLUGIN_ROOT')
    return Path(override).resolve() if override else BUNDLED_PLUGIN_ROOT


def load_fleet(root: Path | None = None) -> Fleet:
    agents_dir = (root or plugin_root()).joinpath('agents')
    return Fleet(workers=[_read_worker(p) for p in sorted(agents_dir.glob('*.md'))])


def render_fleet(fleet: Fleet) -> str:
    return '\n'.join(f'{w.name} ({w.model}): {w.job}' for w in fleet.workers)


def _read_worker(path: Path) -> Worker:
    front = _read_frontmatter(path)
    return Worker(
        name=front['name'],
        job=_first_sentence(front['description']),
        model=front['model'],
    )


def _read_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding='utf-8')
    if not text.startswith(FRONTMATTER_FENCE):
        raise ValueError(f'{path} has no YAML frontmatter')
    block, fence, _ = text[len(FRONTMATTER_FENCE) :].partition(f'\n{FRONTMATTER_FENCE}')
    if not fence:
        raise ValueError(f'{path} has an unterminated YAML frontmatter block')
    return yaml.safe_load(block)


def _first_sentence(description: str) -> str:
    folded = ' '.join(description.split())
    head, stop, _ = folded.partition('. ')
    return head + stop.rstrip()
