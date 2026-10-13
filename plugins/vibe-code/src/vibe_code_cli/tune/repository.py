import hashlib
from collections import ChainMap
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from itertools import groupby
from operator import attrgetter, itemgetter
from pathlib import Path
from typing import Protocol, Self, runtime_checkable

import msgspec
import yaml

from vibe_code_cli.tune.domain.values import LoopOptions, Skill, Split, TriggerExample
from vibe_code_cli.tune.errors import (
    DuplicateSkillError,
    MalformedTriggerSetError,
    MissingFrontmatterError,
    TruncatedRequestError,
)
from vibe_code_cli.tune.locking import write_atomically
from vibe_code_cli.tune.policy import FrontmatterMapping, Rewrite, SkillFilePolicy

FENCE = '---'
SKILL_FILE = 'SKILL.md'

type TriggerTextProblem = MalformedTriggerSetError | TruncatedRequestError


@runtime_checkable
class PendingWrite(Protocol):
    @property
    def path(self) -> Path: ...

    def commit(self) -> None: ...


@runtime_checkable
class SkillRepository(Protocol):
    def discover(self, locations: Sequence[Path]) -> tuple[Skill, ...]: ...

    def plan_write(self, skill: Skill, description: str) -> PendingWrite: ...


@runtime_checkable
class TriggerSetReader(Protocol):
    def read(self, path: Path, options: LoopOptions) -> tuple[TriggerExample, ...]: ...


class Frontmatter(msgspec.Struct, frozen=True, kw_only=True):
    name: str
    description: str
    when_to_use: str = ''


class TriggerEntry(msgspec.Struct, frozen=True, kw_only=True):
    request: str
    skills: tuple[str, ...] = ()

    @property
    def stratum(self) -> tuple[str, ...]:
        return tuple(sorted(self.skills))


@dataclass(slots=True, kw_only=True, frozen=True)
class SkillDocument:
    frontmatter: str
    body: str

    def render(self) -> str:
        return f'{FENCE}\n{self.frontmatter}{FENCE}\n{self.body}'

    def mapping(self) -> FrontmatterMapping:
        return msgspec.yaml.decode(self.frontmatter, type=dict[str, object])

    def mapping_or_none(self) -> FrontmatterMapping | None:
        try:
            return self.mapping()
        except msgspec.DecodeError:
            return None

    def description_node(self) -> yaml.Node | None:
        root = yaml.compose(self.frontmatter)
        if not isinstance(root, yaml.MappingNode):
            return None

        values = (
            value
            for key, value in root.value
            if isinstance(value, yaml.Node) and key.value == 'description'
        )
        return next(values, None)

    def with_description(self, path: Path, description: str) -> Self:
        node = self.description_node()
        if node is None or node.start_mark is None or node.end_mark is None:
            raise MissingFrontmatterError(path)

        start = node.start_mark.index
        end = node.end_mark.index
        trailing = ''
        if self.frontmatter[start:end].endswith('\n'):
            trailing = '\n'

        replacement = msgspec.json.encode(description).decode() + trailing
        frontmatter = self.frontmatter[:start] + replacement + self.frontmatter[end:]
        return replace(self, frontmatter=frontmatter)


def parse_skill_document(path: Path, text: str) -> SkillDocument:
    normalized = text.replace('\r\n', '\n')
    if not normalized.startswith(f'{FENCE}\n'):
        raise MissingFrontmatterError(path)

    remainder = normalized.removeprefix(f'{FENCE}\n')
    frontmatter, fence, body = remainder.partition(f'\n{FENCE}\n')
    if not fence:
        raise MissingFrontmatterError(path)

    return SkillDocument(frontmatter=f'{frontmatter}\n', body=body)


def read_skill(path: Path) -> Skill:
    document = parse_skill_document(path, path.read_text(encoding='utf-8'))
    try:
        frontmatter = msgspec.yaml.decode(document.frontmatter, type=Frontmatter)
    except (msgspec.ValidationError, msgspec.DecodeError) as problem:
        raise MissingFrontmatterError(path) from problem

    return Skill(
        name=frontmatter.name,
        path=str(path.resolve()),
        description=frontmatter.description.strip(),
        when_to_use=frontmatter.when_to_use.strip(),
    )


def skill_paths_at(location: Path) -> list[Path]:
    if location.is_dir():
        return sorted(location.glob(f'*/{SKILL_FILE}'))

    return [location]


@dataclass(slots=True, kw_only=True, frozen=True)
class PlannedWrite:
    path: Path
    content: str

    def commit(self) -> None:
        write_atomically(self.path, self.content.encode('utf-8'))


