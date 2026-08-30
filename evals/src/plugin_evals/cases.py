from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator

from plugin_evals.errors import NoCasesError
from plugin_evals.evaluators import ALL_CHECKS

type CheckTuple = tuple[Evaluator, ...]


@dataclass(slots=True)
class CaseSpec:
    name: str
    plugin: str
    skill: str
    fixture: str
    task: str
    sim_notes: str
    checks: CheckTuple


def _to_case(spec: CaseSpec) -> Case:
    inputs = {
        'case': spec.name,
        'skill': spec.skill,
        'fixture': spec.fixture,
        'task': spec.task,
        'sim_notes': spec.sim_notes,
    }
    return Case(
        name=spec.name,
        inputs=inputs,
        metadata={'skill': spec.skill},
        evaluators=spec.checks,
    )


def behavior_dataset(specs: Sequence[CaseSpec], skill: str | None = None) -> Dataset:
    if not specs:
        raise NoCasesError(skill)

    plugins = {s.plugin for s in specs}
    plugin = plugins.pop() if len(plugins) == 1 else 'plugin'
    name = f'{plugin}-behavior-{skill}' if skill else f'{plugin}-behavior'
    return Dataset(name=name, cases=[_to_case(s) for s in specs])


def behavior_path(datasets_dir: Path, plugin: str, skill: str) -> Path:
    return datasets_dir.joinpath(plugin, skill, 'behavior.yaml')


def trigger_path(datasets_dir: Path, plugin: str, skill: str) -> Path:
    return datasets_dir.joinpath(plugin, skill, 'trigger.yaml')


def write_behavior_datasets(datasets_dir: Path, specs: Sequence[CaseSpec]) -> list[Path]:
    written = []
    for spec in specs:
        path = behavior_path(datasets_dir, spec.plugin, spec.skill)
        path.parent.mkdir(parents=True, exist_ok=True)
        behavior_dataset([spec], spec.skill).to_file(
            path,
            fmt='yaml',
            schema_path='./behavior.schema.json',
            custom_evaluator_types=ALL_CHECKS,
        )
        written.append(path)
    return written


def load_behavior_dataset(
    datasets_dir: Path, skills: Sequence[str] | None = None
) -> Dataset:
    paths = sorted(datasets_dir.glob('*/*/behavior.yaml'))
    if skills is not None:
        wanted = set(skills)
        paths = [path for path in paths if path.parent.name in wanted]
    loaded = [
        Dataset.from_file(path, custom_evaluator_types=ALL_CHECKS) for path in paths
    ]
    if len(loaded) == 1:
        # a single skill loads as its own dataset, keeping the per-skill name
        return loaded[0]

    cases = [case for dataset in loaded for case in dataset.cases]
    if not cases:
        raise NoCasesError(None)
    plugins = {path.parent.parent.name for path in paths}
    plugin = plugins.pop() if len(plugins) == 1 else 'plugin'
    return Dataset(name=f'{plugin}-behavior', cases=cases)


def load_trigger_dataset(datasets_dir: Path, plugin: str, skill: str) -> Dataset:
    # trigger sets are hand-editable data, so the YAML is their source of truth;
    # execution needs a harness-specific retrieval oracle and lives outside this package
    return Dataset.from_file(trigger_path(datasets_dir, plugin, skill))
