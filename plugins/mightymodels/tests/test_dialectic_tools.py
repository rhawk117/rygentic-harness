from pathlib import Path

import pytest
from mightymcp.dialectic import (
    DialecticOption,
    DialecticRecord,
    dialectic_record_write,
    dialectic_score,
)


def option(name: str, **overrides: object) -> DialecticOption:
    return DialecticOption.model_validate({'name': name} | overrides)


def record(**overrides: object) -> DialecticRecord:
    fields: dict[str, object] = {
        'fork': 'Retry in the client or in the consumer',
        'options': ['A: client retry, cheap', 'B: consumer retry, expensive'],
        'worst_found': ['A: High, src/client.py:88', 'B: none'],
        'decided_by': 'rung 1 (found defects)',
        'decision': 'B, because the High against A is not against B',
        'reopen_if': 'the consumer stops owning the idempotency key',
        'unexamined': 'the queue redelivery window',
    }
    return DialecticRecord.model_validate(fields | overrides)


def test_rung_one_decides_on_a_high_against_one_option() -> None:
    decided = dialectic_score([option('A', worst='High'), option('B')])

    assert (decided.winner, decided.rung, decided.rung_name) == ('B', 1, 'found defects')
    assert decided.rule == 'Critical or High against A, not B'


def test_rung_one_decides_on_one_severity_level_below_high() -> None:
    decided = dialectic_score([option('A', worst='Medium'), option('B', worst='Low')])

    assert (decided.winner, decided.rung) == ('B', 1)
    assert decided.rule == 'B is worst at Low, a level better than A at Medium'


def test_an_equal_worst_severity_does_not_decide_rung_one() -> None:
    decided = dialectic_score([
        option('A', worst='High', reversal_cost='expensive'),
        option('B', worst='High', reversal_cost='cheap'),
    ])

    assert (decided.winner, decided.rung) == ('B', 2)


def test_a_tie_for_the_best_worst_severity_does_not_decide_rung_one() -> None:
    decided = dialectic_score([
        option('A', worst='High'),
        option('B', conforms=True),
        option('C'),
    ])

    assert (decided.winner, decided.rung) == ('B', 3)


def test_rung_two_takes_the_option_that_is_cheaper_to_undo() -> None:
    decided = dialectic_score([
        option('A', reversal_cost='expensive'),
        option('B', reversal_cost='cheap'),
    ])

    assert (decided.winner, decided.rung, decided.rung_name) == ('B', 2, 'reversal cost')
    assert decided.rule == 'B is cheap to undo; the others are not'


def test_rung_three_takes_the_option_the_repository_already_does() -> None:
    decided = dialectic_score([option('A'), option('B', conforms=True)])

    assert (decided.winner, decided.rung, decided.rung_name) == ('B', 3, 'conformance')
    assert decided.rule == 'B does what the repository already does'


def test_two_conforming_options_fall_through_to_surface() -> None:
    decided = dialectic_score([
        option('A', conforms=True, surface=4),
        option('B', conforms=True, surface=2),
    ])

    assert (decided.winner, decided.rung, decided.rung_name) == ('B', 4, 'surface')
    assert decided.rule == 'B touches 2, fewer than A at 4'


def test_rung_five_owes_a_spike_instead_of_a_winner() -> None:
    decided = dialectic_score([
        option('A', spike='run the parser over the fixture corpus'),
        option('B'),
    ])

    assert decided.winner is None
    assert (decided.rung, decided.rung_name) == (5, 'spike')
    assert decided.rule == (
        'run the parser over the fixture corpus would separate them; run it and '
        'score again from rung 1'
    )


def test_rung_six_takes_the_option_the_user_listed_first() -> None:
    decided = dialectic_score([option('A'), option('B')])

    assert (decided.winner, decided.rung, decided.rung_name) == ('A', 6, 'coin flip')
    assert decided.rule == 'equivalent by every measure; the option the user listed first'


@pytest.mark.parametrize('count', [0, 1, 4])
def test_a_fork_is_two_or_three_options(count: int) -> None:
    decided = dialectic_score([option(f'option {n}') for n in range(count)])

    assert decided.winner is None
    assert decided.refusals == [
        (
            f'{count} options; a fork has 2 or 3, and a wider one is a design problem '
            'for cross-examine'
        )
    ]


def test_an_unscored_option_is_refused() -> None:
    decided = dialectic_score([
        option('A', worst='Blocker'),
        option('B', reversal_cost='moderate'),
    ])

    assert decided.refusals == [
        "'A' is worst at 'Blocker'; expected Critical, High, Medium, Low, none",
        "'B' reverses 'moderate'; expected cheap, expensive",
    ]


def test_two_options_with_one_name_are_refused() -> None:
    decided = dialectic_score([option('A'), option('A')])

    assert decided.refusals == [
        'two options carry the same name; the record could not name one'
    ]


def test_the_record_carries_the_seven_fixed_lines(ticket_root: Path) -> None:
    written = dialectic_record_write('demo', 'retry-placement', record())

    assert written.refusals == []
    path = ticket_root.joinpath('dialectic-retry-placement.md')
    assert written.path == str(path)
    assert path.read_text(encoding='utf-8').splitlines() == [
        '# Retry in the client or in the consumer',
        '',
        'Options: A: client retry, cheap | B: consumer retry, expensive',
        'Worst found: A: High, src/client.py:88 | B: none',
        'Decided by: rung 1 (found defects)',
        'Decision: B, because the High against A is not against B',
        'Reopen if: the consumer stops owning the idempotency key',
        'Unexamined: the queue redelivery window',
    ]


def test_a_record_over_forty_lines_is_refused(ticket_root: Path) -> None:
    written = dialectic_record_write(
        'demo', 'retry-placement', record(unexamined='\n'.join(['a line'] * 40))
    )

    assert written.path is None
    assert written.refusals == ['the decision record is 47 lines; the cap is 40']
    assert not ticket_root.joinpath('dialectic-retry-placement.md').exists()


def test_a_record_missing_its_decision_is_refused(ticket_root: Path) -> None:
    written = dialectic_record_write('demo', 'retry-placement', record(decision='  '))

    assert written.refusals == ['decision is empty']


def test_a_record_with_no_options_is_refused(ticket_root: Path) -> None:
    written = dialectic_record_write('demo', 'retry-placement', record(options=[]))

    assert written.refusals == ['options is empty; a record names what it chose between']


@pytest.mark.parametrize('fork_slug', ['../evil', 'nested/fork', ''])
def test_a_fork_slug_that_is_not_one_path_segment_is_refused(
    ticket_root: Path, fork_slug: str
) -> None:
    written = dialectic_record_write('demo', fork_slug, record())

    assert written.path is None
    assert written.refusals
