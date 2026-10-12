"""The PreToolUse hook on Agent denies a worker's dispatch outside the row its agent file states."""

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from mightymodels_plugin.cli import main
from mightymodels_plugin.commands.dispatch_hook import (
    DISPATCH_RULES,
    agent_type,
    check_dispatch,
)
from mightymodels_plugin.core.routing import ROUTING, Worker

AGENTS = Path(__file__).parent.parent.joinpath('agents')
ROW_LINE = re.compile(r'^- (?:Delegate|Dispatch) only (?:to )?(?P<names>[^.]*)\.', re.MULTILINE)
BACKTICKED = re.compile(r'`([\w-]+)`')
PREFIX = 'mightymodels:'
ENGINEER = 'mightymodels:workers:engineer'
ARCHITECT = 'mightymodels:workers:architect'
MERGE_VADER = 'mightymodels:review:merge-vader'
UNCLE_BOB = 'mightymodels:review:uncle-bob'
CODE_SCOUT = 'mightymodels:triage:code-scout'
WEB_SCOUT = 'mightymodels:triage:web-scout'
EMPTY_ROW = (
    Worker.CODE_SCOUT,
    Worker.WEB_SCOUT,
    Worker.QUALITYLENS,
    Worker.INTERN,
    Worker.GITTY_UP,
    Worker.WINGMAN,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Verdict:
    decision: str | None
    reason: str


def hook_input(caller: str | None, target: str | None) -> str:
    fields: dict[str, object] = {'tool_name': 'Agent', 'tool_input': {'subagent_type': target}}
    if caller is not None:
        fields['agent_type'] = caller
    return json.dumps(fields)


def run_hook(text: str) -> Verdict:
    stdout = io.BytesIO()
    assert check_dispatch(io.StringIO(text), stdout) == 0
    printed = stdout.getvalue()
    if not printed:
        return Verdict(decision=None, reason='')
    output = json.loads(printed)['hookSpecificOutput']
    assert output['hookEventName'] == 'PreToolUse'
    return Verdict(decision=output['permissionDecision'], reason=output['permissionDecisionReason'])


def row_stated_by(worker: Worker) -> frozenset[str]:
    body = next(AGENTS.glob(f'*/{worker}.md')).read_text(encoding='utf-8')
    found = ROW_LINE.search(body)
    return frozenset(BACKTICKED.findall(found['names'])) if found else frozenset()


class TestWorkerRow:
    @pytest.mark.parametrize(
        ('caller', 'target'),
        [
            pytest.param(ENGINEER, 'code-scout', id='engineer-to-code-scout'),
            pytest.param(ARCHITECT, 'code-scout', id='architect-to-code-scout'),
            pytest.param(MERGE_VADER, 'web-scout', id='merge-vader-to-web-scout'),
            pytest.param(MERGE_VADER, 'qualitylens', id='merge-vader-to-qualitylens'),
            pytest.param(UNCLE_BOB, 'qualitylens', id='uncle-bob-to-qualitylens'),
        ],
    )
    def test_a_target_inside_the_row_is_allowed(self, caller: str, target: str) -> None:
        assert run_hook(hook_input(caller, target)) == Verdict(decision=None, reason='')

    @pytest.mark.parametrize(
        ('caller', 'target', 'may_dispatch'),
        [
            pytest.param(ENGINEER, 'web-scout', 'code-scout', id='engineer-to-web-scout'),
            pytest.param(ENGINEER, 'engineer', 'code-scout', id='engineer-to-engineer'),
            pytest.param(ARCHITECT, 'engineer', 'code-scout', id='architect-to-engineer'),
            pytest.param(
                UNCLE_BOB,
                'web-scout',
                'code-scout, qualitylens',
                id='uncle-bob-to-web-scout',
            ),
            pytest.param(
                MERGE_VADER,
                'architect',
                'code-scout, qualitylens, web-scout',
                id='merge-vader-to-architect',
            ),
            pytest.param(ENGINEER, 'general-purpose', 'code-scout', id='built-in-target'),
            pytest.param(ENGINEER, 'other:code-scout', 'code-scout', id='other-plugin-target'),
        ],
    )
    def test_a_target_outside_the_row_is_denied_with_the_row_named(
        self, caller: str, target: str, may_dispatch: str
    ) -> None:
        verdict = run_hook(hook_input(caller, target))

        assert verdict.decision == 'deny'
        assert verdict.reason == (
            f'{caller} may not dispatch {target}; it may dispatch: {may_dispatch}'
        )

    @pytest.mark.parametrize('caller', EMPTY_ROW)
    @pytest.mark.parametrize('target', [*Worker, 'general-purpose'])
    def test_a_worker_with_an_empty_row_is_denied_every_target(
        self, caller: Worker, target: str
    ) -> None:
        verdict = run_hook(hook_input(agent_type(caller), target))

        assert verdict.decision == 'deny'
        assert verdict.reason.endswith('it may dispatch: nothing')


class TestNames:
    NO_WORKER = (
        pytest.param(f'{PREFIX}stranger', id='unknown-name'),
        pytest.param(f'{PREFIX}engineer', id='flat-engineer'),
        pytest.param(f'{PREFIX}code-scout', id='flat-code-scout'),
        pytest.param(f'{PREFIX}triage:engineer', id='engineer-in-another-folder'),
        pytest.param(f'{PREFIX}workers:code-scout', id='code-scout-in-another-folder'),
        pytest.param(f'{PREFIX}intern', id='flat-intern'),
        pytest.param(f'{PREFIX}triage:intern', id='intern-in-another-folder'),
        pytest.param(f'{PREFIX}triage:stranger', id='unknown-name-in-a-folder'),
        pytest.param(f'{CODE_SCOUT}:extra', id='a-segment-after-the-name'),
        pytest.param(f'{PREFIX}{CODE_SCOUT}', id='the-prefix-twice'),
    )

    @pytest.mark.parametrize(
        'target',
        [
            pytest.param('code-scout', id='bare-target'),
            pytest.param(CODE_SCOUT, id='prefixed-target'),
        ],
    )
    def test_a_prefix_changes_nothing_for_an_allowed_dispatch(self, target: str) -> None:
        assert run_hook(hook_input(ENGINEER, target)).decision is None

    @pytest.mark.parametrize(
        'target',
        [
            pytest.param('web-scout', id='bare-target'),
            pytest.param(WEB_SCOUT, id='prefixed-target'),
        ],
    )
    def test_a_prefix_changes_nothing_for_a_denied_dispatch(self, target: str) -> None:
        assert run_hook(hook_input(ENGINEER, target)).decision == 'deny'

    @pytest.mark.parametrize('target', ['code-scout', 'general-purpose', ENGINEER, CODE_SCOUT])
    @pytest.mark.parametrize('caller', NO_WORKER)
    def test_a_prefixed_name_that_is_no_worker_is_denied_every_target(
        self, caller: str, target: str
    ) -> None:
        assert run_hook(hook_input(caller, target)) == Verdict(
            decision='deny',
            reason=f'{caller} may not dispatch {target}; it may dispatch: nothing',
        )

    @pytest.mark.parametrize('target', NO_WORKER)
    def test_a_prefixed_target_that_is_no_worker_is_denied_with_the_row_named(
        self, target: str
    ) -> None:
        assert run_hook(hook_input(ENGINEER, target)) == Verdict(
            decision='deny',
            reason=f'{ENGINEER} may not dispatch {target}; it may dispatch: code-scout',
        )

    @pytest.mark.parametrize('target', ['code-scout', 'web-scout', 'general-purpose', 'engineer'])
    @pytest.mark.parametrize(
        'caller',
        [
            pytest.param('general-purpose', id='built-in'),
            pytest.param('engineer', id='bare-worker-name'),
            pytest.param('other:engineer', id='another-plugins-agent'),
            pytest.param(f'other{ENGINEER}', id='prefix-not-at-the-start'),
            pytest.param('', id='empty'),
        ],
    )
    def test_a_caller_outside_the_plugin_gets_no_decision(self, caller: str, target: str) -> None:
        assert run_hook(hook_input(caller, target)) == Verdict(decision=None, reason='')


class TestMainConversation:
    @pytest.mark.parametrize('target', ['code-scout', 'engineer', 'general-purpose'])
    def test_input_with_no_agent_type_gets_no_decision(self, target: str) -> None:
        assert run_hook(hook_input(None, target)) == Verdict(decision=None, reason='')


class TestUnexpectedInput:
    @pytest.mark.parametrize(
        'text',
        [
            pytest.param(
                '{"agent_type": "mightymodels:workers:engineer"', id='truncated-json-spaced'
            ),
            pytest.param(
                '{"agent_type":"mightymodels:workers:engineer"', id='truncated-json-compact'
            ),
            pytest.param(
                '{"agent_type" : "mightymodels:workers:engineer"', id='truncated-json-padded'
            ),
            pytest.param('{"agent_type": "mightymodels:workers:engineer"}', id='no-tool-input'),
            pytest.param(
                '{"agent_type": "mightymodels:workers:engineer", "tool_input": []}',
                id='tool-input-a-list',
            ),
            pytest.param(
                '{"agent_type": "mightymodels:workers:engineer", '
                '"tool_input": {"subagent_type": 3}}',
                id='target-a-number',
            ),
        ],
    )
    def test_input_naming_a_plugin_worker_is_denied(self, text: str) -> None:
        assert run_hook(text).decision == 'deny'

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param('', id='empty'),
            pytest.param('not json', id='text'),
            pytest.param('{"tool_name": "Agent"', id='truncated-json'),
            pytest.param('[]', id='list'),
            pytest.param('{"tool_name": "Agent"}', id='object-without-a-caller'),
            pytest.param('{"agent_type": "engineer"', id='truncated-bare-caller'),
            pytest.param('{"agent_type": "other:engineer"', id='truncated-other-plugin'),
            pytest.param(
                '{"tool_input": {"subagent_type": "mightymodels:workers:engineer"',
                id='truncated-prefix-only-in-target',
            ),
            pytest.param('{"agent_type": 7, "tool_input": {}}', id='caller-a-number'),
            pytest.param('{"agent_type": null}', id='caller-null'),
        ],
    )
    def test_input_naming_no_plugin_worker_gets_no_decision(self, text: str) -> None:
        assert run_hook(text) == Verdict(decision=None, reason='')


