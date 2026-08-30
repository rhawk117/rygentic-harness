"""Code owns the directory layout. Prose never describes it.

skill-creator tells the model to write `eval-N/with_skill/outputs/` and then globs
`eval-*/<config>/run-*/grading.json` — a config with no `run-*` child is silently
skipped, so the documented workflow yields an all-zeros benchmark that exits 0.
The fix is not a clearer sentence. It is never letting a path be typed twice.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from skilleng import SCHEMA_VERSION
from skilleng.schema import Arm, Provenance, RunRecord, SchemaError, dump

_SAFE = re.compile(r'[^a-zA-Z0-9._-]+')


def slug(text: str) -> str:
    s = _SAFE.sub('-', str(text).strip()).strip('-').lower()
    return s[:60] or 'unnamed'


class Workspace:
    """Every path in the pipeline comes from a method here.

    Layout (fixed, not configurable — configurable layouts are how drift starts):

        <root>/
          state.json                 phase + gates
          iteration-<N>/
            provenance.json
            events.ndjson            normalized hook events for the whole iteration
            runs/<eval_id>/<arm>/run-<i>/
              outputs/               everything the agent produced
              run.json               RunRecord
              stdout.log, stderr.log
            benchmark.json
            report.html
            feedback.json
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    # -- construction ------------------------------------------------------

    @classmethod
    def create(cls, root: Path) -> Workspace:
        ws = cls(root)
        ws.root.mkdir(parents=True, exist_ok=True)
        if not ws.state_path.exists():
            ws.write_state({
                'schema_version': SCHEMA_VERSION,
                'phase': 'draft',
                'iteration': 0,
                'gates': {},
            })
        return ws

    # -- paths -------------------------------------------------------------

    @property
    def state_path(self) -> Path:
        return self.root / 'state.json'

    def iteration_dir(self, iteration: int) -> Path:
        if iteration < 1:
            raise SchemaError(f'iterations are 1-based, got {iteration}')
        return self.root / f'iteration-{iteration}'

    def events_path(self, iteration: int) -> Path:
        return self.iteration_dir(iteration) / 'events.ndjson'

    def provenance_path(self, iteration: int) -> Path:
        return self.iteration_dir(iteration) / 'provenance.json'

    def run_dir(self, iteration: int, eval_id: str, arm: Arm, run_index: int) -> Path:
        arm = Arm(arm)
        if run_index < 1:
            raise SchemaError(f'run indices are 1-based, got {run_index}')
        return (
            self.iteration_dir(iteration)
            / 'runs'
            / slug(eval_id)
            / arm.value
            / f'run-{run_index}'
        )

    def outputs_dir(self, iteration: int, eval_id: str, arm: Arm, run_index: int) -> Path:
        return self.run_dir(iteration, eval_id, arm, run_index) / 'outputs'

    def run_record_path(
        self, iteration: int, eval_id: str, arm: Arm, run_index: int
    ) -> Path:
        return self.run_dir(iteration, eval_id, arm, run_index) / 'run.json'

    def benchmark_path(self, iteration: int) -> Path:
        return self.iteration_dir(iteration) / 'benchmark.json'

    def report_path(self, iteration: int) -> Path:
        return self.iteration_dir(iteration) / 'report.html'

    def feedback_path(self, iteration: int) -> Path:
        return self.iteration_dir(iteration) / 'feedback.json'

    def prepare_run(self, iteration: int, eval_id: str, arm: Arm, run_index: int) -> Path:
        d = self.outputs_dir(iteration, eval_id, arm, run_index)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -- state / gates -----------------------------------------------------

    def state(self) -> dict:
        if not self.state_path.exists():
            return {
                'schema_version': SCHEMA_VERSION,
                'phase': 'draft',
                'iteration': 0,
                'gates': {},
            }
        return json.loads(self.state_path.read_text())

    def write_state(self, st: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        dump(st, self.state_path)

    def set_gate(self, name: str, passed: bool, detail: str = '') -> None:
        st = self.state()
        st.setdefault('gates', {})[name] = {'passed': bool(passed), 'detail': detail}
        self.write_state(st)

    def gate(self, name: str) -> bool:
        return bool(self.state().get('gates', {}).get(name, {}).get('passed'))

    # -- persistence -------------------------------------------------------

    def save_run(self, iteration: int, rec: RunRecord) -> Path:
        p = self.run_record_path(iteration, rec.eval_id, rec.arm, rec.run_index)
        p.parent.mkdir(parents=True, exist_ok=True)
        dump(asdict(rec), p)
        return p

    def load_runs(self, iteration: int) -> list[RunRecord]:
        """Load every run record. Unreadable records raise — never skipped silently."""
        base = self.iteration_dir(iteration) / 'runs'
        out: list[RunRecord] = []
        if not base.is_dir():
            return out
        for p in sorted(base.glob('*/*/run-*/run.json')):
            try:
                out.append(RunRecord(**json.loads(p.read_text())))
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                raise SchemaError(f'{p} is not a readable run record: {e}') from e
        return out

    def save_provenance(self, iteration: int, prov: Provenance) -> None:
        self.iteration_dir(iteration).mkdir(parents=True, exist_ok=True)
        dump(asdict(prov), self.provenance_path(iteration))

    def load_provenance(self, iteration: int) -> Provenance:
        p = self.provenance_path(iteration)
        if not p.exists():
            raise SchemaError(
                f'no provenance at {p}; refusing to report on an unidentified run'
            )
        return Provenance(**json.loads(p.read_text()))
