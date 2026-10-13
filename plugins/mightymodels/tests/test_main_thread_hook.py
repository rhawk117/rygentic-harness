"""The PreToolUse hook on Edit, Write and Bash holds a caller that is no plugin worker while the
checked-out branch has one unclosed ticket: its edit outside the ticket directories is answered
`ask`, and its push is denied until the ticket is ready to land or while that cannot be read."""

import io
import json
from dataclasses import dataclass, field
from enum import StrEnum, auto

import pytest
from mightymodels_plugin.commands.dispatch_hook import (
    BranchTickets,
    BranchTicketsOrUnreadable,
    agent_type,
)
from mightymodels_plugin.commands.main_thread_hook import (
    Landing,
    LandingOrUnreadable,
    check_main_thread,
    names_a_push,
)
from mightymodels_plugin.commands.tests.hook_inputs import MAIN_THREAD_CALLERS
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Worker
from sqlalchemy.exc import OperationalError

TICKET = 'retry-queue'
OUTSIDE = '/work/checkout/src/queue.py'
ONE_TICKET = BranchTickets(unclosed=(TICKET,))
NO_TICKET = BranchTickets()
SEVERAL_TICKETS = BranchTickets(unclosed=('drain-loop', TICKET))
UNPROVEN = ('T2 is in-progress, not verified', 'T1.AC-1 has no receipt at the current HEAD')
NOT_READY = Landing(unclosed=(TICKET,), unproven=UNPROVEN)
READY = Landing(unclosed=(TICKET,))
NO_LANDING = Landing()
SEVERAL_LANDINGS = Landing(unclosed=('drain-loop', TICKET))
NO_DECISION = b''
EDIT_TOOLS = ('Edit', 'Write')
UNREADABLE_STATES = (
    pytest.param(StateError('CLAUDE_PLUGIN_DATA is not set'), id='no-data-directory'),
    pytest.param(PermissionError(13, 'Permission denied'), id='operating-system'),
    pytest.param(OperationalError('SELECT 1', {}, Exception('database is locked')), id='database'),
)
COMMIT_WITH_A_HERE_DOCUMENT = (
    'git commit -m "$(cat <<\'EOF\'\nhold a git push until the landing receipt\nEOF\n)"'
)
PUSHES = (
    pytest.param('git push', id='plain'),
    pytest.param('git -C ../checkout push', id='another-directory'),
    pytest.param('git push --force-with-lease -u origin fix/retry', id='options-before-the-remote'),
    pytest.param('uv run pytest && git push origin HEAD', id='chained-with-and'),
    pytest.param('git add -A; git commit -m done; git push', id='chained-with-semicolons'),
    pytest.param('git status\ngit push', id='on-a-second-line'),
    pytest.param('git fetch || git push', id='chained-with-or'),
    pytest.param('true|git push', id='after-a-pipe-with-no-spaces'),
    pytest.param('(cd ../checkout && git push)', id='in-a-subshell'),
    pytest.param('out=$(git push 2>&1)', id='in-a-command-substitution'),
    pytest.param('out="$(git push 2>&1)"', id='in-a-quoted-command-substitution'),
    pytest.param('echo `git push`', id='in-backticks'),
    pytest.param('git -c http.proxy= push', id='a-configuration-value-first'),
    pytest.param('git --git-dir=.git --work-tree . --no-pager push', id='long-options-first'),
    pytest.param('GIT_TRACE=1 git push', id='behind-an-assignment'),
    pytest.param('sudo -E git push', id='behind-sudo'),
    pytest.param('env GIT_TRACE=1 git push', id='behind-env'),
    pytest.param('if ! git push; then echo failed; fi', id='behind-keywords'),
    pytest.param('echo origin | xargs git push', id='behind-xargs'),
    pytest.param('/usr/bin/git push', id='git-by-its-path'),
    pytest.param('\'git\' "push"', id='each-word-quoted'),
    pytest.param('git \\\n  push origin main', id='continued-on-the-next-line'),
    pytest.param("bash -lc 'cd ../checkout && git push'", id='given-to-bash'),
    pytest.param('sh -c "git push"', id='given-to-sh'),
    pytest.param('eval "git push"', id='given-to-eval'),
    pytest.param('git $PUSH_FLAGS push', id='a-variable-where-the-options-go'),
)
HELD_AS_PUSHES = (
    pytest.param("git push 'origin", id='a-quote-that-never-closes'),
    pytest.param("cat <<'EOF'\nit's time to git push\nEOF", id='an-apostrophe-in-a-here-document'),
    pytest.param('echo git push', id='the-two-words-of-another-command'),
    pytest.param("cat <<'EOF'\ngit push origin\nEOF", id='a-line-of-a-here-document'),
)
NO_PUSHES = (
    pytest.param('echo "git push"', id='quoted-for-echo'),
    pytest.param('git pushd', id='a-longer-word'),
    pytest.param('git stash push -m wip', id='stash-push'),
    pytest.param('git commit -m "explain why git push is held"', id='in-a-commit-message'),
    pytest.param(COMMIT_WITH_A_HERE_DOCUMENT, id='in-a-commit-message-from-a-here-document'),
    pytest.param('git log --grep push', id='an-argument-of-log'),
    pytest.param('git -C push status', id='a-directory-named-push'),
    pytest.param('git -c alias.p=push status', id='a-configuration-value'),
    pytest.param('git config alias.p push', id='an-argument-of-config'),
    pytest.param('pushd ../checkout && git status', id='pushd-and-git'),
    pytest.param('grep -rn "git push" docs', id='quoted-for-grep'),
    pytest.param('bash scripts/build.sh', id='a-script-given-to-bash'),
    pytest.param('eval "git status"', id='eval-of-another-command'),
    pytest.param('echo "$(date) pushed to git"', id='a-substitution-beside-the-words'),
    pytest.param("echo 'it'\\''s a push' 'unterminated", id='unsplittable-without-git'),
    pytest.param('git', id='git-alone'),
    pytest.param('`', id='an-operator-alone'),
    pytest.param('', id='empty'),
)