class TestInputTheCodecRefuses:
    VALUES = (
        pytest.param('NaN', id='nan'),
        pytest.param('Infinity', id='infinity'),
        pytest.param('1e400', id='number-out-of-range'),
        pytest.param('"\\ud800"', id='escaped-lone-surrogate'),
        pytest.param('"\ud800"', id='raw-lone-surrogate'),
    )
    UNREADABLE = Verdict(
        decision='deny', reason='a dispatch was refused: the hook input is not the expected JSON'
    )

    def verdict_on(self, caller: str | None, value: str) -> Verdict:
        allowed = hook_input(caller, 'code-scout')
        return run_hook(f'{allowed.removesuffix("}")}, "elapsed": {value}}}')

    @pytest.mark.parametrize('value', VALUES)
    def test_a_plugin_workers_allowed_dispatch_holding_it_is_denied_as_unreadable(
        self, value: str
    ) -> None:
        assert self.verdict_on(ENGINEER, value) == self.UNREADABLE

    @pytest.mark.parametrize('value', VALUES)
    @pytest.mark.parametrize(
        'caller',
        [
            pytest.param(None, id='main-conversation'),
            pytest.param('general-purpose', id='built-in'),
        ],
    )
    def test_with_no_plugin_caller_input_holding_it_gets_no_decision(
        self, caller: str | None, value: str
    ) -> None:
        assert self.verdict_on(caller, value) == Verdict(decision=None, reason='')


