"""runners.base.HostAdapter.run — never previously imported by a test.

skill-creator sends stderr to DEVNULL, so a missing CLI, a bad model id and a
genuine non-trigger are indistinguishable. HostAdapter.run must report a missing
CLI as an explicit error instead of silently proceeding.
"""

from __future__ import annotations

from pathlib import Path

from skilleng.runners.base import HostAdapter, RunRequest
from skilleng.schema import Arm


class _MissingCLIAdapter(HostAdapter):
    name = 'missing-cli'
    cli = 'definitely-not-a-real-skilleng-test-binary'
    skill_install_subdir = 'skills'

    def prepare_sandbox(self, sandbox: Path, probe: bool = False) -> Path:
        return Path(sandbox)

    def command(self, req: RunRequest) -> list[str]:
        return [self.cli]


def test_run_reports_a_missing_cli_as_a_failure_not_a_crash(tmp_path: Path) -> None:
    adapter = _MissingCLIAdapter()
    req = RunRequest(
        prompt='p',
        arm=Arm.AVAILABLE,
        run_id='r1',
        cwd=tmp_path,
        event_log=tmp_path / 'events.ndjson',
    )

    result = adapter.run(req, tmp_path)

    assert result.ok is False
    assert result.error is not None
    assert 'not on PATH' in result.error
