from dataclasses import dataclass
from pathlib import Path

from plugin_evals.artifacts import run_cmd
from plugin_evals.errors import RepoCommandError


def _with_pathspec(args: list[str], pathspec: str) -> list[str]:
    if not pathspec:
        return args
    return [*args, '--', *pathspec.split()]


@dataclass(slots=True, frozen=True)
class Repo:
    root: Path

    def query(self, *args: str) -> str:
        _, out = run_cmd(['git', *args], self.root)
        return out

    def run(self, *args: str) -> None:
        code, out = run_cmd(['git', *args], self.root)
        if code != 0:
            raise RepoCommandError(args, out)

    def init_commit(self, message: str) -> None:
        self.run('init', '-q')
        # runners without a global git identity cannot commit otherwise
        self.run('config', 'user.email', 'evals@mightymodels.invalid')
        self.run('config', 'user.name', 'plugin-evals')
        self.commit_all(message)

    def commit_all(self, message: str) -> None:
        self.run('add', '-A')
        self.run('commit', '-qm', message)

    def checkout_new(self, branch: str) -> None:
        self.run('checkout', '-qb', branch)

    def move(self, src: str, dst: str) -> None:
        self.run('mv', src, dst)

    def status_lines(self, pathspec: str = '') -> list[str]:
        out = self.query(*_with_pathspec(['status', '--porcelain'], pathspec))
        return [line for line in out.splitlines() if line.strip()]

    def diff_names(self, pathspec: str = '') -> list[str]:
        out = self.query(*_with_pathspec(['diff', '--name-only'], pathspec))
        return [line for line in out.splitlines() if line.strip()]

    def commit_subjects(self, pathspec: str = '') -> list[str]:
        out = self.query(*_with_pathspec(['log', '--oneline'], pathspec))
        return [line for line in out.splitlines() if line.strip()]

    def has_branch(self, name: str) -> bool:
        return name in self.query('branch', '--list', name)
