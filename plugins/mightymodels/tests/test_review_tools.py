from pathlib import Path

import pytest
from mightymcp.review import (
    BLOCK,
    CLEAR,
    CONDITIONS,
    Finding,
    GradeInput,
    findings_merge,
    grade_compute,
    pr_comment_render,
    review_report_write,
    review_verdict,
)

CATEGORIES = (
    'names',
    'functions',
    'comments',
    'error_handling',
    'tests',
    'classes_and_solid',
    'components_and_architecture',
    'simplicity_and_duplication',
)


def finding(**overrides: object) -> Finding:
    fields: dict[str, object] = {
        'id': 'MV-1',
        'severity': 'Medium',
        'file': 'src/api/limits.py',
        'line': '17',
        'source': 'merge-vader',
        'summary': 'the new parser has no tests',
    }
    return Finding.model_validate(fields | overrides)


def grades(**overrides: str) -> GradeInput:
    return GradeInput.model_validate(
        dict.fromkeys(CATEGORIES, 'A') | dict(overrides.items())
    )


def test_findings_on_the_same_line_merge_and_keep_both_ids() -> None:
    merged = findings_merge([
        finding(id='MV-1', severity='Medium'),
        finding(id='UB-2', severity='Medium', source='uncle-bob'),
    ])

    assert merged.refusals == []
    assert len(merged.findings) == 1
    assert merged.findings[0].ids == ['MV-1', 'UB-2']
    assert merged.findings[0].sources == ['merge-vader', 'uncle-bob']
    assert merged.findings[0].note == ''


def test_overlapping_spans_are_one_defect() -> None:
    merged = findings_merge([
        finding(id='UB-1', line='142-149', source='uncle-bob'),
        finding(id='MV-2', line='145'),
    ])

    assert [entry.line for entry in merged.findings] == ['142-149']
    assert merged.findings[0].ids == ['UB-1', 'MV-2']


def test_findings_that_do_not_overlap_stay_separate() -> None:
    merged = findings_merge([
        finding(id='MV-1', line='17'),
        finding(id='MV-2', line='18'),
        finding(id='UB-3', file='src/other.py', line='17', source='uncle-bob'),
    ])

    assert [entry.ids for entry in merged.findings] == [['MV-1'], ['MV-2'], ['UB-3']]


def test_a_chain_of_overlaps_merges_the_same_in_either_order() -> None:
    chain = [
        finding(id='UB-1', line='1-5', source='uncle-bob'),
        finding(id='UB-2', line='4-12', source='uncle-bob'),
        finding(id='MV-1', severity='High', line='10-15'),
    ]

    for order in (chain, list(reversed(chain))):
        merged = findings_merge(order)

        assert len(merged.findings) == 1
        assert merged.findings[0].line == '1-15'
        assert merged.findings[0].severity == 'High'
        assert sorted(merged.findings[0].ids) == ['MV-1', 'UB-1', 'UB-2']


def test_uncle_bob_blocker_merges_as_critical() -> None:
    merged = findings_merge([
        finding(id='UB-1', severity='Blocker', source='uncle-bob'),
        finding(id='MV-2', severity='High'),
    ])

    entry = merged.findings[0]
    assert entry.severity == 'Critical'
    assert entry.severities == ['Blocker', 'High']
    assert entry.note == 'UB-1 Blocker and MV-2 High; kept Critical'
    assert entry.needs_user is False


def test_the_higher_severity_wins_and_both_are_noted() -> None:
    merged = findings_merge([
        finding(id='MV-1', severity='Low', summary='a nit'),
        finding(id='UB-2', severity='Medium', source='uncle-bob', summary='no tests'),
    ])

    entry = merged.findings[0]
    assert (entry.severity, entry.summary) == ('Medium', 'no tests')
    assert entry.note == 'UB-2 Medium and MV-1 Low; kept Medium'


def test_a_two_level_gap_is_the_users_to_judge() -> None:
    merged = findings_merge([
        finding(id='MV-1', severity='Critical'),
        finding(id='UB-2', severity='Medium', source='uncle-bob'),
    ])

    assert merged.needs_user is True
    assert merged.findings[0].needs_user is True
    assert '2 levels apart' in merged.findings[0].note


