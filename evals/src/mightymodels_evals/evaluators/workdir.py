from dataclasses import dataclass, field

from pydantic_evals.evaluators import EvaluationReason

from mightymodels_evals.artifacts import run_cmd
from mightymodels_evals.evaluators.base import (
    Check,
    CheckContext,
    TypedEvaluator,
    failed,
    passed,
)
from mightymodels_evals.repo import Repo

_ALWAYS_ALLOWED_UNTRACKED = ('__pycache__',)


@dataclass
class GitStatusClean(Check, TypedEvaluator):
    pathspec: str = ''
    allow_untracked_under: list[str] = field(default_factory=list)

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        allowed = (*self.allow_untracked_under, *_ALWAYS_ALLOWED_UNTRACKED)
        lines = Repo(ctx.output.workdir).status_lines(self.pathspec)
        dirty = [line for line in lines if not any(a in line for a in allowed)]
        if dirty:
            return failed(f'dirty: {dirty[:5]}')

        scope = f' ({self.pathspec})' if self.pathspec else ''
        return passed(f'git status clean{scope}')


@dataclass
class GitDiffEmpty(Check, TypedEvaluator):
    pathspec: str = ''

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        touched = Repo(ctx.output.workdir).diff_names(self.pathspec)
        if touched:
            return failed(f'diff touches: {touched[:5]}')
        return passed(f'no diff ({self.pathspec or "tree"})')


@dataclass
class GitCommitsTouchingAtMost(Check, TypedEvaluator):
    pathspec: str = ''
    max_count: int = 1

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        # catches work that was committed to look clean; diff-based checks miss it
        subjects = Repo(ctx.output.workdir).commit_subjects(self.pathspec)
        scope = self.pathspec or 'tree'
        if len(subjects) <= self.max_count:
            return passed(f'{len(subjects)} commits touch {scope} (max {self.max_count})')
        return failed(
            f'{len(subjects)} commits touch {scope} '
            f'(max {self.max_count}): {subjects[:3]}'
        )


@dataclass
class BranchExists(Check, TypedEvaluator):
    branch: str = ''

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        if Repo(ctx.output.workdir).has_branch(self.branch):
            return passed(f'branch {self.branch} exists')
        return failed(f'branch {self.branch} missing')


@dataclass
class PytestGreen(Check, TypedEvaluator):
    args: str = '-q'

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        code, out = run_cmd(
            ['python3', '-m', 'pytest', *self.args.split()], ctx.output.workdir
        )
        tail = out.strip().splitlines()[-1] if out.strip() else ''
        if code == 0:
            return passed(f'pytest green: {tail}')
        return failed(f'pytest rc={code}: {tail}')
