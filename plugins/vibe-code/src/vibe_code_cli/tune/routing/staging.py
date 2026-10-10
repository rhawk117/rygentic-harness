from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import msgspec

from vibe_code_cli.tune.domain.values import Skill
from vibe_code_cli.tune.errors import UnsafeSkillNameError
from vibe_code_cli.tune.repository import SKILL_FILE, parse_skill_document

STAGED_SKILLS = ('.claude', 'skills')
ROUTING_KEYS = ('disable-model-invocation', 'argument-hint')


def routing_frontmatter(skill: Skill) -> str:
    source = Path(skill.path)
    document = parse_skill_document(source, source.read_text(encoding='utf-8'))
    frontmatter = document.mapping()
    routing: dict[str, object] = {
        key: frontmatter[key] for key in ROUTING_KEYS if key in frontmatter
    }
    if skill.when_to_use:
        routing['when_to_use'] = skill.when_to_use
    if not routing:
        return ''
    return msgspec.yaml.encode(routing).decode()


def render_stub(skill: Skill, description: str) -> str:
    quoted = msgspec.json.encode(description).decode()
    extra = routing_frontmatter(skill)
    header = f'name: {skill.name}\ndescription: {quoted}\n{extra}'
    return f'---\n{header}---\n# {skill.name}\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class StubProject:
    root: Path
    skills: tuple[Skill, ...]

    @property
    def skills_root(self) -> Path:
        return self.root.joinpath(*STAGED_SKILLS).resolve()

    @property
    def team(self) -> frozenset[str]:
        return frozenset(skill.name for skill in self.skills)

    def stub_path(self, skill: Skill) -> Path:
        target = self.skills_root.joinpath(skill.name, SKILL_FILE).resolve()
        if not target.is_relative_to(self.skills_root):
            raise UnsafeSkillNameError(skill.name)
        return target

    def stage(self, descriptions: Mapping[str, str]) -> None:
        for skill in self.skills:
            target = self.stub_path(skill)
            target.parent.mkdir(parents=True)
            target.write_text(render_stub(skill, descriptions[skill.name]), encoding='utf-8')