@pytest.mark.parametrize(
    ('overrides', 'expected'),
    [
        ({'severity': 'Nasty'}, "MV-1 is 'Nasty'"),
        ({'source': 'grumpy'}, "MV-1 came from 'grumpy'"),
        ({'line': 'somewhere'}, "MV-1 cites line 'somewhere'"),
    ],
)
def test_a_finding_outside_the_tables_is_refused(
    overrides: dict[str, object], expected: str
) -> None:
    merged = findings_merge([finding(**overrides)])

    assert merged.findings == []
    assert merged.refusals[0].startswith(expected)


@pytest.mark.parametrize(
    ('severities', 'blocked', 'verdict', 'rule'),
    [
        (['Critical'], False, BLOCK, 'a Critical or High finding'),
        (['High'], False, BLOCK, 'a Critical or High finding'),
        (['Blocker'], False, BLOCK, 'a Critical or High finding'),
        (['Low', 'High'], False, BLOCK, 'a Critical or High finding'),
        (['Critical'], True, BLOCK, 'a Critical or High finding'),
        (['Medium'], False, CONDITIONS, 'a Medium finding'),
        (['Low', 'Medium'], False, CONDITIONS, 'a Medium finding'),
        (['Low'], False, CLEAR, 'no Critical, High, or Medium finding'),
        ([], False, CLEAR, 'no Critical, High, or Medium finding'),
    ],
)
def test_the_verdict_table_holds(
    severities: list[str], verdict: str, rule: str, *, blocked: bool
) -> None:
    findings = [
        finding(id=f'MV-{number}', severity=severity)
        for number, severity in enumerate(severities, start=1)
    ]

    decided = review_verdict(findings, security_unknown_blocked=blocked)

    assert (decided.verdict, decided.rule) == (verdict, rule)


@pytest.mark.parametrize('severities', [[], ['Low'], ['Medium']])
def test_an_unknown_blocked_security_question_never_clears(severities: list[str]) -> None:
    findings = [finding(severity=severity) for severity in severities]

    decided = review_verdict(findings, security_unknown_blocked=True)

    assert decided.verdict == CONDITIONS
    assert 'UNKNOWN-BLOCKED' in decided.rule


def test_a_verdict_over_an_unknown_severity_is_refused() -> None:
    decided = review_verdict([finding(severity='Spicy')])

    assert decided.verdict is None
    assert decided.refusals


def test_every_a_grades_an_a() -> None:
    result = grade_compute(grades())

    assert (result.grade, result.score, result.capped) == ('A', 4.0, False)


def test_the_weighted_mean_uses_the_category_weights() -> None:
    result = grade_compute(
        grades(
            functions='B',
            comments='C',
            error_handling='B',
            simplicity_and_duplication='C',
            components_and_architecture='B',
        )
    )

    assert (result.score, result.grade) == (3.25, 'B')
    assert result.rule == 'weighted mean 3.25 is B'


@pytest.mark.parametrize(
    ('categories', 'score', 'grade'),
    [
        (dict.fromkeys(CATEGORIES, 'F'), 0.0, 'F'),
        (dict.fromkeys(CATEGORIES, 'D'), 1.0, 'D'),
        (dict.fromkeys(CATEGORIES, 'C'), 2.0, 'C'),
        (dict.fromkeys(CATEGORIES, 'B'), 3.0, 'B'),
    ],
)
def test_the_bands_sit_where_report_md_puts_them(
    categories: dict[str, str], score: float, grade: str
) -> None:
    result = grade_compute(GradeInput.model_validate(categories))

    assert (result.score, result.grade) == (score, grade)


@pytest.mark.parametrize(('mode', 'capped'), [('pure', 'D'), ('calibrated', 'C')])
def test_no_tests_caps_the_grade(mode: str, capped: str) -> None:
    result = grade_compute(grades(), mode, tests_present=False)

    assert (result.grade, result.capped) == (capped, True)
    assert result.score == 4.0
    assert result.rule == f'no tests: {mode} mode caps the grade at {capped}'


