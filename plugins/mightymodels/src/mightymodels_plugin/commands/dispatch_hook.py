"""The `mightymodels dispatch-hook` command, which the plugin's PreToolUse hook on `Agent` runs.

Claude Code lets a subagent dispatch any subagent type and ignores an allow-list in a subagent's
definition, so the plugin enforces the "delegate only to" lines of its agent files here. The hook
input is JSON on standard input; a call made inside a subagent carries `agent_type`, and the main
conversation's does not. The rows police only this plugin's workers, whose `agent_type` begins
`mightymodels:`: a worker's dispatch outside its row is denied, a name under that prefix that is
no worker has no row, and unreadable input that names such an `agent_type` is denied. A worker's
type is `mightymodels:<folder>:<name>`, the folder being the one its agent file is in, so a type
without the folder or with another folder is no worker. A target is a worker under its type or
under its bare name.

Every other caller is judged as the main thread: input without `agent_type`, one whose `agent_type`
is not a string, a built-in subagent, another plugin's agent. Its dispatch of the engineer or the
architect is denied, with the step to take, while the one unclosed ticket on the checked-out branch
has no task in progress, and when the tickets cannot be read. With no unclosed ticket on the branch
it gets no decision, as if the plugin were not installed. With several it gets no decision either,
and the user is shown one line naming them.

Its dispatch of the architect or the wingman is an escalation, and the owner hears of a block
before one is spent on it. While the one unclosed ticket on the checked-out branch has a task a
block stopped (`BlockedTask`) and the ticket's `auto-escalate` is off, the dispatch is answered
`ask`, naming each such task with the reasons of its block. For the architect the denial above
comes first. With `auto-escalate` on, with no such task, with no unclosed ticket on the branch or
several, and when the tickets cannot be read, this rule gives no decision.

Its dispatch of any other worker but the intern, and of a type that is no worker, gets no decision
and reads no state.

One rule holds whoever the caller is. The intern takes only a tiny task, so a dispatch of the
intern that the rows let through is denied unless the intern has a task in progress on the ticket
whose branch is checked out and every such task owns exactly one file. The denial says why and
names the engineer, which takes a task of any size. When the started tasks cannot be read the
dispatch is denied with the reason they could not.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import BinaryIO, Protocol, TextIO, runtime_checkable

from mightymodels_plugin.core.codec import UnreadableJsonError, decode_text, encode_compact
from mightymodels_plugin.core.routing import FOLDERS, Worker

PLUGIN_PREFIX = 'mightymodels:'
AGENT_TYPE_KEY = 'agent_type'
PLUGIN_CALLER = re.compile(rf'"{AGENT_TYPE_KEY}"\s*:\s*"{re.escape(PLUGIN_PREFIX)}')
UNREADABLE = 'a dispatch was refused: the hook input is not the expected JSON'
HOOK_EVENT = 'PreToolUse'
DENY = 'deny'
ASK = 'ask'
NO_TARGETS = frozenset[Worker]()
TINY_OWNED_FILES = 1
NO_STARTED_TASK = 'no task is started for the intern on the ticket whose branch is checked out'
STARTED_UNREADABLE = 'the started task could not be read ({error})'
NO_TASK_IN_PROGRESS = (
    '{target} was refused: ticket {slug}, whose branch is checked out, has no task in progress. '
    'Start the task with the `task` tool (action `start`, `by` naming this worker), then dispatch '
    'again.'
)
TICKETS_UNREADABLE = (
    '{target} was refused: the tasks in progress could not be read ({error}), so a started task '
    'cannot be told from none. Dispatch again once the state can be read.'
)
SEVERAL_TICKETS = (
    'mightymodels did not check the dispatch of {target} for a started task: the checked-out '
    'branch has {count} unclosed tickets ({names}), and the hook acts only when it has one'
)

DISPATCH_RULES: Mapping[Worker, frozenset[Worker]] = MappingProxyType(
    {
        Worker.CODE_SCOUT: NO_TARGETS,
        Worker.WEB_SCOUT: NO_TARGETS,
        Worker.QUALITYLENS: NO_TARGETS,
        Worker.FACT_CHECKER: NO_TARGETS,
        Worker.ENGINEER: frozenset({Worker.CODE_SCOUT}),
        Worker.ARCHITECT: frozenset({Worker.CODE_SCOUT}),
        Worker.INTERN: NO_TARGETS,
        Worker.GITTY_UP: NO_TARGETS,
        Worker.WINGMAN: NO_TARGETS,
        Worker.TERRY_TOOLCHAIN: NO_TARGETS,
        Worker.MERGE_VADER: frozenset({Worker.CODE_SCOUT, Worker.WEB_SCOUT, Worker.QUALITYLENS}),
        Worker.UNCLE_BOB: frozenset({Worker.CODE_SCOUT, Worker.QUALITYLENS}),
    }
)
STARTED_BEFORE_DISPATCH = frozenset({Worker.ENGINEER, Worker.ARCHITECT})
ESCALATIONS = frozenset({Worker.ARCHITECT, Worker.WINGMAN})
BLOCK_GOES_TO_THE_OWNER_FIRST = (
    '{target} was held for the owner: ticket {slug}, whose branch is checked out, has a task a '
    'block stopped ({blocks}), and its `auto-escalate` is off. Approve this dispatch to '
    'escalate, or decline it and say what to do about the block. `auto-escalate: true` under '
    '`handoff-context` in ticket.yml, validated with the `ticket` tool, lets an escalation '
    'through without this question.'
)


@dataclass(slots=True, kw_only=True, frozen=True)
class StartedTask:
    id: str
    owned: tuple[str, ...]


type StartedOrUnreadable = Sequence[StartedTask] | Exception


@dataclass(slots=True, kw_only=True, frozen=True)
class BlockedTask:
    id: str
    status: str
    reasons: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchTickets:
    unclosed: tuple[str, ...] = ()
    in_progress: tuple[str, ...] = ()
    auto_escalate: bool = False
    blocked: tuple[BlockedTask, ...] = ()


type BranchTicketsOrUnreadable = BranchTickets | Exception


@runtime_checkable
class StartedTasks(Protocol):
    def started_by(self, worker: Worker) -> StartedOrUnreadable: ...

    def tickets_on_branch(self) -> BranchTicketsOrUnreadable: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class Denied:
    reason: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Asked:
    reason: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Unjudged:
    warning: str


type Ruling = Denied | Asked | Unjudged | None


def agent_type(worker: Worker) -> str:
    return f'{PLUGIN_PREFIX}{FOLDERS[worker]}:{worker}'


def worker_named(name: str) -> Worker | None:
    return next((worker for worker in Worker if name in {worker, agent_type(worker)}), None)


def decoded_object(text: str) -> dict[str, object] | None:
    try:
        decoded = decode_text(text)
    except UnreadableJsonError:
        return None
    if not isinstance(decoded, dict):
        return None
    return {str(key): value for key, value in decoded.items()}


def target_of(fields: Mapping[str, object]) -> object:
    tool_input = fields.get('tool_input')
    return tool_input.get('subagent_type') if isinstance(tool_input, dict) else None


def allowed_names(allowed: frozenset[Worker]) -> str:
    return ', '.join(sorted(allowed)) or 'nothing'


def allowed_for(caller: str) -> frozenset[Worker]:
    worker = worker_named(caller)
    return NO_TARGETS if worker is None else DISPATCH_RULES[worker]


def denial_for_worker(caller: str, target: object) -> str | None:
    if not isinstance(target, str):
        return f'{caller} was refused a dispatch: the hook input names no target type'
    allowed = allowed_for(caller)
    worker = worker_named(target)
    if worker is not None and worker in allowed:
        return None
    return f'{caller} may not dispatch {target}; it may dispatch: {allowed_names(allowed)}'


def plugin_caller(fields: Mapping[str, object]) -> str | None:
    caller = fields.get(AGENT_TYPE_KEY)
    return caller if isinstance(caller, str) and caller.startswith(PLUGIN_PREFIX) else None


def intern_refusal(why: str) -> str:
    return (
        f'{agent_type(Worker.INTERN)} was refused: {why}. The intern takes only a tiny task, '
        f'one that owns exactly one file; dispatch {agent_type(Worker.ENGINEER)} instead.'
    )


def intern_denial(started: StartedOrUnreadable) -> str | None:
    if isinstance(started, Exception):
        return intern_refusal(STARTED_UNREADABLE.format(error=started))
    if len(started) == 0:
        return intern_refusal(NO_STARTED_TASK)
    not_tiny = [
        f'{task.id} owns {len(task.owned)} files'
        for task in started
        if len(task.owned) != TINY_OWNED_FILES
    ]
    return intern_refusal('; '.join(not_tiny)) if not_tiny else None


def unstarted_ruling(target: str, tickets: BranchTicketsOrUnreadable) -> Ruling:
    if isinstance(tickets, Exception):
        return Denied(reason=TICKETS_UNREADABLE.format(target=target, error=tickets))
    if len(tickets.unclosed) > 1:
        return Unjudged(
            warning=SEVERAL_TICKETS.format(
                target=target, count=len(tickets.unclosed), names=', '.join(tickets.unclosed)
            )
        )
    if len(tickets.unclosed) == 0 or tickets.in_progress:
        return None
    return Denied(reason=NO_TASK_IN_PROGRESS.format(target=target, slug=tickets.unclosed[0]))


def block_line(task: BlockedTask) -> str:
    return f'{task.id} {task.status}: {"; ".join(task.reasons)}'


def escalation_ruling(target: str, tickets: BranchTicketsOrUnreadable) -> Ruling:
    if isinstance(tickets, Exception) or tickets.auto_escalate or not tickets.blocked:
        return None
    return Asked(
        reason=BLOCK_GOES_TO_THE_OWNER_FIRST.format(
            target=target,
            slug=tickets.unclosed[0],
            blocks=' | '.join(map(block_line, tickets.blocked)),
        )
    )


def ticket_ruling(target: Worker, tickets: BranchTicketsOrUnreadable) -> Ruling:
    named = agent_type(target)
    started_first = target in STARTED_BEFORE_DISPATCH
    if started_first and (unstarted := unstarted_ruling(named, tickets)) is not None:
        return unstarted
    return escalation_ruling(named, tickets) if target in ESCALATIONS else None


def started_ruling(caller: str | None, target: Worker, started: StartedTasks) -> Ruling:
    if target is Worker.INTERN:
        refused = intern_denial(started.started_by(Worker.INTERN))
        return None if refused is None else Denied(reason=refused)
    if caller is None and target in STARTED_BEFORE_DISPATCH | ESCALATIONS:
        return ticket_ruling(target, started.tickets_on_branch())
    return None


def dispatch_ruling(text: str, started: StartedTasks) -> Ruling:
    fields = decoded_object(text)
    if fields is None:
        return Denied(reason=UNREADABLE) if PLUGIN_CALLER.search(text) else None
    caller = plugin_caller(fields)
    target = target_of(fields)
    if caller is not None and (refused := denial_for_worker(caller, target)) is not None:
        return Denied(reason=refused)
    worker = worker_named(target) if isinstance(target, str) else None
    return None if worker is None else started_ruling(caller, worker, started)


def hook_output(ruling: Denied | Asked | Unjudged) -> dict[str, object]:
    if isinstance(ruling, Unjudged):
        return {'systemMessage': ruling.warning}
    return {
        'hookSpecificOutput': {
            'hookEventName': HOOK_EVENT,
            'permissionDecision': ASK if isinstance(ruling, Asked) else DENY,
            'permissionDecisionReason': ruling.reason,
        }
    }


def write_ruling(output: BinaryIO, ruling: Ruling) -> int:
    if ruling is not None:
        output.write(encode_compact(hook_output(ruling)) + b'\n')
    return 0


def check_dispatch(stdin: TextIO, output: BinaryIO, started: StartedTasks) -> int:
    return write_ruling(output, dispatch_ruling(stdin.read(), started))
