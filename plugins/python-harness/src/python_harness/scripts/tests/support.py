"""CLI result capture shared by the tests of the data command modules."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import msgspec
import pytest

ENVELOPE_KEYS = ('schema_version', 'command', 'arguments', 'result', 'caveats')

type YamlDocument = dict[str, Any]
type Main = Callable[[list[str]], int]


@dataclass(frozen=True, slots=True, kw_only=True)
class CliResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def document(self) -> YamlDocument:
        return msgspec.yaml.decode(self.stdout)

    @property
    def result(self) -> YamlDocument:
        return self.document['result']

    @property
    def caveats(self) -> list[str]:
        return self.document['caveats']


@dataclass(frozen=True, slots=True, kw_only=True)
class ScriptRunner:
    main: Main
    capture: pytest.CaptureFixture[str]
    logs: pytest.LogCaptureFixture

    def __call__(self, *arguments: str) -> CliResult:
        self.logs.clear()
        exit_code = self.main(list(arguments))
        captured = self.capture.readouterr()
        diagnostics = captured.err + self.logs.text
        return CliResult(exit_code=exit_code, stdout=captured.out, stderr=diagnostics)
