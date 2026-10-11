"""Failures that stop the gate before any verification tool starts."""

from python_harness.core.errors import PythonHarnessError


class LauncherUnavailableError(PythonHarnessError):
    def __init__(self, program: str) -> None:
        super().__init__(f'{program} is not on PATH; the gate launches its tools with it')
        self.program = program


class InvalidRuffVersionError(PythonHarnessError):
    def __init__(self, option: str, variable: str, value: str) -> None:
        super().__init__(
            f'the {option} option must be a ruff version like 1.2.3, not {value!r}'
            f' (read from {variable})'
        )
        self.option = option
        self.variable = variable
        self.value = value
