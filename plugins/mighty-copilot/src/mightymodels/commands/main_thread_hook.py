"""The `mightymodels main-thread-hook` command, which the plugin's PreToolUse hook on `Edit`,
`Write` and `Bash` runs.

While the checked-out branch has one unclosed ticket the main thread hands repository edits to a
worker and pushes only a proven landing. The caller rule is the dispatch hook's: a caller whose
`agent_type` begins `mightymodels:` is a plugin worker and gets no decision here, and every other
caller is judged as the main thread.

An `Edit` or `Write` whose `file_path` is in a ticket directory gets no decision and reads no
state. Any other one is answered `ask` while the branch has one unclosed ticket, so the user
approves it in the permission prompt. When the tickets cannot be read the edit goes ahead and the
user is shown one line saying it was not checked.

A `Bash` command that names no push gets no decision and reads no state. One that does is denied,
with what is still open and the step to take, until the ticket is ready to land (`Landing`), and
when that cannot be read.

A push is found in the command's shell words, never in its text. A word that is `git`, bare or
under a path, followed by git's own options and then the word `push` is a push wherever it stands
in the command: after `&&`, `;`, `|` or a newline, inside `( )`, `$( )` or backticks, behind an
assignment, a keyword or a wrapper such as `sudo`, `env` or `xargs`. The command a shell is given
with `-c`, the words of an `eval`, and a quoted word that holds a command substitution and no
here-document are read the same way. So `echo "git push"`, `git pushd`, `git stash push` and a
commit message that says `git push` are no push. A variable where git's options go is passed over
as an option. A command that cannot be split into words, because a quote never closes, is held as
a push when it has the words `git` and `push`, and so is hook input that is not the expected JSON
when it names the `Bash` tool and has both words.

With no unclosed ticket on the branch neither tool gets a decision. With several neither does, and
the user is shown one line naming them.
"""

import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import BinaryIO, Protocol, TextIO, runtime_checkable

from mightymodels.commands.dispatch_hook import (
    PLUGIN_CALLER,
    Asked,
    BranchTicketsOrUnreadable,
    Denied,
    Ruling,
    Unjudged,
    decoded_object,
    plugin_caller,
    write_ruling,
)

