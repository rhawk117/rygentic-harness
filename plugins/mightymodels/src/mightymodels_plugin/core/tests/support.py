import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

RECORDER_SOURCE = """#!{python}
import json
import sys
from pathlib import Path

call = {{'argv': sys.argv, 'cwd': str(Path.cwd())}}
with Path({log!r}).open('a', encoding='utf-8') as log:
    log.write(json.dumps(call) + '\\n')
print(0)
"""


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedCall:
    argv: list[str]
    cwd: Path


@dataclass(slots=True, kw_only=True, frozen=True)
class Recorder:
    executable: str
    log: Path

    def calls(self) -> list[RecordedCall]:
        lines = self.log.read_text(encoding='utf-8').splitlines() if self.log.is_file() else []
        return [
            RecordedCall(argv=call['argv'], cwd=Path(call['cwd']))
            for call in map(json.loads, lines)
        ]


@pytest.fixture
def recorder(tmp_path: Path) -> Recorder:
    directory = tmp_path.joinpath('recorder')
    directory.mkdir()
    log = directory.joinpath('calls.jsonl')
    executable = directory.joinpath('record')
    executable.write_text(
        RECORDER_SOURCE.format(python=sys.executable, log=str(log)), encoding='utf-8'
    )
    executable.chmod(0o700)
    return Recorder(executable=str(executable), log=log)
