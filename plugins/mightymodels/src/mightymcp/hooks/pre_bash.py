import shlex
from pathlib import Path
from typing import Any

from mightymcp.hooks.guard import SCOUT, agent_role, deny, payload_root
from mightymcp.hookstate import count_bash
from mightymcp.paths import MIGHTYMODELS_DIR
from mightymcp.prune import prunable

# never-rules from the fleet contracts: they hold for every role, primary included
NEVER = (
    '--no-verify',
    'push --force',
    'push -f',
    '--force-with-lease',
    'reset --hard',
)
GIT = 'git'
GITTY_UP = 'gitty-up'
SEPARATORS = ('|', '||', '&&', ';', '&')
REDIRECTIONS = ('>', '>>')
MUTATING = ('rm', 'mv', 'tee')
MUTATING_GIT = ('add', 'commit', 'push', 'checkout', 'reset', 'rebase', 'stash')
MUTATING_UV = ('add', 'remove')
RECURSIVE = ('--recursive',)
# the budgets the agent files name; the call that would exceed one is refused
BUDGETS = {SCOUT: 5, 'budgetron': 10}


def pre_bash(payload: dict[str, Any]) -> dict[str, Any]:
    """Guard the never-rules, the read-only roles, the Bash budgets, and pruning."""
    command = payload['tool_input']['command']
    role = agent_role(payload.get('agent_type', ''))
    tokens = _tokens(command)
    segments = _segments(tokens)
    calls = _count(payload, role)

    reason = (
        _never_reason(command)
        or _role_reason(role, tokens, segments)
        or _budget_reason(role, calls)
        or _prune_reason(payload, segments)
    )
    return deny(reason) if reason else {}


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


def _count(payload: dict[str, Any], role: str | None) -> int:
    agent_id = payload.get('agent_id', '')
    if role is None or not agent_id:
        return 0
    return count_bash(payload_root(payload), payload['session_id'], agent_id, role)


def _never_reason(command: str) -> str | None:
    folded = ' '.join(command.split())
    named = [rule for rule in NEVER if rule in folded]
    if not named:
        return None
    return f'{named[0]} is a never-rule; solve the obstacle instead of bypassing it'


def _role_reason(
    role: str | None, tokens: list[str], segments: list[list[str]]
) -> str | None:
    if role == GITTY_UP and any(segment[0] == GIT for segment in segments):
        return 'gitty-up never runs git; its Bash is for gh'
    if role != SCOUT:
        return None
    mutation = _mutation(tokens, segments)
    if mutation is None:
        return None
    return f'a scout stays read-only; {mutation} mutates state'


def _mutation(tokens: list[str], segments: list[list[str]]) -> str | None:
    if any(token in REDIRECTIONS or token.startswith('>') for token in tokens):
        return 'a redirection'
    return next(filter(None, (_segment_mutation(segment) for segment in segments)), None)


def _segment_mutation(segment: list[str]) -> str | None:
    command, *arguments = segment
    subcommand = _subcommand(arguments)
    if command in MUTATING:
        return command
    if command == 'sed' and any(argument.startswith('-i') for argument in arguments):
        return 'sed -i'
    if command == GIT and subcommand in MUTATING_GIT:
        return f'git {subcommand}'
    if command == 'uv' and subcommand in MUTATING_UV:
        return f'uv {subcommand}'
    if command == 'pip' and subcommand == 'install':
        return 'pip install'
    return None


def _subcommand(arguments: list[str]) -> str:
    return next((argument for argument in arguments if not argument.startswith('-')), '')


def _budget_reason(role: str | None, calls: int) -> str | None:
    budget = BUDGETS.get(role or '')
    if budget is None or calls <= budget:
        return None
    return f'a {role} runs on {budget} Bash calls; this is call {calls}'


def _prune_reason(payload: dict[str, Any], segments: list[list[str]]) -> str | None:
    cwd = Path(payload['cwd'])
    slugs = [slug for segment in segments for slug in _removed_slugs(segment, cwd)]
    for slug in slugs:
        check = prunable(slug)
        if check.reasons:
            return (
                f'{MIGHTYMODELS_DIR}/{slug} still holds live work: '
                f'{"; ".join(check.reasons)}'
            )
    return None


def _removed_slugs(segment: list[str], cwd: Path) -> list[str]:
    command, *arguments = segment
    if command != 'rm' or not _recursive(arguments):
        return []
    slugs = (_ticket_slug(argument, cwd) for argument in arguments)
    return [slug for slug in slugs if slug]


def _recursive(arguments: list[str]) -> bool:
    return any(_recursive_flag(argument) for argument in arguments)


def _recursive_flag(argument: str) -> bool:
    if argument in RECURSIVE:
        return True
    short = argument.startswith('-') and not argument.startswith('--')
    return short and 'r' in argument.lower()


def _ticket_slug(argument: str, cwd: Path) -> str | None:
    if argument.startswith('-'):
        return None
    target = Path(cwd, argument)
    if target.parent.name != MIGHTYMODELS_DIR:
        return None
    return target.name