EDIT_TOOLS = frozenset({'Edit', 'Write'})
BASH_TOOL = 'Bash'
BASH_CALL = re.compile(rf'"tool_name"\s*:\s*"{BASH_TOOL}"')
GIT = 'git'
PUSH = 'push'
PUSH_WORDS = (re.compile(rf'\b{GIT}\b'), re.compile(rf'\b{PUSH}\b'))
GIT_OPTIONS_WITH_A_VALUE = frozenset(
    {
        '-C',
        '-c',
        '--git-dir',
        '--work-tree',
        '--namespace',
        '--super-prefix',
        '--config-env',
        '--attr-source',
    }
)
OPTION_OR_VARIABLE = ('-', '$')
SHELLS = frozenset({'sh', 'bash', 'zsh', 'dash', 'ksh'})
EVAL = 'eval'
SHELL_OPERATORS = '();<>|&`'
COMMAND_SUBSTITUTIONS = ('$(', '`')
HERE_DOCUMENT = '<<'
LINE_CONTINUATION = '\\\n'
JSON_ESCAPE = re.compile(r'\\.')
EDIT_OUTSIDE = (
    'mightymodels: ticket {slug} is unclosed on the checked-out branch, and this {tool} of {path} '
    'is outside the ticket directories under `.mightymodels/`. The main thread hands a repository '
    'edit to a worker through a started task; approve this one only if the main thread should '
    'make it.'
)
EDIT_UNREADABLE = (
    'mightymodels did not check the {tool} of {path} against an unclosed ticket: the tickets on '
    'the checked-out branch could not be read ({error})'
)
EDIT_SEVERAL_TICKETS = (
    'mightymodels did not check the {tool} of {path} against an unclosed ticket: the checked-out '
    'branch has {count} unclosed tickets ({names}), and the hook acts only when it has one'
)
PUSH_HELD = (
    '`git push` was refused: ticket {slug}, whose branch is checked out, is not ready to land: '
    '{unproven}. Close the tasks still open, then land through the `stick-the-landing` skill, '
    'whose step 1 proves the contract at HEAD with `mightymodels verify run --slug {slug} --all '
    '--phase landing`; the push goes through once that has passed. The hook also holds a command '
    'whose words `git` and `push` it cannot place, so reword one that is no push.'
)
PUSH_UNREADABLE = (
    '`git push` was refused: the tasks and receipts of the ticket on the checked-out branch could '
    'not be read ({error}), so a proven landing cannot be told from none. Push again once the '
    'state can be read.'
)
PUSH_SEVERAL_TICKETS = (
    'mightymodels did not hold this `git push`: the checked-out branch has {count} unclosed '
    'tickets ({names}), and the hook acts only when it has one'
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Landing:
    unclosed: tuple[str, ...] = ()
    unproven: tuple[str, ...] = ()


type LandingOrUnreadable = Landing | Exception


@runtime_checkable
class TicketOnBranch(Protocol):
    def ticket_directory_holds(self, file_path: str) -> bool: ...

    def tickets_on_branch(self) -> BranchTicketsOrUnreadable: ...

    def landing_on_branch(self) -> LandingOrUnreadable: ...


def shell_words(command: str) -> list[str] | None:
    lexer = shlex.shlex(
        command.replace(LINE_CONTINUATION, ''), posix=True, punctuation_chars=SHELL_OPERATORS
    )
    lexer.whitespace_split = True
    lexer.commenters = ''
    try:
        return list(lexer)
    except ValueError:
        return None


def program(word: str) -> str:
    return word.rpartition('/')[2]


def git_subcommand(arguments: Sequence[str]) -> str | None:
    position = 0
    while position < len(arguments) and arguments[position].startswith(OPTION_OR_VARIABLE):
        position += 2 if arguments[position] in GIT_OPTIONS_WITH_A_VALUE else 1
    return arguments[position] if position < len(arguments) else None


def is_command_option(word: str) -> bool:
    return word.startswith('-') and not word.startswith('--') and 'c' in word


def command_of_shell(arguments: Sequence[str]) -> str | None:
    after_option = next(
        (position + 1 for position, word in enumerate(arguments) if is_command_option(word)), None
    )
    if after_option is None or after_option >= len(arguments):
        return None
    return arguments[after_option]


def nested_command(words: Sequence[str], position: int) -> str | None:
    word = words[position]
    if program(word) == EVAL:
        return ' '.join(words[position + 1 :])
    if program(word) in SHELLS:
        return command_of_shell(words[position + 1 :])
    is_operator = word.strip(SHELL_OPERATORS) == ''
    substitutes = any(mark in word for mark in COMMAND_SUBSTITUTIONS)
    return word if substitutes and not is_operator and HERE_DOCUMENT not in word else None


def pushes_at(words: Sequence[str], position: int) -> bool:
    if program(words[position]) == GIT:
        return git_subcommand(words[position + 1 :]) == PUSH
    nested = nested_command(words, position)
    return nested is not None and names_a_push(nested)


def has_the_words_of_a_push(text: str) -> bool:
    return all(word.search(text) is not None for word in PUSH_WORDS)


def names_a_push(command: str) -> bool:
    words = shell_words(command)
    if words is None:
        return has_the_words_of_a_push(command)
    return any(pushes_at(words, position) for position in range(len(words)))


def unreadable_input_names_a_push(text: str) -> bool:
    if PLUGIN_CALLER.search(text) is not None or BASH_CALL.search(text) is None:
        return False
    return has_the_words_of_a_push(JSON_ESCAPE.sub(' ', text))


def outside_edit_ruling(tool: str, file_path: str, tickets: BranchTicketsOrUnreadable) -> Ruling:
    if isinstance(tickets, Exception):
        return Unjudged(warning=EDIT_UNREADABLE.format(tool=tool, path=file_path, error=tickets))
    if len(tickets.unclosed) > 1:
        return Unjudged(
            warning=EDIT_SEVERAL_TICKETS.format(
                tool=tool,
                path=file_path,
                count=len(tickets.unclosed),
                names=', '.join(tickets.unclosed),
            )
        )
    if len(tickets.unclosed) == 0:
        return None
    return Asked(reason=EDIT_OUTSIDE.format(slug=tickets.unclosed[0], tool=tool, path=file_path))


def edit_ruling(tool: str, file_path: str, ticket: TicketOnBranch) -> Ruling:
    if ticket.ticket_directory_holds(file_path):
        return None
    return outside_edit_ruling(tool, file_path, ticket.tickets_on_branch())


def push_ruling(landing: LandingOrUnreadable) -> Ruling:
    if isinstance(landing, Exception):
        return Denied(reason=PUSH_UNREADABLE.format(error=landing))
    if len(landing.unclosed) > 1:
        return Unjudged(
            warning=PUSH_SEVERAL_TICKETS.format(
                count=len(landing.unclosed), names=', '.join(landing.unclosed)
            )
        )
    if len(landing.unclosed) == 0 or len(landing.unproven) == 0:
        return None
    return Denied(
        reason=PUSH_HELD.format(slug=landing.unclosed[0], unproven='; '.join(landing.unproven))
    )


def tool_ruling(fields: Mapping[str, object], ticket: TicketOnBranch) -> Ruling:
    tool = fields.get('tool_name')
    tool_input = fields.get('tool_input')
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get('file_path')
    command = tool_input.get('command')
    if tool in EDIT_TOOLS and isinstance(file_path, str):
        return edit_ruling(tool, file_path, ticket)
    if tool == BASH_TOOL and isinstance(command, str) and names_a_push(command):
        return push_ruling(ticket.landing_on_branch())
    return None


def main_thread_ruling(text: str, ticket: TicketOnBranch) -> Ruling:
    fields = decoded_object(text)
    if fields is None:
        held = unreadable_input_names_a_push(text)
        return push_ruling(ticket.landing_on_branch()) if held else None
    if plugin_caller(fields) is not None:
        return None
    return tool_ruling(fields, ticket)


def check_main_thread(stdin: TextIO, output: BinaryIO, ticket: TicketOnBranch) -> int:
    return write_ruling(output, main_thread_ruling(stdin.read(), ticket))
