from collections.abc import Callable
from pathlib import Path

from mightymcp.handoff import (
    HandoffFields,
    decision_record,
    handoff_prompt,
    handoff_write,
)
from mightymcp.routing import Scope
from mightymcp.ticket import CompanionDocs, HandoffContext, ticket_create

SUMMARY = 'Ship the brief tools'
CONTEXT = ['the api is sync', 'retries are capped at three', 'the fixture is shared']
SKELETON = (
    '# Handoff for demo\n'
    '\n'
    '<important>YOU MUST invoke `using-mightymodels`</important>\n'
    '\n'
    '## Handoff Content\n'
    '\n'
    '<!-- The next session reads these first, so they must be correct. -->\n'
)
BATON_PARTS = [
    'Focus:',
    'State:',
    '## Settled this session',
    '## Do not retry',
    '## Works',
    '## Gotchas',
    '## Parked',
]


def make_ticket(
    repo: Path, scope: Scope = 'med', docs: CompanionDocs | None = None
) -> Path:
    written = ticket_create(
        'demo',
        SUMMARY,
        CONTEXT,
        HandoffContext(scope=scope, plan_first=False, branch_name='feat/demo'),
        docs or CompanionDocs(issue_number=7, jira_key='PROJ-1'),
    )
    assert written.refusals == []
    return repo.joinpath('.mightymodels', 'demo')


def baton(**overrides: object) -> HandoffFields:
    fields: dict[str, object] = {
        'focus': 'finish task-01',
        'settled': ['one ledger per ticket (user)'],
        'do_not_retry': ['a yaml stanza parser | failed because: colons in values'],
        'works': ['`uv run pytest -q` | for: the whole suite'],
        'gotchas': ['the ignore ritual is idempotent | so: run it every time'],
        'parked': [
            'the archive format | why parked: not this sprint | revisit when: prune'
        ],
    }
    return HandoffFields.model_validate(fields | overrides)


def test_the_sprint_handoff_is_the_skeleton_and_pointers(repo: Path) -> None:
    directory = make_ticket(repo)

    written = handoff_write('demo', 'sprint')

    assert written.refusals == []
    assert written.path == str(directory.joinpath('handoffs', 'SPRINT.md'))
    assert directory.joinpath('handoffs', 'SPRINT.md').read_text(encoding='utf-8') == (
        f'{SKELETON}'
        '\n'
        '- Read `.mightymodels/demo/ticket.yml` first.\n'
        '- Read GitHub issue #7.\n'
        '- Read Jira PROJ-1.\n'
        '- Invoke the `game-plan` skill and stop at its gate.\n'
    )


def test_the_sprint_handoff_names_the_ramp_the_routing_table_picks(repo: Path) -> None:
    directory = make_ticket(repo, 'sm')

    handoff_write('demo', 'sprint')

    text = directory.joinpath('handoffs', 'SPRINT.md').read_text(encoding='utf-8')
    assert '- Invoke the `yolo` skill and stop at its gate.\n' in text


def test_the_review_handoff_points_at_the_pr_and_names_review_circus(
    repo: Path,
) -> None:
    directory = make_ticket(repo, docs=CompanionDocs(issue_number=7, pr_number=12))

    written = handoff_write('demo', 'review')

    assert written.refusals == []
    assert directory.joinpath('handoffs', 'REVIEW.md').read_text(encoding='utf-8') == (
        f'{SKELETON}'
        '\n'
        '- Read `.mightymodels/demo/ticket.yml` first.\n'
        '- Read GitHub issue #7.\n'
        '- Read PR #12.\n'
        '- Invoke `review-circus`.\n'
        '- The reviewer models come from ticket.yml `subagent-models`.\n'
    )


def test_neither_pointer_handoff_carries_a_ticket_fact(repo: Path) -> None:
    directory = make_ticket(repo, docs=CompanionDocs(issue_number=7, pr_number=12))

    handoff_write('demo', 'sprint')
    handoff_write('demo', 'review')

    for name in ('SPRINT.md', 'REVIEW.md'):
        text = directory.joinpath('handoffs', name).read_text(encoding='utf-8')
        assert SUMMARY not in text
        assert not any(line in text for line in CONTEXT)


def test_an_unknown_handoff_kind_is_refused(repo: Path) -> None:
    make_ticket(repo)

    written = handoff_write('demo', 'postcard')

    assert written.path is None
    assert written.refusals == ["unknown kind 'postcard'; expected sprint, review, baton"]


def test_the_baton_carries_its_seven_parts(
    repo: Path, commit: Callable[[Path, str], str]
) -> None:
    directory = make_ticket(repo)
    commit(repo, 'one.txt')

    written = handoff_write('demo', 'baton', baton())

    assert written.refusals == []
    text = directory.joinpath('handoffs', 'BATON.md').read_text(encoding='utf-8')
    assert text.startswith('# Baton for demo\n\nFocus: finish task-01\n')
    assert all(part in text for part in BATON_PARTS)
    assert '- `uv run pytest -q` | for: the whole suite\n' in text


