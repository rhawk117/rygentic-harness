import shlex
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from plugin_evals.artifacts import RunArtifacts, read_rel, run_cmd
from plugin_evals.errors import (
    HarnessError,
    ReplayRunMissingError,
    UnknownFixtureError,
)
from plugin_evals.fixtures import BUILDERS
from plugin_evals.registry import plugin_for_skill


class MissingSkillDirError(HarnessError):
    def __init__(self, skill_dir: str) -> None:
        super().__init__(
            f'no skill directory at {skill_dir}; the with-skill arm cannot run without it'
        )
        self.skill_dir = skill_dir


class Variant(StrEnum):
    WITH_SKILL = 'with_skill'
    WITHOUT_SKILL = 'without_skill'


class Executor(Protocol):
    def run(self, inputs: dict) -> RunArtifacts: ...


@dataclass(slots=True)
class ReplayExecutor:
    runs_root: Path
    variant: Variant

    def run(self, inputs: dict) -> RunArtifacts:
        base = self.runs_root.joinpath(inputs['case'], self.variant.value)
        workdir = base.joinpath('work')
        if not workdir.is_dir():
            raise ReplayRunMissingError(str(workdir))

        response = read_rel(base, 'response.md') or ''
        return RunArtifacts(workdir=workdir, response=response)


@dataclass(slots=True)
class CliExecutor:
    command: str
    fixtures_root: Path
    staging_root: Path
    plugins_root: Path
    variant: Variant
    include_sim_notes: bool = False
    timeout: int = 2400

    def run(self, inputs: dict) -> RunArtifacts:
        workdir = self._stage(inputs)
        prompt_file = workdir.parent.joinpath('prompt.md')
        prompt_file.write_text(self._compose(inputs), encoding='utf-8')

        cmd = [
            part.format(prompt_file=str(prompt_file), workdir=str(workdir))
            for part in shlex.split(self.command)
        ]
        _, out = run_cmd(cmd, workdir, timeout=self.timeout)
        workdir.parent.joinpath('response.md').write_text(out, encoding='utf-8')
        return RunArtifacts(workdir=workdir, response=out)

    def _stage(self, inputs: dict) -> Path:
        fixture = inputs['fixture']
        if fixture not in BUILDERS:
            raise UnknownFixtureError(fixture)

        source = self.fixtures_root.joinpath(fixture)
        workdir = self.staging_root.joinpath(inputs['case'], self.variant.value, 'work')
        if workdir.exists():
            shutil.rmtree(workdir)

        workdir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, workdir, symlinks=True)
        return workdir

    def _skill_dir(self, skill: str) -> Path:
        plugin = plugin_for_skill(skill)
        skill_dir = self.plugins_root.joinpath(plugin, 'skills', skill)
        if not skill_dir.is_dir():
            raise MissingSkillDirError(str(skill_dir))
        return skill_dir

    def _compose(self, inputs: dict) -> str:
        parts = []
        if self.variant is Variant.WITH_SKILL:
            skill_dir = self._skill_dir(inputs['skill'])
            parts.append(
                f'First read {skill_dir}/SKILL.md and every reference file it points '
                f'to, then follow it for this task. Related skills live under '
                f'{skill_dir.parent} and '
                f'agent contracts beside them.'
            )

        parts.append(f'Task: {inputs["task"]}')
        if self.include_sim_notes and inputs.get('sim_notes'):
            parts.append(inputs['sim_notes'])
        return '\n\n'.join(parts)


def as_task(executor: Executor) -> Callable[[dict], RunArtifacts]:
    def task(inputs: dict) -> RunArtifacts:
        return executor.run(inputs)

    return task
