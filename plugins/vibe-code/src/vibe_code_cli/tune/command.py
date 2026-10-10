import argparse
import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path

from vibe_code_cli.builtin import Services
from vibe_code_cli.tune.collisions import DEFAULT_THRESHOLD
from vibe_code_cli.tune.domain.values import Judge, LoopOptions, RoutingOptions
from vibe_code_cli.tune.errors import TuneError
from vibe_code_cli.tune.services import StartRequest
from vibe_code_cli.tune.store import encode_json
from vibe_code_cli.tune.wiring import Settings, TuneServices, build_services

DEFAULT_STATE = Path('.skill-tuning/state.json')
DEFAULTS = LoopOptions()
REFUSED = 1
COULD_NOT_RUN = 2

type CommandMethod = Callable[[argparse.Namespace], str]


class TuneCommand(StrEnum):
    INIT = auto()
    NEXT = auto()
    ROUTE = auto()
    SUBMIT = auto()
    STATUS = auto()
    LINT = auto()
    REPORT = auto()
    APPLY = auto()


def loop_options(arguments: argparse.Namespace) -> LoopOptions:
    routing = RoutingOptions(
        concurrency=arguments.concurrency,
        timeout_seconds=arguments.timeout,
        model=arguments.model,
    )
    return LoopOptions(
        judge=arguments.judge,
        routing=routing,
        validation_fraction=arguments.validation_fraction,
        batch_size=arguments.batch_size,
        max_rounds=arguments.max_rounds,
        patience=arguments.patience,
        seed=arguments.seed,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandLine:
    services: TuneServices

    def init(self, arguments: argparse.Namespace) -> str:
        request = StartRequest(
            skills=tuple(arguments.skills),
            triggers=arguments.triggers,
            options=loop_options(arguments),
            force=arguments.force,
        )
        return encode_json(self.services.tuning.start(request))

    def next(self, _arguments: argparse.Namespace) -> str:
        return encode_json(self.services.tuning.next_work())

    def route(self, _arguments: argparse.Namespace) -> str:
        return encode_json(asyncio.run(self.services.routing.route_pending()))

    def submit(self, arguments: argparse.Namespace) -> str:
        answer = arguments.answer.read_bytes()
        return encode_json(self.services.tuning.submit(arguments.packet, answer))

    def status(self, _arguments: argparse.Namespace) -> str:
        return encode_json(self.services.tuning.status())

    def lint(self, arguments: argparse.Namespace) -> str:
        return encode_json(self.services.publishing.lint(arguments.skills))

    def report(self, _arguments: argparse.Namespace) -> str:
        return self.services.publishing.report()

    def apply(self, arguments: argparse.Namespace) -> str:
        return encode_json(self.services.publishing.apply(dry_run=arguments.dry_run))

    def methods(self) -> dict[TuneCommand, CommandMethod]:
        return {
            TuneCommand.INIT: self.init,
            TuneCommand.NEXT: self.next,
            TuneCommand.ROUTE: self.route,
            TuneCommand.SUBMIT: self.submit,
            TuneCommand.STATUS: self.status,
            TuneCommand.LINT: self.lint,
            TuneCommand.REPORT: self.report,
            TuneCommand.APPLY: self.apply,
        }


def settings_from(arguments: argparse.Namespace) -> Settings:
    return Settings(
        state=arguments.state,
        claude=arguments.claude,
        collision_threshold=arguments.threshold,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class TuneHandler:
    command: TuneCommand

    def run(self, arguments: argparse.Namespace) -> str:
        command_line = CommandLine(services=build_services(settings_from(arguments)))
        return command_line.methods()[self.command](arguments)

    def __call__(self, arguments: argparse.Namespace, _services: Services) -> int:
        try:
            output = self.run(arguments)
        except TuneError as problem:
            print(f'error: {problem}', file=sys.stderr)
            return REFUSED
        except OSError as problem:
            print(f'error: {problem}', file=sys.stderr)
            return COULD_NOT_RUN
        sys.stdout.write(output)
        return 0


def configure_init(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--skills', type=Path, nargs='+', required=True, metavar='PATH')
    parser.add_argument('--triggers', type=Path, required=True, metavar='FILE')
    parser.add_argument('--force', action='store_true', help='replace an existing run')
    parser.add_argument('--judge', type=Judge, choices=list(Judge), default=DEFAULTS.judge)
    parser.add_argument('--model', default=DEFAULTS.routing.model, help='routing model')
    parser.add_argument('--concurrency', type=int, default=DEFAULTS.routing.concurrency)
    parser.add_argument('--timeout', type=float, default=DEFAULTS.routing.timeout_seconds)
    parser.add_argument('--validation-fraction', type=float, default=DEFAULTS.validation_fraction)
    parser.add_argument('--batch-size', type=int, default=DEFAULTS.batch_size)
    parser.add_argument('--max-rounds', type=int, default=DEFAULTS.max_rounds)
    parser.add_argument('--patience', type=int, default=DEFAULTS.patience)
    parser.add_argument('--seed', type=int, default=DEFAULTS.seed)


def configure_submit(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--packet', required=True)
    parser.add_argument(
        '--answer', type=Path, required=True, metavar='FILE', help='answer JSON file'
    )


def configure_route(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--claude', help='path to the claude executable')


def configure_lint(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--skills', type=Path, nargs='+', required=True, metavar='PATH')
    parser.add_argument('--threshold', type=float, default=DEFAULT_THRESHOLD)


def configure_apply(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--dry-run', action='store_true')


COMMAND_HELP = {
    TuneCommand.INIT: 'load skills and a trigger set',
    TuneCommand.NEXT: 'print the next piece of work',
    TuneCommand.ROUTE: 'judge by real Claude Code routing',
    TuneCommand.SUBMIT: 'answer one packet',
    TuneCommand.STATUS: 'print the stage and scores',
    TuneCommand.LINT: 'find competing descriptions',
    TuneCommand.REPORT: 'print the Markdown report',
    TuneCommand.APPLY: 'write the tuned descriptions',
}
CONFIGURERS: dict[TuneCommand, Callable[[argparse.ArgumentParser], None]] = {
    TuneCommand.INIT: configure_init,
    TuneCommand.ROUTE: configure_route,
    TuneCommand.SUBMIT: configure_submit,
    TuneCommand.LINT: configure_lint,
    TuneCommand.APPLY: configure_apply,
}


def build(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE, metavar='FILE')
    parser.set_defaults(claude=None, threshold=DEFAULT_THRESHOLD)
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    for command, summary in COMMAND_HELP.items():
        subparser = commands.add_parser(command.value, help=summary, description=summary)
        subparser.set_defaults(handler=TuneHandler(command=command))
        if configure := CONFIGURERS.get(command):
            configure(subparser)


def dispatch(arguments: argparse.Namespace, services: Services) -> int:
    return int(arguments.handler(arguments, services))
