import os
import subprocess
from pathlib import Path

MIGHTYMODELS_DIR = '.mightymodels'
TICKET_FILE = 'ticket.yml'
# Names the live ticket when the repository carries more than one, or none yet.
ACTIVE_TICKET_VAR = 'MIGHTYMCP_TICKET'
# .mcp.json sets MIGHTYMCP_PROJECT_DIR to ${CLAUDE_PROJECT_DIR}; a harness that does not
# substitute the placeholder leaves the literal behind, which is never a path.
PROJECT_DIR_PLACEHOLDER = '${CLAUDE_PROJECT_DIR}'
PROJECT_DIR_VARS = ('MIGHTYMCP_PROJECT_DIR', 'CLAUDE_PROJECT_DIR')
UNSAFE_FRAGMENTS = ('/', '\\', '..')


class TicketPathError(ValueError):
    """A ticket path cannot be built: unsafe name, or no usable repository root."""


def safe_name(value: str) -> str:
    """Return a slug or task id unchanged, or raise when it is not one path segment."""
    name = value.strip()
    if not name:
        raise TicketPathError('name is empty')
    for fragment in UNSAFE_FRAGMENTS:
        if fragment in name:
            raise TicketPathError(f'name {value!r} contains {fragment!r}')
    return name


def repo_root(explicit: Path | None = None) -> Path:
    """Resolve the repository root: the env vars, then git, then the explicit argument."""
    candidate = _env_root() or _git_root() or explicit
    if candidate is None:
        raise TicketPathError(
            'no repository root: set CLAUDE_PROJECT_DIR or run inside a git checkout'
        )
    root = candidate.resolve()
    if not root.joinpath('.git').exists():
        raise TicketPathError(f'{root} is not a repository root: no .git entry')
    return root


def ticket_dir(slug: str, root: Path | None = None) -> Path:
    """Return .mightymodels/<slug> under the repository root, after vetting the slug."""
    name = safe_name(slug)
    return repo_root(root).joinpath(MIGHTYMODELS_DIR, name)


def active_ticket(root: Path | None = None) -> str:
    """Return the slug of the live ticket: the only one on disk, else the env override."""
    directory = repo_root(root).joinpath(MIGHTYMODELS_DIR)
    slugs = [
        path.name
        for path in sorted(directory.glob('*'))
        if path.joinpath(TICKET_FILE).is_file()
    ]
    if len(slugs) == 1:
        return slugs[0]
    override = os.environ.get(ACTIVE_TICKET_VAR, '').strip()
    if override:
        return safe_name(override)
    raise TicketPathError(
        f'{len(slugs)} tickets under {directory}: '
        f'set {ACTIVE_TICKET_VAR} to the slug of the live one'
    )


def git_output(args: list[str], cwd: Path) -> str | None:
    """Run git in cwd and return its stripped stdout, or None when it fails."""
    proc = subprocess.run(  # noqa: S603 -- argv list built here, never a shell string
        ['git', *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _env_root() -> Path | None:
    for name in PROJECT_DIR_VARS:
        value = os.environ.get(name, '').strip()
        if value and value != PROJECT_DIR_PLACEHOLDER:
            return Path(value)
    return None


def _git_root() -> Path | None:
    toplevel = git_output(['rev-parse', '--show-toplevel'], cwd=Path.cwd())
    return Path(toplevel) if toplevel else None
