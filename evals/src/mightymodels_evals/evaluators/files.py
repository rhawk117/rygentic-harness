import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_evals.evaluators import EvaluationReason

from mightymodels_evals.artifacts import read_rel
from mightymodels_evals.evaluators.base import (
    Check,
    CheckContext,
    TypedEvaluator,
    failed,
    passed,
)


def matching_files(workdir: Path, pattern: str, containing_regex: str) -> list[Path]:
    hits = []
    for path in sorted(workdir.glob(pattern)):
        if not path.is_file():
            continue

        if containing_regex:
            text = path.read_text(encoding='utf-8', errors='replace')
            if not re.search(containing_regex, text):
                continue

        hits.append(path)
    return hits


@dataclass
class FileExists(Check, TypedEvaluator):
    path: str = ''

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        if ctx.output.workdir.joinpath(self.path).is_file():
            return passed(self.path)
        return failed(f'missing: {self.path}')


@dataclass
class PathAbsent(Check, TypedEvaluator):
    path: str = ''

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        if ctx.output.workdir.joinpath(self.path).exists():
            return failed(f'still present: {self.path}')
        return passed(f'absent: {self.path}')


@dataclass
class FileLineCap(Check, TypedEvaluator):
    path: str = ''
    max_lines: int = 0

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        text = read_rel(ctx.output.workdir, self.path)
        if text is None:
            return failed(f'missing: {self.path}')

        count = len(text.rstrip().split('\n'))
        if count <= self.max_lines:
            return passed(f'{self.path}: {count} lines (cap {self.max_lines})')
        return failed(f'{self.path}: {count} lines exceeds cap {self.max_lines}')


@dataclass
class FileContains(Check, TypedEvaluator):
    path: str = ''
    needle: str = ''
    expect: bool = True

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        text = read_rel(ctx.output.workdir, self.path)
        if text is None:
            return failed(f'missing: {self.path}')

        found = self.needle in text
        state = 'found' if found else 'absent'
        if found == self.expect:
            return passed(f'{self.needle!r} {state} in {self.path}')
        return failed(f'{self.needle!r} unexpectedly {state} in {self.path}')


@dataclass
class FileContainsAll(Check, TypedEvaluator):
    path: str = ''
    needles: list[str] = field(default_factory=list)

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        text = read_rel(ctx.output.workdir, self.path)
        if text is None:
            return failed(f'missing: {self.path}')

        missing = [n for n in self.needles if n not in text]
        if not missing:
            return passed(f'all {len(self.needles)} needles in {self.path}')
        return failed(f'{self.path} lacks: {missing}')


@dataclass
class FileRegex(Check, TypedEvaluator):
    path: str = ''
    pattern: str = ''
    expect: bool = True

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        text = read_rel(ctx.output.workdir, self.path)
        if text is None:
            return failed(f'missing: {self.path}')

        match = re.search(self.pattern, text)
        if bool(match) == self.expect:
            detail = match.group(0) if match else 'no match'
            return passed(f'{self.pattern!r} in {self.path}: {detail}')
        state = 'matched' if match else 'missing'
        return failed(f'{self.pattern!r} {state} in {self.path}')


@dataclass
class FileRegexCount(Check, TypedEvaluator):
    path: str = ''
    pattern: str = ''
    minimum: int = 1

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        text = read_rel(ctx.output.workdir, self.path)
        if text is None:
            return failed(f'missing: {self.path}')

        count = len(re.findall(self.pattern, text))
        if count >= self.minimum:
            return passed(f'{count}x {self.pattern!r} in {self.path}')
        return failed(
            f'only {count}x {self.pattern!r} in {self.path} (need {self.minimum})'
        )


@dataclass
class CheckboxCount(Check, TypedEvaluator):
    path: str = ''
    minimum: int = 1

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        text = read_rel(ctx.output.workdir, self.path)
        if text is None:
            return failed(f'missing: {self.path}')

        count = text.count('[x]')
        if count >= self.minimum:
            return passed(f'{count} checked boxes in {self.path}')
        return failed(f'{count} checked boxes in {self.path} (need {self.minimum})')


@dataclass
class GlobCountAtLeast(Check, TypedEvaluator):
    pattern: str = ''
    minimum: int = 1
    containing_regex: str = ''

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        hits = matching_files(ctx.output.workdir, self.pattern, self.containing_regex)
        names = [p.name for p in hits][:6]
        if len(hits) >= self.minimum:
            return passed(f'{len(hits)} files match {self.pattern}: {names}')
        return failed(f'{len(hits)} files match {self.pattern} (need {self.minimum})')


@dataclass
class GlobFileContainsAll(Check, TypedEvaluator):
    pattern: str = ''
    name_regex: str = ''
    needles: list[str] = field(default_factory=list)

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        for path in sorted(ctx.output.workdir.glob(self.pattern)):
            if self.name_regex and not re.search(
                self.name_regex, path.name, re.IGNORECASE
            ):
                continue

            text = path.read_text(encoding='utf-8', errors='replace')
            if all(n in text for n in self.needles):
                return passed(f'{path.name} carries {self.needles}')

        return failed(
            f'no file under {self.pattern} (name~{self.name_regex!r}) '
            f'carries {self.needles}'
        )


@dataclass
class NoGlobFileContains(Check, TypedEvaluator):
    pattern: str = ''
    needle: str = ''

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        offenders = matching_files(
            ctx.output.workdir, self.pattern, re.escape(self.needle)
        )
        if offenders:
            return failed(f'{self.needle!r} appears in {[p.name for p in offenders]}')
        return passed(f'{self.needle!r} in no file under {self.pattern}')