class Read(StrEnum):
    TICKETS = auto()
    LANDING = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeTicket:
    in_a_ticket_directory: bool = False
    tickets: BranchTicketsOrUnreadable = ONE_TICKET
    landing: LandingOrUnreadable = NOT_READY
    paths: list[str] = field(default_factory=list)
    reads: list[Read] = field(default_factory=list)

    def ticket_directory_holds(self, file_path: str) -> bool:
        self.paths.append(file_path)
        return self.in_a_ticket_directory

    def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        self.reads.append(Read.TICKETS)
        return self.tickets

    def landing_on_branch(self) -> LandingOrUnreadable:
        self.reads.append(Read.LANDING)
        return self.landing


def call(caller: dict[str, object], tool: str, **tool_input: object) -> str:
    return json.dumps({'tool_name': tool, 'tool_input': tool_input} | caller)


def written(text: str, ticket: FakeTicket) -> bytes:
    output = io.BytesIO()
    assert check_main_thread(io.StringIO(text), output, ticket) == 0
    return output.getvalue()


def decided(text: str, ticket: FakeTicket, decision: str) -> str:
    answer = json.loads(written(text, ticket))['hookSpecificOutput']
    assert answer['hookEventName'] == 'PreToolUse'
    assert answer['permissionDecision'] == decision
    return answer['permissionDecisionReason']