def test_the_cap_does_not_raise_a_grade_that_is_already_lower() -> None:
    result = grade_compute(
        GradeInput.model_validate(dict.fromkeys(CATEGORIES, 'F')),
        'pure',
        tests_present=False,
    )

    assert (result.grade, result.capped) == ('F', False)


def test_the_cap_does_not_apply_when_tests_are_present() -> None:
    result = grade_compute(grades(), 'pure', tests_present=True)

    assert (result.grade, result.capped) == ('A', False)


def test_an_unknown_letter_or_mode_is_refused() -> None:
    result = grade_compute(grades(names='great'), 'strict')

    assert result.grade is None
    assert result.refusals == [
        "names is graded 'great'; expected A, B, C, D, F",
        "unknown mode 'strict'; expected pure, calibrated",
    ]


@pytest.mark.parametrize(
    ('reviewer', 'name'),
    [('merge-vader', 'MERGE-VADER-REPORT.md'), ('uncle-bob', 'UNCLE-BOB-REPORT.md')],
)
def test_each_reviewer_writes_its_own_report(
    ticket_root: Path, reviewer: str, name: str
) -> None:
    written = review_report_write('demo', reviewer, '# report\n\nVERDICT: CLEAR')

    assert written.refusals == []
    path = ticket_root.joinpath('review', name)
    assert written.path == str(path)
    assert path.read_text(encoding='utf-8').endswith('VERDICT: CLEAR\n')


def test_a_third_reviewer_is_refused(ticket_root: Path) -> None:
    written = review_report_write('demo', 'grumpy', '# report')

    assert written.path is None
    assert written.refusals == [
        "unknown reviewer 'grumpy'; expected merge-vader, uncle-bob"
    ]
    assert not ticket_root.joinpath('review').exists()


def test_an_empty_report_body_is_refused(ticket_root: Path) -> None:
    assert review_report_write('demo', 'uncle-bob', '  ').refusals == ['body is empty']


def test_a_report_outside_the_ticket_tree_is_refused(repo: Path) -> None:
    assert review_report_write('../evil', 'uncle-bob', '# report').refusals


def test_the_pr_comment_groups_findings_by_severity() -> None:
    comment = pr_comment_render(
        BLOCK,
        [
            finding(id='MV-1', severity='High', summary='the nightly report breaks'),
            finding(id='UB-2', severity='Blocker', source='uncle-bob', summary='cycle'),
            finding(id='MV-3', severity='High', summary='the gate was lowered'),
        ],
    )

    assert comment.text.splitlines() == [
        'VERDICT: BLOCK',
        '',
        '## Findings',
        '',
        '### Critical',
        '',
        '- UB-2 | `src/api/limits.py:17` | cycle',
        '',
        '### High',
        '',
        '- MV-1 | `src/api/limits.py:17` | the nightly report breaks',
        '- MV-3 | `src/api/limits.py:17` | the gate was lowered',
    ]


def test_a_clear_comment_says_there_are_no_findings() -> None:
    comment = pr_comment_render(CLEAR, [])

    assert comment.text.splitlines() == [
        'VERDICT: CLEAR',
        '',
        '## Findings',
        '',
        '- none',
    ]


def test_conditions_are_enumerated_only_for_merge_with_conditions() -> None:
    findings = [finding(id='MV-1', severity='Medium', summary='the parser has no tests')]

    conditioned = pr_comment_render(CONDITIONS, findings)
    blocked = pr_comment_render(BLOCK, findings)

    assert '## Conditions' in conditioned.text
    assert '- MV-1: the parser has no tests' in conditioned.text
    assert '## Conditions' not in blocked.text


def test_remediation_replaces_the_default_conditions() -> None:
    comment = pr_comment_render(
        CONDITIONS,
        [finding(severity='Medium')],
        ['add the two malformed-input cases; verify with pytest tests/test_parser.py'],
    )

    assert comment.text.endswith(
        '## Conditions\n- add the two malformed-input cases; verify with pytest '
        'tests/test_parser.py\n'
    )


def test_an_unknown_verdict_renders_nothing() -> None:
    comment = pr_comment_render('LGTM', [])

    assert comment.text == ''
    assert comment.refusals == [
        "unknown verdict 'LGTM'; expected BLOCK, MERGE WITH CONDITIONS, CLEAR"
    ]
