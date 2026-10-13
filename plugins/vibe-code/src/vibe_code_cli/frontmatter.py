import datetime
from dataclasses import dataclass

import msgspec

from vibe_code_cli.jsondoc import as_object


@dataclass(slots=True, kw_only=True, frozen=True)
class SkillText:
    fields: dict[str, object] | None
    key_problem: str | None
    body: str
    yaml_problem: str | None = None


def split_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != '---':
        return None, text
    closing = next(
        (index for index, line in enumerate(lines[1:], 1) if line.strip() == '---'), None
    )
    if closing is None:
        return None, text
    return ''.join(lines[1:closing]), ''.join(lines[closing + 1 :])


def key_problem_of(fields: object) -> str | None:
    if not isinstance(fields, dict):
        return None
    try:
        msgspec.convert(fields, dict[str, object], builtin_types=(datetime.date, datetime.datetime))
    except msgspec.ValidationError as problem:
        return f'frontmatter keys must be strings ({problem})'
    return None


def parse_skill_text(text: str) -> SkillText:
    raw, body = split_frontmatter(text)
    if raw is None:
        return SkillText(fields=None, key_problem=None, body=body)

    try:
        fields = msgspec.yaml.decode(raw)
    except msgspec.DecodeError as problem:
        first_line = (str(problem).splitlines() or [type(problem).__name__])[0]
        return SkillText(fields=None, key_problem=None, body=body, yaml_problem=first_line)

    if fields is None:
        fields = {}

    return SkillText(fields=as_object(fields), key_problem=key_problem_of(fields), body=body)
