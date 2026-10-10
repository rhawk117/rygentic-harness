import argparse
import itertools
import shutil
import sys
import tempfile
from pathlib import Path

from vibe_code_cli.builtin import BuiltinRunner, Services
from vibe_code_cli.findings import CannotCheckError, Finding, error, report
from vibe_code_cli.subagent.body import check_body
from vibe_code_cli.subagent.fields import check_fields
from vibe_code_cli.subagent.text import parse_agent_text

NO_FRONTMATTER_BLOCK = (
    'no frontmatter block: the file must start with a --- line and close the block with '
    'another --- line, or Claude Code treats it as documentation and does not load it'
)


def build(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser(
        'validate',
        help='run claude plugin validate on an agent file, then the checks it misses',
    )
    validate.add_argument('agent_file', type=Path, metavar='FILE', help='agent .md file')
    validate.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    validate.set_defaults(handler=validate_command)


def dispatch(arguments: argparse.Namespace, services: Services) -> int:
    return int(arguments.handler(arguments, services))


def validate_command(arguments: argparse.Namespace, services: Services) -> int:
    path = arguments.agent_file
    try:
        text = read_agent_file(path)
        findings = validate_findings(path, text, services.run_builtin)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2

    return report(path.name, findings, strict=arguments.strict)


def read_agent_file(path: Path) -> str:
    if path.suffix != ".md" or not path.is_file():
        message = f"{path} is not a .md file"
        raise CannotCheckError(message)

    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        message = f'could not read {path}: {problem}'
        raise CannotCheckError(message) from problem


def is_plugin_agent(path: Path) -> bool:
    directory = path.resolve().parent
    return directory.name == 'agents' and directory.parent.name != '.claude'


def validate_findings(path: Path, text: str, runner: BuiltinRunner) -> list[Finding]:
    plugin = is_plugin_agent(path)
    builtin_findings = run_agent_builtin(path, runner, plugin=plugin)
    builtin_errored = any(finding.level == 'error' for finding in builtin_findings)
    own_findings = check_agent(text, plugin=plugin, builtin_errored=builtin_errored)
    return list(itertools.chain(builtin_findings, own_findings))


def run_agent_builtin(path: Path, runner: BuiltinRunner, *, plugin: bool) -> list[Finding]:
    with tempfile.TemporaryDirectory() as staging:
        root = Path(staging)
        try:
            target = stage_agent(path, root, plugin=plugin)
        except OSError as problem:
            message = f'could not stage {path} for claude: {problem}'
            raise CannotCheckError(message) from problem

        return runner(target, include_manifest=False)


def stage_agent(path: Path, root: Path, *, plugin: bool) -> Path:
    agents = root.joinpath(".claude", "agents")
    target = agents
    if plugin:
        manifest = root.joinpath(".claude-plugin", "plugin.json")
        manifest.parent.mkdir()
        manifest.write_text('{"name": "staged"}', encoding="utf-8")
        agents = root.joinpath("agents")
        target = root

    agents.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, agents.joinpath(path.name))
    return target


def check_agent(text: str, *, plugin: bool, builtin_errored: bool) -> list[Finding]:
    agent = parse_agent_text(text)
    if not agent.has_block:
        return [] if plugin else [error(NO_FRONTMATTER_BLOCK)]

    if agent.yaml_problem and not builtin_errored:
        message = f"frontmatter is not valid YAML ({agent.yaml_problem}); the field checks could not run"
        raise CannotCheckError(message)

    findings: list[Finding] = [error(agent.key_problem)] if agent.key_problem else []

    if agent.fields:
        findings.extend(
            check_fields(
                agent.fields,
                plugin=plugin,
                unquoted_colon=agent.unquoted_colon,
                builtin_errored=builtin_errored,
            )
        )

    return list(itertools.chain(findings, check_body(agent.body)))
