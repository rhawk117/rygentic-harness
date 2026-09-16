from pathlib import Path
from typing import Any

from mightymcp.brief import BriefRead, brief_read
from mightymcp.hooks.guard import payload_root, payload_slug
from mightymcp.paths import MIGHTYMODELS_DIR, git_output

BRIEFS = 'briefs'
LOG_DEPTH = '20'
SHORT_SHA = 7
# the lint sweep is not the work a brief records; durable-before-advance is about the work
LINT_PREFIX = 'chore(lint)'
REMINDER = (
    'commit {sha} is recorded in no DONE half, and {path} still has none; '
    'append it with brief_append_done before the sprint advances.'
)


def stop(payload: dict[str, Any]) -> dict[str, Any]:
    """Remind the primary of a commit that landed without the DONE half behind it."""
    root = payload_root(payload)
    slug = payload_slug(root)
    if slug is None:
        return {}
    briefs = _briefs(root, slug)
    pending = next(
        (read for read in briefs if read.asked is not None and read.done is None), None
    )
    if pending is None:
        return {}
    sha = _unrecorded(root, [read.done.commit for read in briefs if read.done])
    if sha is None:
        return {}
    return {'systemMessage': REMINDER.format(sha=sha, path=pending.path)}


def _briefs(root: Path, slug: str) -> list[BriefRead]:
    directory = root.joinpath(MIGHTYMODELS_DIR, slug, BRIEFS)
    return [brief_read(slug, path.stem) for path in sorted(directory.glob('task-*.md'))]


def _unrecorded(root: Path, recorded: list[str]) -> str | None:
    """The newest commit no DONE half records, reading down until one of them does."""
    log = git_output(['log', '--format=%H %s', '-n', LOG_DEPTH], cwd=root)
    if log is None:
        return None
    for line in log.splitlines():
        sha, _, subject = line.partition(' ')
        if any(sha.startswith(hash_) for hash_ in recorded):
            return None
        if not subject.startswith(LINT_PREFIX):
            return sha[:SHORT_SHA]
    return None
