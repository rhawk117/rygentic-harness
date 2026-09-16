import json
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from mightymcp.fleet import plugin_root
from mightymcp.paths import MIGHTYMODELS_DIR, TicketPathError, repo_root

CRASHOUT_SCRIPT = ('skills', 'crashout', 'scripts', 'crashout_journal.py')
METRICS_SCRIPT = ('skills', 'uncle-bob', 'scripts', 'metrics.py')
JOURNAL = 'crashouts.yml'
STDERR_TAIL = 10
PACKAGE_DEPTH = 1
MAX_LISTED = 50


class CrashoutEntry(BaseModel):
    """One journal entry, in the keys crashout_journal.py validates."""

    severity: str = Field(description='mild-tilt, heated, crashout, or full-meltdown')
    verdict: str = Field(description='deserved, split, or unreasonable')
    rant: str = Field(description='What the user said, verbatim')
    failures: list[str] = Field(description='What the agent did wrong, one per entry')
    root_cause: str = Field(description='The mechanism behind the failures')
    corrective_action: str = Field(description='What changes so it does not recur')
    barked_back: bool = Field(
        default=False, description='True when the agent pushed back'
    )
    ticket: str | None = Field(
        default=None, description='The ticket slug, when one is open'
    )
    branch: str | None = Field(default=None, description='The branch, when there is one')


class ScriptRun(BaseModel):
    """What one of the plugin's bundled scripts printed, unchanged."""

    stdout: str = Field(default='', description='The script stdout, verbatim')
    refusals: list[str] = Field(
        default_factory=list, description='Why the script did not succeed'
    )


def crashout_add(entry: CrashoutEntry) -> ScriptRun:
    """Append one crashout to the journal through the crashout skill's script."""
    return _crashout('add', json.dumps(entry.model_dump()))


def crashout_stats() -> ScriptRun:
    """Report the journal's counts, failures, and standing corrective actions."""
    return _crashout('stats')


def crashout_last() -> ScriptRun:
    """Print the most recent journal entry."""
    return _crashout('last')


def metrics_run(
    repo_root: str | None = None,
    package_depth: int = PACKAGE_DEPTH,
    max_listed: int = MAX_LISTED,
) -> ScriptRun:
    """Run the uncle-bob metrics script over the repository and return what it printed.

    repo_root is the fallback: the project-dir variables and git are resolved first.
    """
    root, refusals = _root(repo_root)
    if root is None:
        return ScriptRun(refusals=refusals)
    arguments = [
        str(root),
        '--package-depth',
        str(package_depth),
        '--max-listed',
        str(max_listed),
    ]
    return _run(METRICS_SCRIPT, arguments, root)


def _crashout(command: str, stdin: str | None = None) -> ScriptRun:
    root, refusals = _root(None)
    if root is None:
        return ScriptRun(refusals=refusals)
    journal = root.joinpath(MIGHTYMODELS_DIR, JOURNAL)
    return _run(CRASHOUT_SCRIPT, [command, '--journal', str(journal)], root, stdin)


def _root(explicit: str | None) -> tuple[Path | None, list[str]]:
    try:
        return repo_root(Path(explicit) if explicit else None), []
    except TicketPathError as err:
        return None, [str(err)]


def _run(
    script: tuple[str, ...], arguments: list[str], cwd: Path, stdin: str | None = None
) -> ScriptRun:
    path = plugin_root().joinpath(*script)
    if not path.is_file():
        return ScriptRun(refusals=[f'no script at {path}'])
    proc = subprocess.run(  # noqa: S603 -- argv list built here, never a shell string
        [sys.executable, str(path), *arguments],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        tail = '\n'.join(proc.stderr.strip().splitlines()[-STDERR_TAIL:])
        return ScriptRun(
            stdout=proc.stdout,
            refusals=[f'{path.name} exited {proc.returncode}: {tail}'],
        )
    return ScriptRun(stdout=proc.stdout)