def test_the_baton_reads_its_state_from_git_and_the_briefs(
    repo: Path, commit: Callable[[Path, str], str]
) -> None:
    directory = make_ticket(repo)
    sha = commit(repo, 'one.txt')
    directory.joinpath('briefs', 'task-01.md').write_text(
        '## ASKED\nobjective: one\n\n## DONE\nwhat: done\n', encoding='utf-8'
    )
    directory.joinpath('briefs', 'task-02.md').write_text(
        '## ASKED\nobjective: two\n', encoding='utf-8'
    )

    handoff_write('demo', 'baton', baton())

    text = directory.joinpath('handoffs', 'BATON.md').read_text(encoding='utf-8')
    assert (
        f'State: branch main at {sha[:7]}; in flight: task-02 '
        '(.mightymodels/demo/briefs/task-02.md), DONE half absent; tree clean\n'
    ) in text


def test_the_baton_says_none_when_no_task_is_in_flight(
    repo: Path, commit: Callable[[Path, str], str]
) -> None:
    directory = make_ticket(repo)
    commit(repo, 'one.txt')

    handoff_write('demo', 'baton', baton())

    text = directory.joinpath('handoffs', 'BATON.md').read_text(encoding='utf-8')
    assert 'in flight: none;' in text


def test_the_baton_refuses_an_empty_focus(repo: Path) -> None:
    directory = make_ticket(repo)

    written = handoff_write('demo', 'baton', baton(focus=''))

    assert written.refusals == ['focus is empty']
    assert not directory.joinpath('handoffs', 'BATON.md').exists()


def test_the_baton_refuses_over_forty_lines(repo: Path) -> None:
    directory = make_ticket(repo)
    works = [f'`check {number}` | for: line {number}' for number in range(30)]

    written = handoff_write('demo', 'baton', baton(works=works))

    assert written.refusals == ['BATON.md is 48 lines; the cap is 40']
    assert not directory.joinpath('handoffs', 'BATON.md').exists()


def test_the_prompt_prefers_the_baton_and_carries_its_focus(
    repo: Path, commit: Callable[[Path, str], str]
) -> None:
    directory = make_ticket(repo)
    commit(repo, 'one.txt')
    directory.joinpath('briefs', 'task-01.md').write_text(
        '## ASKED\nobjective: one\n', encoding='utf-8'
    )
    handoff_write('demo', 'sprint')
    handoff_write('demo', 'baton', baton())

    built = handoff_prompt('demo')

    assert built.refusals == []
    assert built.kind == 'baton'
    assert built.path == str(directory.joinpath('handoffs', 'BATON.md'))
    assert built.prompt == (
        'Read `.mightymodels/demo/ticket.yml`, then '
        '`.mightymodels/demo/handoffs/BATON.md`, and invoke `using-mightymodels` '
        'before anything else. The checklist is GitHub issue #7. '
        'The tracker item is Jira PROJ-1. '
        'The focus is "finish task-01"; invoke `agents-assemble` for it.'
    )


def test_the_prompt_for_a_fresh_ticket_names_the_ramp(repo: Path) -> None:
    make_ticket(repo, 'sm')
    handoff_write('demo', 'sprint')

    built = handoff_prompt('demo')

    assert built.kind == 'sprint'
    assert built.prompt.endswith('Invoke the `yolo` skill and stop at its gate.')
    assert '\n' not in built.prompt


def test_the_prompt_for_a_review_handoff_names_review_circus(repo: Path) -> None:
    make_ticket(repo)
    handoff_write('demo', 'review')

    built = handoff_prompt('demo')

    assert built.kind == 'review'
    assert built.prompt.endswith('Invoke `review-circus`.')


def test_the_prompt_is_refused_before_any_handoff_is_written(repo: Path) -> None:
    directory = make_ticket(repo)

    built = handoff_prompt('demo')

    assert built.prompt == ''
    assert built.refusals == [f'no handoff in {directory.joinpath("handoffs")}']


def test_decisions_are_appended_with_an_incrementing_number(repo: Path) -> None:
    directory = make_ticket(repo)

    first = decision_record(
        'demo', 'where the ledger lives', ['ticket', 'brief'], 'ticket', 'user'
    )
    second = decision_record('demo', 'the cap', ['20', '40'], '40', 'dialectic rung 2')

    assert (first.number, second.number) == (1, 2)
    assert directory.joinpath('decisions.md').read_text(encoding='utf-8') == (
        '- D1: where the ledger lives | options: ticket, brief | chose: ticket (user)\n'
        '- D2: the cap | options: 20, 40 | chose: 40 (dialectic rung 2)\n'
    )


def test_a_decision_without_options_is_refused(repo: Path) -> None:
    directory = make_ticket(repo)

    written = decision_record('demo', 'the cap', [], '40', 'user')

    assert written.refusals == [
        'options is empty; a decision records what it chose between'
    ]
    assert not directory.joinpath('decisions.md').exists()


def test_the_decision_ledger_refuses_to_pass_forty_lines(repo: Path) -> None:
    directory = make_ticket(repo)
    lines = [
        f'- D{number}: old | options: a, b | chose: a (user)' for number in range(1, 41)
    ]
    directory.joinpath('decisions.md').write_text(
        '\n'.join(lines) + '\n', encoding='utf-8'
    )

    written = decision_record('demo', 'one more', ['a', 'b'], 'a', 'user')

    assert written.refusals == ['decisions.md is 40 lines; the cap is 40']
    assert (
        len(directory.joinpath('decisions.md').read_text(encoding='utf-8').splitlines())
        == 40
    )
