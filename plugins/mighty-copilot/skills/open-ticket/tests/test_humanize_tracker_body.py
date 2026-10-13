"""Behavioral tests for scripts/humanize_tracker_body.py via its entry point."""

from __future__ import annotations

import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'humanize_tracker_body.py'
ASSET = Path(__file__).resolve().parents[1] / 'assets' / 'tracker-body.md'
CLEAN, ISSUES, REJECTED = 0, 1, 2
EM_DASH = '\u2014'
EN_DASH = '\u2013'
GOOD = """## Summary

The retry queue drains slowly after the nightly compaction.

## Findings

- the drain loop sleeps between batches [src/queue.py:41]

## Acceptance

- [ ] `pytest tests/test_queue.py` passes
"""


@dataclass(frozen=True, slots=True)
class Outcome:
    code: int
    out: str
    body: str


@dataclass(frozen=True, slots=True)
class Runner:
    body: Path
    capsys: pytest.CaptureFixture[str]
    main: Callable[[list[str]], int]

    def run(self, command: str, text: str, *extra: str) -> Outcome:
        self.body.write_text(text, encoding='utf-8')
        code = self.main([command, str(self.body), *extra])
        out = self.capsys.readouterr().out
        return Outcome(code=code, out=out, body=self.body.read_text(encoding='utf-8'))


@pytest.fixture
def runner(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Runner:
    main = runpy.run_path(str(SCRIPT))['main']
    return Runner(body=tmp_path / 'body.md', capsys=capsys, main=main)


def test_a_clean_body_passes(runner: Runner) -> None:
    outcome = runner.run('check', GOOD)
    assert (outcome.code, outcome.out.strip()) == (CLEAN, f'{runner.body}: clean')


def test_the_unfilled_asset_is_all_placeholders(runner: Runner) -> None:
    outcome = runner.run('check', ASSET.read_text(encoding='utf-8'))
    assert outcome.code == ISSUES
    assert 'placeholder' in outcome.out


@pytest.mark.parametrize(
    ('text', 'rule'),
    [
        (GOOD.replace('## Acceptance', '## Done when'), 'missing-section'),
        (GOOD.replace('slowly', 'slowly, a testament to debt'), 'tell-word'),
        (GOOD.replace(' [src/queue.py:41]', ''), 'uncited-finding'),
        (GOOD.replace('## Summary', '## Acceptance\n\n## Summary', 1), 'section-order'),
    ],
)
def test_problems_are_reported_by_rule(runner: Runner, text: str, rule: str) -> None:
    outcome = runner.run('check', text)
    assert outcome.code == ISSUES
    assert f': {rule}: ' in outcome.out


def test_check_never_edits_the_body(runner: Runner) -> None:
    text = GOOD.replace('slowly after', f'slowly {EM_DASH} after')
    outcome = runner.run('check', text)
    assert outcome.body == text


def test_fix_repairs_dashes_and_filler_openers(runner: Runner) -> None:
    text = GOOD.replace(
        'The retry queue drains slowly after the nightly compaction.',
        f'Furthermore, the queue drains slowly {EM_DASH} after 2am. Retries 1{EN_DASH}3 fail.',
    )
    outcome = runner.run('fix', text)
    assert outcome.code == CLEAN
    assert 'The queue drains slowly, after 2am. Retries 1-3 fail.' in outcome.body


def test_fix_leaves_code_untouched(runner: Runner) -> None:
    command = f'`echo a {EM_DASH} b`'
    fence = f'```\nMoreover, x {EM_DASH} y\n```\n'
    text = GOOD.replace('`pytest tests/test_queue.py`', command) + fence
    outcome = runner.run('fix', text)
    assert command in outcome.body
    assert f'Moreover, x {EM_DASH} y' in outcome.body


def test_fix_reports_what_still_needs_rewording(runner: Runner) -> None:
    outcome = runner.run('fix', GOOD.replace('slowly', 'slowly; we must leverage caching'))
    assert outcome.code == ISSUES
    assert '0 lines fixed, 1 issues remain' in outcome.out


def test_a_missing_body_is_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main = runpy.run_path(str(SCRIPT))['main']
    code = main(['check', str(tmp_path / 'absent.md')])
    assert code == REJECTED
    assert 'does not exist' in capsys.readouterr().err


def test_comment_shape_skips_structure_but_keeps_prose_rules(runner: Runner) -> None:
    comment = 'Review found MV-1 and UB-2. Moreover, the fix is small.\n'
    checked = runner.run('check', comment, '--shape', 'comment')
    fixed = runner.run('fix', comment, '--shape', 'comment')
    assert ': missing-section: ' not in checked.out
    assert ': filler-opener: ' in checked.out
    assert (fixed.code, fixed.body) == (
        CLEAN,
        'Review found MV-1 and UB-2. The fix is small.\n',
    )
