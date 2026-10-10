"""PublishingService: the report, lint and writing tuned descriptions back."""

from pathlib import Path

import msgspec
import pytest
from vibe_code_cli.tune.repository import read_skill
from vibe_code_cli.tune.tests.agent import ScriptedAgent
from vibe_code_cli.tune.tests.support import MemoryRun


class TestBeforeBaseline:
    def test_report_says_judging_is_unfinished(self, started: MemoryRun) -> None:
        started.tuning.next_work()
        assert 'Baseline judging has not finished yet.' in started.publishing.report()

    def test_apply_has_nothing_to_write(self, started: MemoryRun) -> None:
        result = started.publishing.apply(dry_run=True)
        assert not result.written
        assert result.changes == ()


class TestCompetingSkillsSection:
    def test_report_says_none_recorded_for_the_subagent_judge(self, started: MemoryRun) -> None:
        report = started.publishing.report()
        assert '## Competing skills' in report
        assert 'None recorded; the subagent judge sees only the tuned skills.' in report


class TestAfterRun:
    @pytest.fixture
    def finished(self, started: MemoryRun, scripted_agent: ScriptedAgent) -> MemoryRun:
        scripted_agent.drive(started.tuning, started.packets)
        return started

    def test_apply_writes_tuned_descriptions(self, finished: MemoryRun, skills_dir: Path) -> None:
        result = finished.publishing.apply(dry_run=False)
        assert result.written
        assert result.changes
        for change in result.changes:
            path = skills_dir.joinpath(change.skill, 'SKILL.md')
            assert read_skill(path).description == change.description

    def test_dry_run_leaves_files_alone(self, finished: MemoryRun, skills_dir: Path) -> None:
        before = {p: p.read_bytes() for p in skills_dir.rglob('SKILL.md')}
        assert finished.publishing.apply(dry_run=True).changes
        assert {p: p.read_bytes() for p in skills_dir.rglob('SKILL.md')} == before

    def test_report_lists_every_changed_skill(self, finished: MemoryRun) -> None:
        report = finished.publishing.report()
        changed = finished.publishing.apply(dry_run=True).changes
        assert all(f'### {change.skill}' in report for change in changed)

    def test_apply_preserves_crlf_endings_and_other_frontmatter(
        self, finished: MemoryRun, skills_dir: Path
    ) -> None:
        path = skills_dir.joinpath('jira', 'SKILL.md')
        before = msgspec.yaml.decode(
            path.read_text(encoding='utf-8').split('---\n', 2)[1], type=dict[str, object]
        )
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))

        result = finished.publishing.apply(dry_run=False)

        change = next(c for c in result.changes if c.skill == 'jira')
        after_bytes = path.read_bytes()
        assert b'\r\n' in after_bytes
        assert after_bytes.replace(b'\r\n', b'').count(b'\n') == 0
        after = msgspec.yaml.decode(
            path.read_text(encoding='utf-8').split('---\n', 2)[1], type=dict[str, object]
        )
        assert after['description'] == change.description
        assert after['name'] == before['name']
        assert after['license'] == before['license']


class TestLint:
    def test_overlapping_descriptions_are_reported(
        self, memory_run: MemoryRun, tmp_path: Path
    ) -> None:
        for name in ('boards', 'tickets'):
            folder = tmp_path.joinpath('lint', name)
            folder.mkdir(parents=True)
            folder.joinpath('SKILL.md').write_text(
                f'---\nname: {name}\ndescription: Use for jira {name}.\n---\n', encoding='utf-8'
            )
        found = memory_run.publishing.lint([tmp_path.joinpath('lint')])
        assert len(found) == 1
        assert 'jira' in found[0]