class TestWrittenBytes:
    TARGET = 'café'
    DENIAL = (
        b'{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",'
        b'"permissionDecisionReason":"mightymodels:workers:engineer may not dispatch '
        b'caf\xc3\xa9; it may dispatch: code-scout"}}\n'
    )

    @pytest.fixture
    def written(self) -> bytes:
        output = io.BytesIO()
        check_dispatch(io.StringIO(hook_input(ENGINEER, self.TARGET)), output)
        return output.getvalue()

    def test_a_denial_is_one_compact_line_with_a_character_outside_ascii_as_utf8(
        self, written: bytes
    ) -> None:
        assert written == self.DENIAL


class TestCommand:
    def test_the_subcommand_prints_the_deny_decision(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr('sys.stdin', io.StringIO(hook_input(ENGINEER, 'architect')))

        assert main(['dispatch-hook']) == 0
        assert json.loads(capsys.readouterr().out)['hookSpecificOutput'] == {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': (
                f'{ENGINEER} may not dispatch architect; it may dispatch: code-scout'
            ),
        }


class TestAgentFiles:
    @pytest.mark.parametrize('worker', Worker)
    def test_the_row_equals_the_one_the_agent_file_states(self, worker: Worker) -> None:
        assert frozenset(DISPATCH_RULES[worker]) == row_stated_by(worker)

    def test_every_worker_has_a_row(self) -> None:
        assert set(DISPATCH_RULES) == set(Worker)


class TestReviewerTypes:
    REVIEWERS = frozenset({MERGE_VADER, UNCLE_BOB})

    @pytest.mark.parametrize(
        'workers',
        [
            pytest.param(frozenset(ROUTING), id='routing-table'),
            pytest.param(
                frozenset(DISPATCH_RULES).union(*DISPATCH_RULES.values()), id='dispatch-rules'
            ),
        ],
    )
    def test_names_the_two_reviewers_and_no_type_ending_in_reviewer(
        self, workers: frozenset[Worker]
    ) -> None:
        types = set(map(agent_type, workers))

        assert types >= self.REVIEWERS
        assert [name for name in types if name.endswith('-reviewer')] == []
