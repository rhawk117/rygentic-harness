from pathlib import Path

from mightymodels_evals.report import (
    AssertionRow,
    CaseRow,
    Payload,
    SkillRow,
    VariantSummary,
    render_html,
    write_report,
)


def _payload() -> Payload:
    win = AssertionRow(name='brief within cap', passed=True, reason='18 lines (cap 80)')
    loss = AssertionRow(
        name='brief within cap', passed=False, reason='missing: briefs/task-01.md'
    )
    with_case = CaseRow(
        name='agents-assemble-two-tasks',
        skill='agents-assemble',
        duration=1.0,
        assertions=[win],
    )
    base_case = CaseRow(
        name='agents-assemble-two-tasks',
        skill='agents-assemble',
        duration=0.5,
        assertions=[loss],
    )
    return Payload(
        generated_at='2026-08-20T00:00:00+00:00',
        runner='test',
        mode='replay',
        variants={
            'with_skill': VariantSummary(
                cases=[with_case], passed=1, total=1, pass_rate=1.0, failures=[]
            ),
            'without_skill': VariantSummary(
                cases=[base_case], passed=0, total=1, pass_rate=0.0, failures=['boom']
            ),
        },
        skills=[SkillRow(skill='agents-assemble', with_skill=1.0, without_skill=0.0)],
    )


def test_render_html_carries_tiles_rows_and_failures() -> None:
    page = render_html(_payload())
    assert 'mightymodels eval report' in page
    assert '100%' in page
    assert 'brief within cap' in page
    assert 'pass' in page
    assert 'fail' in page
    assert 'Task failures: boom' in page
    assert '__ROWS__' not in page


def test_write_report_emits_json_and_html(tmp_path: Path) -> None:
    json_path = tmp_path.joinpath('out', 'r.json')
    html_path = tmp_path.joinpath('out', 'r.html')
    write_report(_payload(), json_path, html_path)
    assert json_path.is_file()
    assert html_path.read_text(encoding='utf-8').startswith('<!doctype html>')