def one_line_shown(text: str, ticket: FakeTicket) -> str:
    printed = written(text, ticket)
    shown = json.loads(printed)
    assert printed.count(b'\n') == 1
    assert list(shown) == ['systemMessage']
    return shown['systemMessage']


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
@pytest.mark.parametrize('tool', EDIT_TOOLS)
class TestEditOutsideTheTicketDirectories:
    def test_with_one_unclosed_ticket_it_is_asked_naming_the_ticket_the_tool_and_the_path(
        self, caller: dict[str, object], tool: str
    ) -> None:
        ticket = FakeTicket(tickets=ONE_TICKET)

        assert decided(call(caller, tool, file_path=OUTSIDE), ticket, 'ask') == (
            f'mightymodels: ticket {TICKET} is unclosed on the checked-out branch, and this '
            f'{tool} of {OUTSIDE} is outside the ticket directories under `.mightymodels/`. The '
            'main thread hands a repository edit to a worker through a started task; approve this '
            'one only if the main thread should make it.'
        )
        assert ticket.paths == [OUTSIDE]
        assert ticket.reads == [Read.TICKETS]

    def test_with_no_unclosed_ticket_on_the_branch_it_gets_no_decision(
        self, caller: dict[str, object], tool: str
    ) -> None:
        ticket = FakeTicket(tickets=NO_TICKET)

        assert written(call(caller, tool, file_path=OUTSIDE), ticket) == NO_DECISION

    def test_with_several_tickets_it_gets_no_decision_and_one_line_naming_them(
        self, caller: dict[str, object], tool: str
    ) -> None:
        ticket = FakeTicket(tickets=SEVERAL_TICKETS)

        assert one_line_shown(call(caller, tool, file_path=OUTSIDE), ticket) == (
            f'mightymodels did not check the {tool} of {OUTSIDE} against an unclosed ticket: the '
            f'checked-out branch has 2 unclosed tickets (drain-loop, {TICKET}), and the hook acts '
            'only when it has one'
        )

    @pytest.mark.parametrize('failure', UNREADABLE_STATES)
    def test_when_the_tickets_cannot_be_read_it_goes_ahead_with_one_line_saying_why(
        self, caller: dict[str, object], tool: str, failure: Exception
    ) -> None:
        ticket = FakeTicket(tickets=failure)

        assert one_line_shown(call(caller, tool, file_path=OUTSIDE), ticket) == (
            f'mightymodels did not check the {tool} of {OUTSIDE} against an unclosed ticket: the '
            f'tickets on the checked-out branch could not be read ({failure})'
        )


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
@pytest.mark.parametrize('tool', EDIT_TOOLS)
class TestEditThatReadsNoState:
    def test_in_a_ticket_directory_it_gets_no_decision(
        self, caller: dict[str, object], tool: str
    ) -> None:
        ticket = FakeTicket(in_a_ticket_directory=True)

        assert written(call(caller, tool, file_path=OUTSIDE), ticket) == NO_DECISION
        assert ticket.reads == []

    @pytest.mark.parametrize('tool_input', [{}, {'file_path': 7}, {'file_path': None}])
    def test_with_no_path_it_gets_no_decision(
        self, caller: dict[str, object], tool: str, tool_input: dict[str, object]
    ) -> None:
        ticket = FakeTicket()

        assert written(call(caller, tool, **tool_input), ticket) == NO_DECISION
        assert (ticket.paths, ticket.reads) == ([], [])


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
@pytest.mark.parametrize('command', [*PUSHES, *HELD_AS_PUSHES])
class TestPush:
    def test_while_the_ticket_is_not_ready_it_is_denied_with_what_is_open_and_the_step_to_take(
        self, caller: dict[str, object], command: str
    ) -> None:
        ticket = FakeTicket(landing=NOT_READY)

        assert decided(call(caller, 'Bash', command=command), ticket, 'deny') == (
            f'`git push` was refused: ticket {TICKET}, whose branch is checked out, is not ready '
            f'to land: {UNPROVEN[0]}; {UNPROVEN[1]}. Close the tasks still open, then land '
            'through the `stick-the-landing` skill, whose step 1 proves the contract at HEAD '
            f'with `mightymodels verify run --slug {TICKET} --all --phase landing`; the push goes '
            'through once that has passed. The hook also holds a command whose words `git` and '
            '`push` it cannot place, so reword one that is no push.'
        )
        assert ticket.reads == [Read.LANDING]

    def test_once_the_ticket_is_ready_it_gets_no_decision(
        self, caller: dict[str, object], command: str
    ) -> None:
        ticket = FakeTicket(landing=READY)

        assert written(call(caller, 'Bash', command=command), ticket) == NO_DECISION

    def test_with_no_unclosed_ticket_on_the_branch_it_gets_no_decision(
        self, caller: dict[str, object], command: str
    ) -> None:
        ticket = FakeTicket(landing=NO_LANDING)

        assert written(call(caller, 'Bash', command=command), ticket) == NO_DECISION


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
class TestPushWithNoOneTicketToRead:
    def test_with_several_tickets_it_gets_no_decision_and_one_line_naming_them(
        self, caller: dict[str, object]
    ) -> None:
        ticket = FakeTicket(landing=SEVERAL_LANDINGS)

        assert one_line_shown(call(caller, 'Bash', command='git push'), ticket) == (
            'mightymodels did not hold this `git push`: the checked-out branch has 2 unclosed '
            f'tickets (drain-loop, {TICKET}), and the hook acts only when it has one'
        )

    @pytest.mark.parametrize('failure', UNREADABLE_STATES)
    def test_when_the_landing_cannot_be_read_it_is_denied_saying_why(
        self, caller: dict[str, object], failure: Exception
    ) -> None:
        ticket = FakeTicket(landing=failure)

        assert decided(call(caller, 'Bash', command='git push'), ticket, 'deny') == (
            '`git push` was refused: the tasks and receipts of the ticket on the checked-out '
            f'branch could not be read ({failure}), so a proven landing cannot be told from none. '
            'Push again once the state can be read.'
        )


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
class TestBashThatReadsNoState:
    @pytest.mark.parametrize('command', NO_PUSHES)
    def test_a_command_that_names_no_push_gets_no_decision(
        self, caller: dict[str, object], command: str
    ) -> None:
        ticket = FakeTicket()

        assert written(call(caller, 'Bash', command=command), ticket) == NO_DECISION
        assert ticket.reads == []

    @pytest.mark.parametrize('tool_input', [{}, {'command': 7}, {'command': ['git', 'push']}])
    def test_with_no_command_it_gets_no_decision(
        self, caller: dict[str, object], tool_input: dict[str, object]
    ) -> None:
        ticket = FakeTicket()

        assert written(call(caller, 'Bash', **tool_input), ticket) == NO_DECISION
        assert ticket.reads == []


