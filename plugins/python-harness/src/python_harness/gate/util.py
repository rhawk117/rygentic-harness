"""Pure helpers: gate inputs, child environments, output tails and git status entries."""

import os
import sys
from collections.abc import Collection, Mapping
from pathlib import Path

from python_harness.gate.domain import ConfigKind, GateInputs, GateOptions
from python_harness.survey.domain import ProjectSurvey

SEARCH_PATH = 'PATH'
VIRTUAL_ENV = 'VIRTUAL_ENV'
VIRTUALENV_SCRIPTS = 'Scripts' if sys.platform == 'win32' else 'bin'
UNTRACKED_STATUS_CODES = frozenset({'??', '!!'})


def project_configs_from(survey: ProjectSurvey) -> frozenset[ConfigKind]:
    found = {
        ConfigKind.RUFF: survey.ruff_config,
        ConfigKind.TY: survey.ty_config,
    }
    return frozenset(kind for kind, config in found.items() if config is not None)


def gate_inputs_from(survey: ProjectSurvey) -> GateInputs:
    return GateInputs(
        declared_distributions=survey.manifest.declared_distributions,
        has_uv_lock=survey.layout.has_uv_lock,
        project_configs=project_configs_from(survey),
        domains=frozenset(survey.domains),
        source_roots=survey.source_roots,
    )


def take_output_tail(output: bytes | bytearray, line_count: int) -> str:
    lines = output.decode('utf-8', errors='replace').splitlines()
    return '\n'.join(lines[max(len(lines) - line_count, 0) :])


def remove_search_path_entries(search_path: str, directories: Collection[Path]) -> str:
    entries = search_path.split(os.pathsep)
    return os.pathsep.join(entry for entry in entries if Path(entry) not in directories)


def list_virtualenv_scripts(parent: Mapping[str, str], options: GateOptions) -> frozenset[Path]:
    virtualenvs = (parent.get(VIRTUAL_ENV), options.launcher_environment)
    return frozenset(
        Path(virtualenv, VIRTUALENV_SCRIPTS) for virtualenv in virtualenvs if virtualenv is not None
    )


def build_child_environment(parent: Mapping[str, str], options: GateOptions) -> dict[str, str]:
    dropped = options.dropped_environment
    kept = {name: value for name, value in parent.items() if name not in dropped}
    if SEARCH_PATH in kept:
        scripts = list_virtualenv_scripts(parent, options)
        kept[SEARCH_PATH] = remove_search_path_entries(kept[SEARCH_PATH], scripts)
    return kept | dict(options.child_environment)


def untracked_paths_from_status(status: str, prefix: str) -> frozenset[str]:
    entries = (entry for entry in status.split('\0') if entry)
    untracked = (entry[3:] for entry in entries if entry[:2] in UNTRACKED_STATUS_CODES)
    return frozenset(path.removeprefix(prefix) for path in untracked)
