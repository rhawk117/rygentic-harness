from pathlib import Path

import pytest
from mightymodels_evals.cases import (
    SPECS,
    behavior_dataset,
    load_behavior_dataset,
    write_behavior_datasets,
)
from mightymodels_evals.errors import NoCasesError

EXPECTED_SPECS = 11  # ten loop skills + the using-mightymodels fleet reference


def test_specs_cover_the_roster_with_unique_names() -> None:
    assert len(SPECS) == EXPECTED_SPECS
    assert len({s.name for s in SPECS}) == EXPECTED_SPECS
    assert all(s.checks for s in SPECS)


def test_behavior_dataset_filters_by_skill() -> None:
    assert len(behavior_dataset().cases) == EXPECTED_SPECS
    assert len(behavior_dataset('agents-assemble').cases) == 1

    with pytest.raises(NoCasesError):
        behavior_dataset('nonexistent-skill')


def test_write_then_load_round_trips_per_skill_layout(tmp_path: Path) -> None:
    written = write_behavior_datasets(tmp_path)
    assert len(written) == EXPECTED_SPECS
    assert tmp_path.joinpath('agents-assemble', 'behavior.yaml').is_file()
    assert tmp_path.joinpath('agents-assemble', 'behavior.schema.json').is_file()

    combined = load_behavior_dataset(tmp_path)
    assert len(combined.cases) == EXPECTED_SPECS

    single = load_behavior_dataset(tmp_path, 'whats-broken')
    assert single.cases[0].evaluators
