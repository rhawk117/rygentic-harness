import re
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

import pytest
from vibe_code_cli.cli import main

type TemplateFill = Callable[[str, Mapping[str, str], re.Pattern[str]], str]


class TestCreateInstructionsTemplate:
    TEMPLATE = (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath(
            'skills',
            'create-rules',
            'assets',
            'instructions.template.md',
        )
    )
    PLACEHOLDER = re.compile(r'\b[A-Z][A-Z0-9_]{2,}\b')
    FILLS = MappingProxyType(
        {
            'GLOB_ONE': 'src/**/*.py',
            'FILES_IN_WORDS': 'the Python sources under src',
            'CARVE_OUTS': 'generated code',
            'STRENGTH_WORD': 'Prefer',
            'CONVENTION_ONE': 'early returns over nested conditionals',
            'CONVENTION_TWO': 'named constants over repeated literals',
            'REASON': 'flat code is easier to review',
            'LANG': 'python',
            'BEFORE_SNIPPET': 'if ready:\n    run()',
            'AFTER_SNIPPET': 'if not ready:\n    return\nrun()',
            'GENERIC_ANTI_PATTERN': 'Nesting three conditionals deep',
            'INSTEAD': 'return early',
            'EXISTING_VIOLATION_POLICY': 'leave it unless the change touches those lines',
            'CHECK_COMMAND_OR_QUESTION': 'ask whether any new branch can return early',
            'REVIEWER_CHECK': 'scanning the diff for nested conditionals',
        }
    )

    @pytest.fixture
    def template_text(self) -> str:
        return self.TEMPLATE.read_text()

    @pytest.fixture
    def filled_rule(self, tmp_path: Path, template_text: str, fill: TemplateFill) -> Path:
        rule = tmp_path / '.claude' / 'rules' / 'demo.md'
        rule.parent.mkdir(parents=True)
        rule.write_text(fill(template_text, self.FILLS, self.PLACEHOLDER))
        return rule

    def test_every_template_placeholder_has_a_fill(
        self, template_text: str, fill: TemplateFill
    ) -> None:
        unfilled = set(self.PLACEHOLDER.findall(fill(template_text, self.FILLS, self.PLACEHOLDER)))

        assert unfilled == set()

    def test_template_frontmatter_holds_paths_and_no_other_key(self, template_text: str) -> None:
        frontmatter = template_text.split('---\n')[1]

        keys = re.findall(r'^([a-z]+):', frontmatter, re.MULTILINE)

        assert keys == ['paths']

    def test_filled_template_passes_strict_validation(
        self, filled_rule: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(['instruction', 'validate', str(filled_rule), '--strict'])

        assert code == 0, capsys.readouterr().out
