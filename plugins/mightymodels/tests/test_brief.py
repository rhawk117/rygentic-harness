from collections.abc import Callable
from pathlib import Path

import pytest
from mightymcp.brief import (
    AskedStanza,
    DoneHalf,
    asked_half,
    brief_append_done,
    brief_open,
    brief_read,
)

MESSAGE = 'feat(demo): ship the thing [#7]'


def asked(**overrides: object) -> AskedStanza:
    fields: dict[str, object] = {
        'objective': 'Ship the thing',
        'acceptance': ['AC-1: `uv run pytest -q` passes'],
        'verification': '`uv run pytest -q`',
        'files_in_scope': ['src/demo.py'],
        'engineer_tier': 'claude-sonnet-5',
        'uses': ['docs/workflow.md'],
        'do_not': 'touch the lockfile',
    }
    return AskedStanza.model_validate(fields | overrides)


def done(**overrides: object) -> DoneHalf:
    fields: dict[str, object] = {
        'what': 'shipped the thing',
        'commit': 'HEAD',
        'diff_summary': 'one module, one test',
        'commands_run': '`uv run pytest -q`: 400 passed',
    }
    return DoneHalf.model_validate(fields | overrides)


@pytest.fixture
def opened(ticket_root: Path) -> Path:
    assert brief_open('demo', 'task-01', asked(), MESSAGE).refusals == []
    return ticket_root.joinpath('briefs', 'task-01.md')


def test_open_writes_every_stanza_field(opened: Path) -> None:
    lines = opened.read_text(encoding='utf-8').splitlines()

    assert lines == [
        '## ASKED',
        'objective: Ship the thing',
        'acceptance:',
        '  - AC-1: `uv run pytest -q` passes',
        'verification: `uv run pytest -q`',
        'files-in-scope: [src/demo.py]',
        'engineer-tier: claude-sonnet-5',
        'uses: [docs/workflow.md]',
        'do-not: touch the lockfile',
    ]


def test_open_returns_the_engineer_dispatch(ticket_root: Path) -> None:
    dispatch = brief_open('demo', 'task-01', asked(), MESSAGE).dispatch

    assert dispatch.startswith('<objective>Execute the task specified in the ASKED')
    assert '.mightymodels/demo/briefs/task-01.md' in dispatch
    assert '## DONE section there before reporting (≤65 lines).</objective>' in dispatch
    assert '## ASKED\nobjective: Ship the thing' in dispatch
    assert dispatch.endswith(
        f'<constraints>Commit when done with message "{MESSAGE}".</constraints>\n'
    )


def test_open_adds_the_push_clause_only_in_remediation_mode(ticket_root: Path) -> None:
    opened = brief_open('demo', 'task-01', asked(), MESSAGE, push=True)

    assert f'"{MESSAGE}". push after committing.</constraints>' in opened.dispatch


@pytest.mark.parametrize(
    'criterion',
    [
        'AC-1: the parser works correctly',
        'AC-1: it handles errors appropriately',
        'AC-1: the module is consistent with the rest',
    ],
)
def test_open_refuses_a_placeholder_criterion(ticket_root: Path, criterion: str) -> None:
    opened = brief_open('demo', 'task-01', asked(acceptance=[criterion]), MESSAGE)

    assert opened.path is None
    assert 'is a placeholder' in opened.refusals[0]
    assert not ticket_root.joinpath('briefs', 'task-01.md').exists()


def test_open_refuses_an_empty_files_in_scope(ticket_root: Path) -> None:
    opened = brief_open('demo', 'task-01', asked(files_in_scope=[]), MESSAGE)

    assert opened.refusals == [
        'files-in-scope is empty; a task owns the paths it may write'
    ]


def test_open_refuses_an_empty_acceptance_list(ticket_root: Path) -> None:
    opened = brief_open('demo', 'task-01', asked(acceptance=[]), MESSAGE)

    assert opened.refusals[0].startswith('acceptance is empty')


@pytest.mark.parametrize('task_id', ['task-1', 'task-one', 'taskish-01', '../evil'])
def test_open_refuses_a_task_id_that_is_not_task_nn(
    ticket_root: Path, task_id: str
) -> None:
    opened = brief_open('demo', task_id, asked(), MESSAGE)

    assert opened.refusals == [f'task id {task_id!r} is not task-NN']


def test_open_refuses_a_brief_that_already_carries_an_asked_half(opened: Path) -> None:
    before = opened.read_text(encoding='utf-8')

    second = brief_open('demo', 'task-01', asked(objective='something else'), MESSAGE)

    assert second.refusals == [f'{opened} already carries an ASKED half']
    assert opened.read_text(encoding='utf-8') == before


def test_open_refuses_a_stanza_over_eighty_lines(ticket_root: Path) -> None:
    criteria = [f'AC-{number}: `check {number}` exits 0' for number in range(1, 80)]

    opened = brief_open('demo', 'task-01', asked(acceptance=criteria), MESSAGE)

    assert opened.refusals == ['the ASKED stanza is 87 lines; the cap is 80']
    assert not ticket_root.joinpath('briefs', 'task-01.md').exists()


def test_open_refuses_a_ticket_that_does_not_exist(repo: Path) -> None:
    opened = brief_open('demo', 'task-01', asked(), MESSAGE)

    assert opened.refusals[0].startswith('no ticket directory at')


