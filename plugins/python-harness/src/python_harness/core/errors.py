"""Failures every python-harness command reports as a message instead of a traceback."""

from pathlib import Path


class PythonHarnessError(Exception):
    pass


class PathOutsideWorkspaceError(PythonHarnessError):
    def __init__(self, path: Path, root: Path) -> None:
        super().__init__(f'{path} is outside the workspace root {root}')
        self.path = path
        self.root = root


class WorkspaceRootMissingError(PythonHarnessError):
    def __init__(self, root: Path) -> None:
        super().__init__(f'workspace root {root} is not a directory')
        self.root = root


class TargetPathMissingError(PythonHarnessError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'target path {path} does not exist')
        self.path = path


class GitUnavailableError(PythonHarnessError):
    def __init__(self) -> None:
        super().__init__('git is not on PATH; a diff target needs git')


class GitCommandError(PythonHarnessError):
    def __init__(self, arguments: tuple[str, ...], exit_code: int, stderr: str) -> None:
        command = ' '.join(arguments)
        super().__init__(f'git {command} exited {exit_code}: {stderr.strip()}')
        self.arguments = arguments
        self.exit_code = exit_code
        self.stderr = stderr


class UvWorkspaceError(PythonHarnessError):
    def __init__(self, reason: str) -> None:
        super().__init__(f'uv workspace discovery failed: {reason}')
        self.reason = reason
