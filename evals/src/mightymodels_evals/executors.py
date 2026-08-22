import shlex
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from mightymodels_evals.artifacts import RunArtifacts, read_rel, run_cmd
from mightymodels_evals.errors import ReplayRunMissingError, UnknownFixtureError
from mightymodels_evals.fixtures import BUILDERS


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
    skills_root: Path
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

    def _compose(self, inputs: dict) -> str:
        parts = []
        if self.variant is Variant.WITH_SKILL:
            skill_dir = self.skills_root.joinpath(inputs['skill'])
            parts.append(
                f'First read {skill_dir}/SKILL.md and every reference file it points '
                f'to, then follow it for this task. Related skills live under '
                f'{self.skills_root} and '
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
