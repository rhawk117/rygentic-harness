"""The PreToolUse hook on Agent denies a worker's dispatch outside the row its agent file states,
and a dispatch of the intern unless every task started for it owns exactly one file. The tickets
on the branch are none here; `test_main_thread_dispatch.py` has the rule that reads them."""

import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from mightymodels.cli import main
from mightymodels.commands.dispatch_hook import (
    DISPATCH_RULES,
    BranchTickets,
    BranchTicketsOrUnreadable,
    StartedOrUnreadable,
    StartedTask,
    StartedTasks,
    agent_type,
    check_dispatch,
)
from mightymodels.core.errors import StateError
from mightymodels.core.routing import ROUTING, Worker

AGENTS = Path(__file__).parent.parent.joinpath('agents')
ROW_LINE = re.compile(r'^- (?:Delegate|Dispatch) only (?:to )?(?P<names>[^.]*)\.', re.MULTILINE)
BACKTICKED = re.compile(r'`([\w-]+)`')
PREFIX = 'mightymodels:'
ENGINEER = 'mightymodels:workers:engineer'
ARCHITECT = 'mightymodels:workers:architect'
INTERN = 'mightymodels:workers:intern'
MERGE_VADER = 'mightymodels:review:merge-vader'
UNCLE_BOB = 'mightymodels:review:uncle-bob'
CODE_SCOUT = 'mightymodels:triage:code-scout'
WEB_SCOUT = 'mightymodels:triage:web-scout'
IMPLEMENTERS = (Worker.ENGINEER, Worker.ARCHITECT, Worker.INTERN)
EMPTY_ROW = (
    Worker.CODE_SCOUT,
    Worker.WEB_SCOUT,
    Worker.QUALITYLENS,
    Worker.FACT_CHECKER,
    Worker.INTERN,
    Worker.GITTY_UP,
    Worker.WINGMAN,
    Worker.TERRY_TOOLCHAIN,
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


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeStartedTasks:
    answer: StartedOrUnreadable = ()
    asked: list[Worker | None] = field(default_factory=list)

    def started_by(self, worker: Worker) -> StartedOrUnreadable:
        self.asked.append(worker)
        return self.answer

    def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        self.asked.append(None)
        return BranchTickets()


def run_hook(text: str, started: StartedTasks | None = None) -> Verdict:
    stdout = io.BytesIO()
    started = FakeStartedTasks() if started is None else started
    assert check_dispatch(io.StringIO(text), stdout, started) == 0
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


class TestInternDispatch:
    ONE_FILE = StartedTask(id='T1', owned=('src/queue.py',))
    TWO_FILES = StartedTask(id='T2', owned=('src/queue.py', 'src/drain.py'))
    NO_FILE = StartedTask(id='T3', owned=())
    ANOTHER_ONE_FILE = StartedTask(id='T4', owned=('src/drain.py',))
    NO_DATA_DIRECTORY = StateError('CLAUDE_PLUGIN_DATA is not set')
    NOT_TINY = (
        pytest.param(
            (),
            'no task is started for the intern on the ticket whose branch is checked out',
            id='no-task-started',
        ),
        pytest.param((TWO_FILES,), 'T2 owns 2 files', id='two-files'),
        pytest.param((NO_FILE,), 'T3 owns 0 files', id='no-file'),
        pytest.param((ONE_FILE, TWO_FILES), 'T2 owns 2 files', id='one-task-of-two-not-tiny'),
        pytest.param(
            (TWO_FILES, NO_FILE), 'T2 owns 2 files; T3 owns 0 files', id='two-tasks-not-tiny'
        ),
        pytest.param(
            NO_DATA_DIRECTORY,
            'the started task could not be read (CLAUDE_PLUGIN_DATA is not set)',
            id='state-unreadable',
        ),
    )
    TINY = (
        pytest.param((ONE_FILE,), id='one-file'),
        pytest.param((ONE_FILE, ANOTHER_ONE_FILE), id='two-tasks-of-one-file'),
    )
    OUTSIDE_CALLERS = (
        pytest.param(None, id='main-conversation'),
        pytest.param('general-purpose', id='built-in'),
        pytest.param('other:engineer', id='another-plugins-agent'),
    )
    OTHER_TARGETS = (
        *(agent_type(worker) for worker in Worker if worker not in {*IMPLEMENTERS, Worker.WINGMAN}),
        'general-purpose',
        f'{PREFIX}intern',
        f'{INTERN}:extra',
    )

    @pytest.mark.parametrize(('started', 'why'), NOT_TINY)
    @pytest.mark.parametrize('caller', OUTSIDE_CALLERS)
    def test_it_is_refused_saying_why_and_naming_the_engineer(
        self, caller: str | None, started: StartedOrUnreadable, why: str
    ) -> None:
        verdict = run_hook(hook_input(caller, INTERN), FakeStartedTasks(answer=started))

        assert verdict == Verdict(
            decision='deny',
            reason=(
                f'{INTERN} was refused: {why}. The intern takes only a tiny task, one that '
                f'owns exactly one file; dispatch {ENGINEER} instead.'
            ),
        )

    @pytest.mark.parametrize('started', TINY)
    @pytest.mark.parametrize('caller', OUTSIDE_CALLERS)
    def test_it_is_allowed_when_every_started_task_owns_exactly_one_file(
        self, caller: str | None, started: StartedOrUnreadable
    ) -> None:
        verdict = run_hook(hook_input(caller, INTERN), FakeStartedTasks(answer=started))

        assert verdict == Verdict(decision=None, reason='')

    def test_the_started_tasks_it_asks_for_are_the_interns(self) -> None:
        started = FakeStartedTasks(answer=(self.ONE_FILE,))

        run_hook(hook_input(None, INTERN), started)

        assert started.asked == [Worker.INTERN]

    @pytest.mark.parametrize(
        'started', [*TINY, *(pytest.param(*case.values[:1], id=case.id) for case in NOT_TINY)]
    )
    def test_an_engineer_dispatch_never_asks_for_what_the_intern_started(
        self, started: StartedOrUnreadable
    ) -> None:
        tasks = FakeStartedTasks(answer=started)

        assert run_hook(hook_input(None, ENGINEER), tasks) == Verdict(decision=None, reason='')
        assert Worker.INTERN not in tasks.asked

    def test_a_bare_target_is_held_as_the_typed_one_is(self) -> None:
        started = FakeStartedTasks()

        assert run_hook(hook_input(None, 'intern'), started).decision == 'deny'
        assert started.asked == [Worker.INTERN]

    @pytest.mark.parametrize('target', OTHER_TARGETS)
    @pytest.mark.parametrize('caller', [*OUTSIDE_CALLERS, pytest.param(ENGINEER, id='worker')])
    def test_a_dispatch_of_any_other_type_reads_no_state(
        self, caller: str | None, target: str
    ) -> None:
        started = FakeStartedTasks()

        run_hook(hook_input(caller, target), started)

        assert started.asked == []

    @pytest.mark.parametrize('caller', [ENGINEER, MERGE_VADER, INTERN])
    def test_a_workers_dispatch_of_it_is_denied_by_the_row_and_reads_no_state(
        self, caller: str
    ) -> None:
        started = FakeStartedTasks(answer=(self.ONE_FILE,))

        verdict = run_hook(hook_input(caller, INTERN), started)

        assert verdict.decision == 'deny'
        assert verdict.reason.startswith(f'{caller} may not dispatch {INTERN}; it may dispatch: ')
        assert started.asked == []


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
        check_dispatch(io.StringIO(hook_input(ENGINEER, self.TARGET)), output, FakeStartedTasks())
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
