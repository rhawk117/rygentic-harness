import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_rules import Finding, audit, main

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def smells_in(findings: list[Finding], path: str) -> set[str]:
    return {finding.smell for finding in findings if finding.path == path}


@pytest.fixture(scope='module')
def dirty_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp('dirty')
    shutil.copytree(FIXTURES / 'dirty', root, dirs_exist_ok=True)
    return root


@pytest.fixture(scope='module')
def clean_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp('clean')
    shutil.copytree(FIXTURES / 'clean', root, dirs_exist_ok=True)
    return root


@pytest.fixture(scope='module')
def dirty_result(dirty_root: Path) -> tuple[list[Finding], dict]:
    return audit(dirty_root)


@pytest.fixture(scope='module')
def dirty_findings(dirty_result: tuple[list[Finding], dict]) -> list[Finding]:
    return dirty_result[0]


@pytest.fixture(scope='module')
def dirty_layout(dirty_result: tuple[list[Finding], dict]) -> dict:
    return dirty_result[1]


@pytest.fixture(scope='module')
def dirty_smells(dirty_findings: list[Finding]) -> set[str]:
    return {finding.smell for finding in dirty_findings}


@pytest.fixture(scope='module')
def clean_result(clean_root: Path) -> tuple[list[Finding], dict]:
    return audit(clean_root)


@pytest.fixture(scope='module')
def clean_findings(clean_result: tuple[list[Finding], dict]) -> list[Finding]:
    return clean_result[0]


def test_detects_lint_leakage(dirty_findings: list[Finding]) -> None:
    assert 'Lint Leakage' in smells_in(dirty_findings, 'AGENTS.md')


def test_detects_blind_reference(dirty_findings: list[Finding]) -> None:
    blind = [f for f in dirty_findings if f.smell == 'Blind Reference']
    assert any('plugin-reorg' in f.message for f in blind)


def test_detects_conflicting_test_commands(dirty_findings: list[Finding]) -> None:
    conflicts = [f for f in dirty_findings if f.smell == 'Conflicting Instructions']
    assert any('npm test' in f.message and 'pnpm test' in f.message for f in conflicts)


def test_detects_missing_apply_to(dirty_findings: list[Finding]) -> None:
    assert 'Scoping' in smells_in(
        dirty_findings, '.github/instructions/frontend.instructions.md'
    )


def test_missing_apply_to_is_an_error(dirty_findings: list[Finding]) -> None:
    scoping = [
        f
        for f in dirty_findings
        if f.smell == 'Scoping' and f.path.endswith('frontend.instructions.md')
    ]
    assert [f.severity for f in scoping] == ['error']


def test_flags_rule_without_paths_as_info_only(dirty_findings: list[Finding]) -> None:
    scoping = [
        f
        for f in dirty_findings
        if f.smell == 'Scoping' and f.path == '.claude/rules/api.md'
    ]
    assert [f.severity for f in scoping] == ['info']


def test_detects_agents_md_invisible_to_claude_code(dirty_smells: set[str]) -> None:
    assert 'Invisible AGENTS.md' in dirty_smells


def test_detects_duplication_across_tools(dirty_smells: set[str]) -> None:
    assert 'Duplication' in dirty_smells


def test_layout_reports_readers_per_file(dirty_layout: dict) -> None:
    by_path = {entry['path']: entry for entry in dirty_layout['files']}
    assert by_path['AGENTS.md']['read_by'] == ['GitHub Copilot']
    assert by_path['CLAUDE.md']['read_by'] == ['Claude Code']


def test_ignores_smells_inside_code_fences(tmp_path: Path) -> None:
    dirty_copy = tmp_path / 'dirty'
    shutil.copytree(FIXTURES / 'dirty', dirty_copy)
    fenced = dirty_copy / 'FENCED.md'
    fenced.write_text('# X\n\n```md\n- Indentation: 2 spaces\n```\n', encoding='utf-8')

    findings, _ = audit(dirty_copy)

    assert not [
        f for f in findings if f.path == 'FENCED.md' and f.smell == 'Lint Leakage'
    ]


def test_no_errors_or_warnings(clean_findings: list[Finding]) -> None:
    blocking = [f for f in clean_findings if f.severity in ('error', 'warn')]
    assert [f'{f.path}:{f.line} {f.smell}: {f.message}' for f in blocking] == []


def test_import_cost_is_info_only(clean_findings: list[Finding]) -> None:
    imports = [f for f in clean_findings if f.smell == 'Import Cost']
    assert sorted({f.severity for f in imports}) == ['info']


def test_skill_paths_are_reported_as_shared(tmp_path: Path) -> None:
    clean_copy = tmp_path / 'clean'
    shutil.copytree(FIXTURES / 'clean', clean_copy)
    skill_dir = clean_copy / '.claude' / 'skills' / 'demo'
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / 'SKILL.md').write_text(
        '---\nname: demo\ndescription: d\n---\n', encoding='utf-8'
    )

    _, layout = audit(clean_copy)

    entry = next(e for e in layout['files'] if e['path'].endswith('demo/SKILL.md'))
    assert entry['read_by'] == ['Claude Code', 'GitHub Copilot']


def test_dirty_fixture_exits_nonzero() -> None:
    assert main([str(FIXTURES / 'dirty')]) == 1


def test_no_fail_suppresses_exit_code() -> None:
    assert main([str(FIXTURES / 'dirty'), '--no-fail']) == 0


def test_clean_fixture_exits_zero() -> None:
    assert main([str(FIXTURES / 'clean')]) == 0


def test_missing_directory_exits_two() -> None:
    assert main([str(FIXTURES / 'does-not-exist')]) == 2
