import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_rules import audit, main

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def smells_in(findings, path):
    return {finding.smell for finding in findings if finding.path == path}


@pytest.fixture(scope='module')
def dirty_root(tmp_path_factory):
    root = tmp_path_factory.mktemp('dirty')
    shutil.copytree(FIXTURES / 'dirty', root, dirs_exist_ok=True)
    return root


@pytest.fixture(scope='module')
def clean_root(tmp_path_factory):
    root = tmp_path_factory.mktemp('clean')
    shutil.copytree(FIXTURES / 'clean', root, dirs_exist_ok=True)
    return root


@pytest.fixture(scope='module')
def dirty_result(dirty_root):
    return audit(dirty_root)


@pytest.fixture(scope='module')
def dirty_findings(dirty_result):
    return dirty_result[0]


@pytest.fixture(scope='module')
def dirty_layout(dirty_result):
    return dirty_result[1]


@pytest.fixture(scope='module')
def dirty_smells(dirty_findings):
    return {finding.smell for finding in dirty_findings}


@pytest.fixture(scope='module')
def clean_result(clean_root):
    return audit(clean_root)


@pytest.fixture(scope='module')
def clean_findings(clean_result):
    return clean_result[0]


def test_detects_lint_leakage(dirty_findings):
    assert 'Lint Leakage' in smells_in(dirty_findings, 'AGENTS.md')


def test_detects_blind_reference(dirty_findings):
    blind = [f for f in dirty_findings if f.smell == 'Blind Reference']
    assert any('plugin-reorg' in f.message for f in blind)


def test_detects_conflicting_test_commands(dirty_findings):
    conflicts = [f for f in dirty_findings if f.smell == 'Conflicting Instructions']
    assert any('npm test' in f.message and 'pnpm test' in f.message for f in conflicts)


def test_detects_missing_apply_to(dirty_findings):
    assert 'Scoping' in smells_in(
        dirty_findings, '.github/instructions/frontend.instructions.md'
    )


def test_missing_apply_to_is_an_error(dirty_findings):
    scoping = [
        f
        for f in dirty_findings
        if f.smell == 'Scoping' and f.path.endswith('frontend.instructions.md')
    ]
    assert ['error'] == [f.severity for f in scoping]


def test_flags_rule_without_paths_as_info_only(dirty_findings):
    scoping = [
        f
        for f in dirty_findings
        if f.smell == 'Scoping' and f.path == '.claude/rules/api.md'
    ]
    assert ['info'] == [f.severity for f in scoping]


def test_detects_agents_md_invisible_to_claude_code(dirty_smells):
    assert 'Invisible AGENTS.md' in dirty_smells


def test_detects_duplication_across_tools(dirty_smells):
    assert 'Duplication' in dirty_smells


def test_layout_reports_readers_per_file(dirty_layout):
    by_path = {entry['path']: entry for entry in dirty_layout['files']}
    assert ['GitHub Copilot'] == by_path['AGENTS.md']['read_by']
    assert ['Claude Code'] == by_path['CLAUDE.md']['read_by']


def test_ignores_smells_inside_code_fences(tmp_path):
    dirty_copy = tmp_path / 'dirty'
    shutil.copytree(FIXTURES / 'dirty', dirty_copy)
    fenced = dirty_copy / 'FENCED.md'
    fenced.write_text('# X\n\n```md\n- Indentation: 2 spaces\n```\n', encoding='utf-8')

    findings, _ = audit(dirty_copy)

    assert not [
        f for f in findings if f.path == 'FENCED.md' and f.smell == 'Lint Leakage'
    ]


def test_no_errors_or_warnings(clean_findings):
    blocking = [f for f in clean_findings if f.severity in ('error', 'warn')]
    assert [] == [f'{f.path}:{f.line} {f.smell}: {f.message}' for f in blocking]


def test_import_cost_is_info_only(clean_findings):
    imports = [f for f in clean_findings if f.smell == 'Import Cost']
    assert ['info'] == sorted({f.severity for f in imports})


def test_skill_paths_are_reported_as_shared(tmp_path):
    clean_copy = tmp_path / 'clean'
    shutil.copytree(FIXTURES / 'clean', clean_copy)
    skill_dir = clean_copy / '.claude' / 'skills' / 'demo'
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / 'SKILL.md').write_text(
        '---\nname: demo\ndescription: d\n---\n', encoding='utf-8'
    )

    _, layout = audit(clean_copy)

    entry = next(e for e in layout['files'] if e['path'].endswith('demo/SKILL.md'))
    assert ['Claude Code', 'GitHub Copilot'] == entry['read_by']


def test_dirty_fixture_exits_nonzero():
    assert main([str(FIXTURES / 'dirty')]) == 1


def test_no_fail_suppresses_exit_code():
    assert main([str(FIXTURES / 'dirty'), '--no-fail']) == 0


def test_clean_fixture_exits_zero():
    assert main([str(FIXTURES / 'clean')]) == 0


def test_missing_directory_exits_two():
    assert main([str(FIXTURES / 'does-not-exist')]) == 2
