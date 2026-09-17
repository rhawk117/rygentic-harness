from pathlib import Path

import pytest
from mightymcp.debug import Hypothesis, whats_broken_close, whats_broken_write
from mightymcp.report import (
    ChecklistTask,
    ShippedTask,
    checklist_render,
    report_write,
)

TASKS = [
    ShippedTask(task_id='task-01', shipped='the parser', commit='abc1234'),
    ShippedTask(task_id='task-02', shipped='the writer', commit='def5678'),
]


def hypothesis(**overrides: object) -> Hypothesis:
    fields: dict[str, object] = {
        'symptom': 'the ci lint job is red',
        'attempt': 1,
        'reproduce': '`uv run ruff check .` exits 1 on src/demo.py',
        'hypothesis': 'I believe the new module is the cause because it is the only '
        'file in the diff. If true, reverting it will show it.',
        'test': '`uv run ruff check src/demo.py`',
    }
    return Hypothesis.model_validate(fields | overrides)


def test_report_regenerates_the_sprint_summary(ticket_root: Path) -> None:
    written = report_write(
        'demo', TASKS, 2, ['UB-3 needs a full engineer'], ['the cache']
    )

    assert written.refusals == []
    assert written.path == str(ticket_root.joinpath('REPORT.md'))
    assert ticket_root.joinpath('REPORT.md').read_text(encoding='utf-8') == (
        '# REPORT: demo\n'
        '\n'
        '- task-01: the parser (abc1234)\n'
        '- task-02: the writer (def5678)\n'
        '\n'
        'residuals fixed: 2\n'
        'escalated:\n'
        '- UB-3 needs a full engineer\n'
        'open threads:\n'
        '- the cache\n'
    )


def test_report_says_none_for_the_empty_lists(ticket_root: Path) -> None:
    report_write('demo', TASKS, 0, [], [])

    text = ticket_root.joinpath('REPORT.md').read_text(encoding='utf-8')
    assert text.endswith('escalated:\n- none\nopen threads:\n- none\n')


def test_report_is_regenerated_not_appended(ticket_root: Path) -> None:
    report_write('demo', TASKS, 0, [], [])
    report_write('demo', TASKS[:1], 0, [], [])

    text = ticket_root.joinpath('REPORT.md').read_text(encoding='utf-8')
    assert 'task-02' not in text


def test_report_refuses_over_fifty_lines(ticket_root: Path) -> None:
    threads = [f'thread {number}' for number in range(50)]

    written = report_write('demo', TASKS, 0, [], threads)

    assert written.refusals == ['REPORT.md is 59 lines; the cap is 50']
    assert not ticket_root.joinpath('REPORT.md').exists()


def test_report_refuses_a_ticket_that_does_not_exist(repo: Path) -> None:
    assert (
        report_write('demo', TASKS, 0, [], [])
        .refusals[0]
        .startswith('no ticket directory at')
    )


def test_the_checklist_checks_a_task_that_carries_a_commit() -> None:
    rendered = checklist_render([
        ChecklistTask(label='T1', title='ticket core', sha='abc1234'),
        ChecklistTask(label='T2', title='the brief tools'),
    ])

    assert rendered.refusals == []
    assert rendered.lines == [
        '- [x] T1 ticket core (abc1234)',
        '- [ ] T2 the brief tools',
    ]


def test_the_checklist_refuses_an_entry_without_a_title() -> None:
    rendered = checklist_render([ChecklistTask(label='T1', title='  ')])

    assert rendered.lines == []
    assert rendered.refusals == ['checklist entry 1 is missing a label or a title']


def test_whats_broken_writes_the_schema(ticket_root: Path) -> None:
    written = whats_broken_write('demo', hypothesis())

    assert written.refusals == []
    lines = ticket_root.joinpath('whats-broken.md').read_text(encoding='utf-8')
    assert lines.startswith('# whats-broken: the ci lint job is red\nattempt: 1\n')
    assert '\nreproduce: `uv run ruff check .` exits 1 on src/demo.py\n' in lines
    assert '\nhypothesis: I believe the new module is the cause' in lines
    assert lines.endswith('\ntest: `uv run ruff check src/demo.py`\n')


def test_whats_broken_is_regenerated_per_attempt(ticket_root: Path) -> None:
    whats_broken_write('demo', hypothesis())
    whats_broken_write('demo', hypothesis(attempt=2, symptom='the same job'))

    text = ticket_root.joinpath('whats-broken.md').read_text(encoding='utf-8')
    assert text.startswith('# whats-broken: the same job\nattempt: 2\n')
    assert text.count('attempt:') == 1


@pytest.mark.parametrize('attempt', [0, 4])
def test_whats_broken_refuses_an_attempt_outside_the_breaker(
    ticket_root: Path, attempt: int
) -> None:
    written = whats_broken_write('demo', hypothesis(attempt=attempt))

    assert written.refusals[0].startswith(f'attempt {attempt} is outside 1-3')
    assert not ticket_root.joinpath('whats-broken.md').exists()


def test_whats_broken_refuses_an_empty_field(ticket_root: Path) -> None:
    written = whats_broken_write('demo', hypothesis(test='   '))

    assert written.refusals == ['test is empty']
    assert not ticket_root.joinpath('whats-broken.md').exists()


def test_closing_the_debug_deletes_the_file(ticket_root: Path) -> None:
    whats_broken_write('demo', hypothesis())

    closed = whats_broken_close('demo')

    assert closed.refusals == []
    assert closed.path == str(ticket_root.joinpath('whats-broken.md'))
    assert not ticket_root.joinpath('whats-broken.md').exists()


def test_closing_a_debug_that_is_not_live_is_refused(ticket_root: Path) -> None:
    closed = whats_broken_close('demo')

    assert closed.path is None
    assert closed.refusals[0].startswith('no debug is live')
