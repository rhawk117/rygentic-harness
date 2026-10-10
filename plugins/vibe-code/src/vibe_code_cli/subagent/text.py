import re
from dataclasses import dataclass

import msgspec

from vibe_code_cli.frontmatter import parse_skill_text, split_frontmatter

UNQUOTED_DESCRIPTION = re.compile(r'^description:[ \t]*(?P<value>[^\s"\'>|].*)$', re.MULTILINE)


@dataclass(slots=True, kw_only=True, frozen=True)
class AgentText:
    has_block: bool
    fields: dict[str, object] | None
    yaml_problem: str | None
    key_problem: str | None
    body: str
    unquoted_colon: bool = False


def parse_agent_text(text: str) -> AgentText:
    raw, body = split_frontmatter(text)
    if raw is None:
        return AgentText(
            has_block=False, fields=None, yaml_problem=None, key_problem=None, body=text,
        )
    skill = parse_skill_text(text)
    unquoted = UNQUOTED_DESCRIPTION.search(raw)
    if unquoted is None:
        return AgentText(
            has_block=True,
            fields=skill.fields,
            yaml_problem=skill.yaml_problem,
            key_problem=skill.key_problem,
            body=body,
        )

    if skill.yaml_problem is not None and ':' in unquoted['value']:
        skill = parse_skill_text(f'---\n{quote_description(raw, unquoted)}---\n{body}')
        return AgentText(
            has_block=True,
            fields=skill.fields,
            yaml_problem=skill.yaml_problem,
            key_problem=skill.key_problem,
            body=body,
            unquoted_colon=True,
        )
    description = (skill.fields or {}).get('description')
    has_colon = isinstance(description, str) and ':' in description
    return AgentText(
        has_block=True,
        fields=skill.fields,
        yaml_problem=skill.yaml_problem,
        key_problem=skill.key_problem,
        body=body,
        unquoted_colon=has_colon,
    )


def quote_description(raw: str, unquoted: re.Match[str]) -> str:
    quoted = msgspec.json.encode(unquoted['value']).decode()
    return f'{raw[: unquoted.start()]}description: {quoted}{raw[unquoted.end() :]}'