def test_open_refuses_a_slug_that_escapes_the_ticket_directory(repo: Path) -> None:
    opened = brief_open('../evil', 'task-01', asked(), MESSAGE)

    assert opened.path is None
    assert opened.refusals[0].startswith('name')


def test_append_done_adds_the_second_half(
    opened: Path, repo: Path, commit: Callable[[Path, str], str]
) -> None:
    sha = commit(repo, 'one.txt')

    written = brief_append_done('demo', 'task-01', done(commit=sha))

    assert written.refusals == []
    text = opened.read_text(encoding='utf-8')
    assert text.startswith('## ASKED\n')
    assert f'\n## DONE\nwhat: shipped the thing\ncommit: {sha}\n' in text
    assert 'diff-summary: one module, one test\n' in text
    assert text.endswith('commands-run: `uv run pytest -q`: 400 passed\n')


def test_append_done_refuses_a_brief_without_an_asked_half(
    ticket_root: Path, repo: Path, commit: Callable[[Path, str], str]
) -> None:
    sha = commit(repo, 'one.txt')
    path = ticket_root.joinpath('briefs', 'task-02.md')
    path.write_text('notes and nothing else\n', encoding='utf-8')

    written = brief_append_done('demo', 'task-02', done(commit=sha))

    assert written.refusals == [f'{path} has no ASKED half']
    assert path.read_text(encoding='utf-8') == 'notes and nothing else\n'


def test_append_done_refuses_a_second_done_half(
    opened: Path, repo: Path, commit: Callable[[Path, str], str]
) -> None:
    sha = commit(repo, 'one.txt')
    assert brief_append_done('demo', 'task-01', done(commit=sha)).refusals == []
    before = opened.read_text(encoding='utf-8')

    written = brief_append_done('demo', 'task-01', done(commit=sha, what='again'))

    assert written.refusals == [f'{opened} already carries a DONE half']
    assert opened.read_text(encoding='utf-8') == before


def test_append_done_refuses_a_commit_the_repository_does_not_carry(
    opened: Path, repo: Path, commit: Callable[[Path, str], str]
) -> None:
    commit(repo, 'one.txt')

    written = brief_append_done('demo', 'task-01', done(commit='0' * 40))

    assert written.refusals == [f'commit {"0" * 40!r} is not a commit in this repository']
    assert '## DONE' not in opened.read_text(encoding='utf-8')


def test_append_done_refuses_a_done_half_over_sixty_five_lines(
    opened: Path, repo: Path, commit: Callable[[Path, str], str]
) -> None:
    sha = commit(repo, 'one.txt')
    long_run = '\n'.join(f'line {number}' for number in range(70))

    written = brief_append_done(
        'demo', 'task-01', done(commit=sha, commands_run=long_run)
    )

    assert written.refusals[0] == 'the DONE half is 74 lines; the cap is 65'


def test_append_done_refuses_a_brief_over_eighty_lines(
    ticket_root: Path, repo: Path, commit: Callable[[Path, str], str]
) -> None:
    sha = commit(repo, 'one.txt')
    criteria = [f'AC-{number}: `check {number}` exits 0' for number in range(1, 21)]
    assert (
        brief_open('demo', 'task-02', asked(acceptance=criteria), MESSAGE).refusals == []
    )
    long_run = '\n'.join(f'line {number}' for number in range(61))

    written = brief_append_done(
        'demo', 'task-02', done(commit=sha, commands_run=long_run)
    )

    assert written.refusals == ['the brief is 94 lines; the cap is 80']
    brief = ticket_root.joinpath('briefs', 'task-02.md')
    assert '## DONE' not in brief.read_text(encoding='utf-8')


def test_read_returns_both_halves(
    opened: Path, repo: Path, commit: Callable[[Path, str], str]
) -> None:
    sha = commit(repo, 'one.txt')
    brief_append_done('demo', 'task-01', done(commit=sha))

    read = brief_read('demo', 'task-01')

    assert read.refusals == []
    assert read.asked is not None
    assert read.asked.objective == 'Ship the thing'
    assert read.asked.acceptance == ['AC-1: `uv run pytest -q` passes']
    assert read.asked.files_in_scope == ['src/demo.py']
    assert read.asked.do_not == 'touch the lockfile'
    assert read.done is not None
    assert read.done.commit == sha
    assert read.done.commands_run == '`uv run pytest -q`: 400 passed'


def test_read_reports_the_verified_section(opened: Path) -> None:
    assert not brief_read('demo', 'task-01').verified

    with opened.open('a', encoding='utf-8') as handle:
        handle.write('\n## VERIFIED\nscout: every AC matches ASKED\n')

    read = brief_read('demo', 'task-01')
    assert read.verified
    assert read.done is None


def test_read_refuses_a_brief_that_is_not_there(ticket_root: Path) -> None:
    read = brief_read('demo', 'task-09')

    assert read.asked is None
    assert read.refusals == [
        f'no brief at {ticket_root.joinpath("briefs", "task-09.md")}'
    ]


def test_asked_half_returns_the_stanza_without_the_done_half(opened: Path) -> None:
    text = opened.read_text(encoding='utf-8') + '\n## DONE\nwhat: shipped it\n'

    half = asked_half(text)

    assert 'objective: Ship the thing' in half
    assert 'what: shipped it' not in half


def test_asked_half_of_a_brief_without_one_is_empty() -> None:
    assert asked_half('# notes\nnothing here\n') == ''