@dataclass(slots=True, kw_only=True, frozen=True)
class FileSkillRepository:
    files: SkillFilePolicy = field(default_factory=SkillFilePolicy)

    def discover(self, locations: Sequence[Path]) -> tuple[Skill, ...]:
        paths = [path for location in locations for path in skill_paths_at(location)]
        skills = tuple(read_skill(path) for path in paths)
        names = [skill.name for skill in skills]
        repeated = (name for name in names if names.count(name) > 1)
        if duplicate := next(repeated, None):
            raise DuplicateSkillError(duplicate)
        return skills

    def plan_write(self, skill: Skill, description: str) -> PlannedWrite:
        path = Path(skill.path)
        original = path.read_bytes().decode('utf-8')

        document = parse_skill_document(path, original)
        before = document.mapping()
        if problem := self.files.get_stale_skill_problem(skill, before):
            raise problem

        after = document.with_description(path, description)
        rewrite = Rewrite(
            path=path,
            description=description,
            original=before,
            rewritten=after.mapping_or_none(),
        )

        if problem := self.files.get_rewrite_problem(rewrite):
            raise problem

        rendered = after.render()
        if '\r\n' in original:
            rendered = rendered.replace('\n', '\r\n')

        return PlannedWrite(path=path, content=rendered)


@dataclass(slots=True, kw_only=True, frozen=True)
class StratifiedSplitter:
    options: LoopOptions

    def rank(self, entry: TriggerEntry) -> str:
        key = f'{self.options.seed}:{entry.request}'
        return hashlib.sha256(key.encode()).hexdigest()

    def split_stratum(self, entries: Sequence[TriggerEntry]) -> dict[str, Split]:
        keyed = sorted(((self.rank(entry), entry) for entry in entries), key=itemgetter(0))

        ranked = [entry for _, entry in keyed]

        validation_count = round(len(ranked) * self.options.validation_fraction)

        held_out = {entry.request: Split.VALIDATION for entry in ranked[:validation_count]}
        training = {entry.request: Split.TRAIN for entry in ranked[validation_count:]}
        splitted = ChainMap(held_out, training)
        return dict(splitted)

    def assign(self, entries: Sequence[TriggerEntry]) -> tuple[TriggerExample, ...]:
        by_stratum = sorted(entries, key=attrgetter('stratum'))
        grouped_strata = groupby(by_stratum, key=attrgetter('stratum'))
        grouped_splits = tuple(self.split_stratum(list(group)) for _, group in grouped_strata)
        split_mapping = ChainMap(*grouped_splits)

        return tuple(
            TriggerExample(
                request_id=f'r{index:03d}',
                request=entry.request,
                expected=frozenset(entry.skills),
                split=split_mapping[entry.request],
            )
            for index, entry in enumerate(entries, start=1)
        )


def plain_request_nodes(root: yaml.Node | None) -> list[yaml.ScalarNode]:
    if not isinstance(root, yaml.SequenceNode):
        return []
    return [
        value
        for item in root.value
        if isinstance(item, yaml.MappingNode)
        for key, value in item.value
        if key.value == 'request' and isinstance(value, yaml.ScalarNode) and value.style is None
    ]


def ends_before_comment(node: yaml.ScalarNode, lines: Sequence[str]) -> bool:
    mark = node.end_mark
    if mark is None:
        return False

    return '#' in lines[mark.line][mark.column :]


def comment_truncated_requests(root: yaml.Node | None, text: str) -> list[str]:
    lines = text.splitlines()
    nodes = plain_request_nodes(root)
    return [node.value for node in nodes if ends_before_comment(node, lines)]


@dataclass(slots=True, kw_only=True, frozen=True)
class YamlTriggerSetReader:
    def read(self, path: Path, options: LoopOptions) -> tuple[TriggerExample, ...]:
        text = path.read_text(encoding='utf-8')
        if problem := self.get_text_problem(path, text):
            raise problem

        try:
            entries = msgspec.yaml.decode(text, type=list[TriggerEntry])
        except msgspec.ValidationError as problem:
            raise MalformedTriggerSetError(path, str(problem)) from None

        strata_splitter = StratifiedSplitter(options=options)
        return strata_splitter.assign(entries)

    def get_text_problem(self, path: Path, text: str) -> TriggerTextProblem | None:
        try:
            root = yaml.compose(text)
        except yaml.YAMLError as problem:
            lines = str(problem).splitlines()
            return MalformedTriggerSetError(path, lines[0])

        if not (truncated := comment_truncated_requests(root, text)):
            return None

        return TruncatedRequestError(truncated[0])
