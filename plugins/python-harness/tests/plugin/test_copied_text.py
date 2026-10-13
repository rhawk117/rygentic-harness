"""Text that several skills must carry word for word is held equal across the copies."""

from pathlib import Path

import pytest
from plugin_layout import DESIGN_SKILLS, PLUGIN_ROOT, SHARED_METHOD_FILES

AGENT_PARAGRAPH = 'If an agent type is not available, stop'
AGENT_PARAGRAPH_SKILLS = (
    'automate-task',
    'build-web-service',
    'data-analysis',
    'data-engineering',
    'design-tests',
)
MCP_BULLET = "- The plugin's MCP server names each tool"


def skill_document(name: str) -> Path:
    return PLUGIN_ROOT / 'skills' / name / 'SKILL.md'


def copy_starting(name: str, prefix: str) -> str:
    [line] = [
        line
        for line in skill_document(name).read_text(encoding='utf-8').splitlines()
        if line.startswith(prefix)
    ]
    return line


class TestSharedMethod:
    @pytest.mark.parametrize('document', SHARED_METHOD_FILES[1:], ids=DESIGN_SKILLS[1:])
    def test_the_four_design_skills_carry_one_shared_method_text(self, document: Path) -> None:
        assert document.read_bytes() == SHARED_METHOD_FILES[0].read_bytes()


class TestCopiedSkillText:
    @pytest.mark.parametrize('name', AGENT_PARAGRAPH_SKILLS[1:])
    def test_the_unavailable_agent_paragraph_is_one_text_in_five_skills(self, name: str) -> None:
        assert copy_starting(name, AGENT_PARAGRAPH) == copy_starting(
            AGENT_PARAGRAPH_SKILLS[0], AGENT_PARAGRAPH
        )

    @pytest.mark.parametrize('name', DESIGN_SKILLS[1:])
    def test_the_mcp_naming_bullet_is_one_text_in_four_skills(self, name: str) -> None:
        assert copy_starting(name, MCP_BULLET) == copy_starting(DESIGN_SKILLS[0], MCP_BULLET)
