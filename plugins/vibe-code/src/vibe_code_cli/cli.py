import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Protocol, runtime_checkable

from vibe_code_cli.builtin import Services
from vibe_code_cli.hook import command as hook_command
from vibe_code_cli.instruction import command as instruction_command
from vibe_code_cli.mcp import command as mcp_command
from vibe_code_cli.plugin import command as plugin_command
from vibe_code_cli.skill import command as skill_command
from vibe_code_cli.subagent import command as subagent_command
from vibe_code_cli.tune import command as tune_command


@runtime_checkable
class CommandGroupDispatcher(Protocol):
    def build(self, parser: argparse.ArgumentParser) -> None: ...

    def dispatch(self, arguments: argparse.Namespace, services: Services) -> int: ...


class GroupName(StrEnum):
    SKILL = auto()
    HOOK = auto()
    SUBAGENT = auto()
    INSTRUCTION = auto()
    MCP = auto()
    PLUGIN = auto()
    TUNE = auto()


def default_dispatchers() -> dict[GroupName, CommandGroupDispatcher]:
    return {
        GroupName.SKILL: skill_command,
        GroupName.HOOK: hook_command,
        GroupName.SUBAGENT: subagent_command,
        GroupName.INSTRUCTION: instruction_command,
        GroupName.MCP: mcp_command,
        GroupName.PLUGIN: plugin_command,
        GroupName.TUNE: tune_command,
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandGroups:
    dispatchers: dict[GroupName, CommandGroupDispatcher] = field(
        default_factory=default_dispatchers
    )


class Arguments(argparse.Namespace):
    group: str
    handler: Callable[[argparse.Namespace, Services], int] | None = None


def build_parser(groups: CommandGroups | None = None) -> argparse.ArgumentParser:
    groups = groups or CommandGroups()
    parser = argparse.ArgumentParser(
        prog='vibe-code',
        description='Validate and scaffold the artifacts the vibe-code skills author.',
    )
    subparsers = parser.add_subparsers(dest='group')
    for name, dispatcher in groups.dispatchers.items():
        dispatcher.build(subparsers.add_parser(name.value))
    return parser


def main(argv: Sequence[str] | None = None, services: Services | None = None) -> int:
    services = services or Services()
    groups = CommandGroups()
    parser = build_parser(groups)
    arguments = parser.parse_args(argv, namespace=Arguments())
    if arguments.handler is None:
        parser.print_help(sys.stderr)
        return 2
    group = groups.dispatchers[GroupName(arguments.group)]
    return group.dispatch(arguments, services)