class TestPluginWorker:
    @pytest.mark.parametrize('worker', Worker)
    @pytest.mark.parametrize(
        ('tool', 'tool_input'),
        [
            pytest.param('Edit', {'file_path': OUTSIDE}, id='edit'),
            pytest.param('Write', {'file_path': OUTSIDE}, id='write'),
            pytest.param('Bash', {'command': 'git push'}, id='push'),
            pytest.param('Bash', {'command': 'uv run pytest'}, id='bash'),
        ],
    )
    def test_its_edit_write_and_bash_get_no_decision_and_read_nothing(
        self, worker: Worker, tool: str, tool_input: dict[str, object]
    ) -> None:
        ticket = FakeTicket()
        caller: dict[str, object] = {'agent_type': agent_type(worker)}

        assert written(call(caller, tool, **tool_input), ticket) == NO_DECISION
        assert (ticket.paths, ticket.reads) == ([], [])


@pytest.mark.parametrize('caller', MAIN_THREAD_CALLERS)
class TestInputTheHookDoesNotJudge:
    @pytest.mark.parametrize('tool', ['Read', 'Agent', 'NotebookEdit', 'bash', 7, None, ['Bash']])
    def test_another_tool_gets_no_decision(self, caller: dict[str, object], tool: object) -> None:
        ticket = FakeTicket()
        text = json.dumps(
            {'tool_name': tool, 'tool_input': {'file_path': OUTSIDE, 'command': 'git push'}}
            | caller
        )

        assert written(text, ticket) == NO_DECISION
        assert (ticket.paths, ticket.reads) == ([], [])

    @pytest.mark.parametrize('tool_input', ['git push', None, ['git', 'push']])
    def test_tool_input_that_is_no_object_gets_no_decision(
        self, caller: dict[str, object], tool_input: object
    ) -> None:
        ticket = FakeTicket()
        text = json.dumps({'tool_name': 'Bash', 'tool_input': tool_input} | caller)

        assert written(text, ticket) == NO_DECISION
        assert ticket.reads == []


class TestInputThatIsNotTheExpectedJson:
    BASH_PUSH = '{"tool_name": "Bash", "tool_input": {"command": "%s"}, "elapsed": NaN}'
    WORKER_PUSH = (
        '{"agent_type": "mightymodels:workers:engineer", "tool_name": "Bash", '
        '"tool_input": {"command": "git push"}, "elapsed": NaN}'
    )
    EDIT_OF_THE_WORDS = (
        '{"tool_name": "Edit", "tool_input": {"file_path": "/x", "new_string": "git push"}, '
        '"elapsed": NaN}'
    )

    @pytest.mark.parametrize(
        'command',
        [
            pytest.param('git push', id='plain'),
            pytest.param('cd ../checkout\\ngit push', id='after-an-escaped-newline'),
            pytest.param('echo \\"git push\\"', id='the-two-words-in-escaped-quotes'),
        ],
    )
    def test_a_bash_call_with_the_words_of_a_push_is_held_as_a_push(self, command: str) -> None:
        ticket = FakeTicket(landing=NOT_READY)

        reason = decided(self.BASH_PUSH % command, ticket, 'deny')

        assert reason.startswith(f'`git push` was refused: ticket {TICKET}')
        assert ticket.reads == [Read.LANDING]

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param(BASH_PUSH % 'git pushd', id='bash-without-the-word-push'),
            pytest.param(BASH_PUSH % 'uv run pytest', id='bash-without-either-word'),
            pytest.param(WORKER_PUSH, id='a-plugin-workers-push'),
            pytest.param(EDIT_OF_THE_WORDS, id='an-edit-of-the-words'),
            pytest.param('', id='empty'),
            pytest.param('[]', id='not-an-object'),
        ],
    )
    def test_any_other_unreadable_input_gets_no_decision_and_reads_no_state(
        self, text: str
    ) -> None:
        ticket = FakeTicket()

        assert written(text, ticket) == NO_DECISION
        assert ticket.reads == []


class TestTheWordsOfACommand:
    @pytest.mark.parametrize('command', PUSHES)
    def test_a_push_is_named_wherever_it_stands(self, command: str) -> None:
        assert names_a_push(command)

    @pytest.mark.parametrize('command', HELD_AS_PUSHES)
    def test_a_command_it_cannot_place_is_named_a_push(self, command: str) -> None:
        assert names_a_push(command)

    @pytest.mark.parametrize('command', NO_PUSHES)
    def test_the_text_of_a_push_inside_another_word_is_no_push(self, command: str) -> None:
        assert not names_a_push(command)
