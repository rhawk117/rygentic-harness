from pathlib import Path

import pytest
from mightymodels_evals.case_modules import mightymodels
from mightymodels_evals.cases import (
    behavior_dataset,
    load_behavior_dataset,
    write_behavior_datasets,
)
from mightymodels_evals.errors import NoCasesError
from mightymodels_evals.registry import (
    DuplicateSkillError,
    UnknownPluginError,
    all_specs,
    collect_specs,
    select_specs,
)

EXPECTED_SPECS = 11  # ten loop skills + the using-mightymodels fleet reference


def test_specs_cover_the_roster_with_unique_names() -> None:
    specs = all_specs()
    assert len(specs) == EXPECTED_SPECS
    assert len({s.name for s in specs}) == EXPECTED_SPECS
    assert all(s.checks for s in specs)
    assert all(s.plugin for s in specs)


def test_registry_filters_by_plugin_and_skill() -> None:
    assert len(select_specs(plugin='mightymodels')) == EXPECTED_SPECS
    assert len(select_specs(skill='agents-assemble')) == 1

    with pytest.raises(NoCasesError):
        select_specs(skill='nonexistent-skill')

    with pytest.raises(UnknownPluginError):
        select_specs(plugin='nonexistent-plugin')


def test_registry_rejects_duplicate_skill_names() -> None:
    # the same module registered twice stands in for two plugins claiming a skill
    with pytest.raises(DuplicateSkillError, match='must be unique'):
        collect_specs((mightymodels, mightymodels))


def test_behavior_dataset_names_the_skill_it_covers() -> None:
    assert len(behavior_dataset(all_specs()).cases) == EXPECTED_SPECS

    single = behavior_dataset(select_specs(skill='agents-assemble'), 'agents-assemble')
    assert len(single.cases) == 1
    assert single.name == 'mightymodels-behavior-agents-assemble'

    with pytest.raises(NoCasesError):
        behavior_dataset([], 'nonexistent-skill')


def test_write_then_load_round_trips_per_skill_layout(tmp_path: Path) -> None:
    written = write_behavior_datasets(tmp_path, all_specs())
    assert len(written) == EXPECTED_SPECS
    assert tmp_path.joinpath('agents-assemble', 'behavior.yaml').is_file()
    assert tmp_path.joinpath('agents-assemble', 'behavior.schema.json').is_file()

    combined = load_behavior_dataset(tmp_path)
    assert len(combined.cases) == EXPECTED_SPECS

    single = load_behavior_dataset(tmp_path, ['whats-broken'])
    assert single.cases[0].evaluators
