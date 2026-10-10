import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from vibe_code_cli.builtin import BuiltinRunner, Services
from vibe_code_cli.findings import CannotCheckError, Finding, error, report
from vibe_code_cli.frontmatter import parse_skill_text
from vibe_code_cli.skill.body import check_body
from vibe_code_cli.skill.fields import check_fields, directory_name_of


def build(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    validate = commands.add_parser(
        "validate",
        help="run claude plugin validate, then the checks it misses",
    )
    validate.add_argument(
        "skill_dir", type=Path, metavar="SKILL_DIR", help="skill directory"
    )
    validate.add_argument(
        "--strict", action="store_true", help="exit 1 on warnings too"
    )
    validate.set_defaults(handler=validate_command)


def dispatch(arguments: argparse.Namespace, services: Services) -> int:
    return int(arguments.handler(arguments, services))


def validate_command(arguments: argparse.Namespace, services: Services) -> int:
    skill_dir = arguments.skill_dir
    if not skill_dir.is_dir():
        print(f"error: {skill_dir} is not a directory", file=sys.stderr)
        return 2

    try:
        builtin_findings = run_skill_builtin(skill_dir, services.run_builtin)
        builtin_errored = any(finding.level == "error" for finding in builtin_findings)
        own_findings = check_skill(skill_dir, builtin_errored=builtin_errored)
    except CannotCheckError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    findings = [*builtin_findings, *own_findings]
    return report(
        directory_name_of(skill_dir),
        findings,
        strict=arguments.strict,
    )


def run_skill_builtin(skill_dir: Path, runner: BuiltinRunner) -> list[Finding]:
    with tempfile.TemporaryDirectory() as staging:
        skills = Path(staging).joinpath("skills")
        try:
            dest_tree = skills.joinpath(directory_name_of(skill_dir))
            shutil.copytree(skill_dir, dest_tree, symlinks=True)
        except (shutil.Error, OSError) as problem:
            message = f"could not read {skill_dir} to hand it to claude: {problem}"
            raise CannotCheckError(message) from problem

        return runner(skills)


def check_skill(skill_dir: Path, *, builtin_errored: bool = False) -> list[Finding]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [error(f"{skill_md} not found")]

    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return []
    except UnicodeError:
        return [error(f"{skill_md} is not valid UTF-8")]

    skill = parse_skill_text(text)
    if skill.yaml_problem is not None and not builtin_errored:
        message = (
            f"{skill_md}: frontmatter is not valid YAML ({skill.yaml_problem}); "
            "the field checks could not run"
        )
        raise CannotCheckError(message)

    findings: list[Finding] = [error(skill.key_problem)] if skill.key_problem else []

    if skill.fields is not None:
        findings.extend(
            check_fields(
                skill.fields,
                directory_name_of(skill_dir),
                builtin_errored=builtin_errored,
            )
        )

    findings.extend(check_body(skill_dir, text, skill.body))
    return findings
