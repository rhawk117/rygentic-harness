import re
from pathlib import Path

from msgspec import UNSET

from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.hook.file import HooksFile
from vibe_code_cli.hook.nodes import Handler
from vibe_code_cli.hook.schema import CommandHook

PLUGIN_ROOT_MARKER = '@CLAUDE_PLUGIN_ROOT@'
PROJECT_DIR_MARKER = '@CLAUDE_PROJECT_DIR@'

PLACEHOLDER = re.compile(r'"?\$\{?(CLAUDE_PLUGIN_ROOT|CLAUDE_PROJECT_DIR)\}?"?')

SCRIPT_SUFFIXES = ('.py', '.sh', '.ps1')
SCRIPT_REFERENCE = re.compile(
    r"(?<![\w.-])([^\s\"'`|;&<>]+\.(?:py|sh|ps1))(?=$|[\s\"'`|;&<>])",
    re.IGNORECASE,
)


def script_findings(handler: Handler, hooks_file: HooksFile) -> list[Finding]:
    hook = handler.hook
    if not isinstance(hook, CommandHook):
        return []

    references = (
        shell_references(hook.command)
        if hook.args is UNSET
        else exec_form_references(hook.command, hook.args)
    )

    findings = (script_finding(handler, reference, hooks_file) for reference in references)
    return [finding for finding in findings if finding is not None]


def shell_references(command: str) -> list[str]:
    return [str(reference) for reference in SCRIPT_REFERENCE.findall(marked(command))]


def exec_form_references(command: str, args: list[str]) -> list[str]:
    candidates = [command, *args]
    return [marked(candidate) for candidate in candidates if names_a_script(candidate)]


def names_a_script(value: str) -> bool:
    return value.lower().endswith(SCRIPT_SUFFIXES)


def marked(command: str) -> str:
    return PLACEHOLDER.sub(r'@\1@', command)


def script_finding(handler: Handler, reference: str, hooks_file: HooksFile) -> Finding | None:
    located = locate(reference, hooks_file)
    if located is None:
        return None
    path, literal_absolute = located
    if not path.exists():
        return missing_script_finding(handler, path, literal_absolute=literal_absolute)
    if not path.is_file():
        return error(f'{handler.where}: script path is not a file: {path}')
    return None


def missing_script_finding(handler: Handler, path: Path, *, literal_absolute: bool) -> Finding:
    if literal_absolute:
        return warning(
            f'{handler.where}: absolute script path {path} does not exist on this machine; '
            'it may be runtime-specific'
        )
    return error(f'{handler.where}: script not found at {path}')


def locate(reference: str, hooks_file: HooksFile) -> tuple[Path, bool] | None:
    roots = (
        (PLUGIN_ROOT_MARKER, hooks_file.plugin_root),
        (PROJECT_DIR_MARKER, hooks_file.project_dir),
    )
    rooted = next(((marker, root) for marker, root in roots if reference.startswith(marker)), None)
    if rooted is not None:
        marker, root = rooted
        if root is None:
            return None
        return (root / reference.removeprefix(marker).lstrip('/')).resolve(), False
    if '$' in reference or '%' in reference or reference.startswith('~'):
        return None
    path = Path(reference.replace('\\', '/'))
    return (path, True) if path.is_absolute() else None
