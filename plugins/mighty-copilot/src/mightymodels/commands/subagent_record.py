"""The `mightymodels subagent-record` command, which the SubagentStop hook on the scouts runs.

When `mightymodels:triage:code-scout` or `mightymodels:triage:web-scout` stops, its final message
is its report, unless it handed the report back with the SubagentHandback tool
(`subagent_handback.py`), in which case the final message is closing text that the server drops.
The command leaves it in the scout-report spool for the state server to take in on its next tool
call: one file named `spool_file_prefix(key)`, `CLOSING_PART`, a unique part and `.json`, written
under the suffix `.part` and renamed, so the server never reads half a report. The key is the
repository the session started in, and the target is the scout and its `agent_id`, since the hook
input carries no dispatch. The command needs the data directory and a git work tree but not the
database.

Any other agent type leaves the spool as it is, and so does a stop with no final message. A report
whose file would pass `SPOOL_FILE_BYTES` is not written, because the server could not take it in.
Every failure is said on standard error with exit 0, and nothing is written.
"""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from mightymodels.commands.hook_context import HookContext, plugin_worker
from mightymodels.commands.rejection import skipped
from mightymodels.core.codec import encode_compact
from mightymodels.core.data_directory import DataDirectoryMissingError
from mightymodels.core.declarative import NAME_LIMIT
from mightymodels.core.errors import StateError
from mightymodels.core.repository_key import RepositoryKey, spool_file_prefix
from mightymodels.core.routing import Worker
from mightymodels.core.workspace import Checkout, find_root, git_at
from mightymodels.tools.similarity.schema import Scout
from mightymodels.tools.similarity.spool import (
    CLOSING_PART,
    REPORT_SUFFIX,
    SPOOL_DIRECTORY,
    SPOOL_FILE_BYTES,
)

SCOUTS = frozenset({Worker.CODE_SCOUT, Worker.WEB_SCOUT})
UNFINISHED_SUFFIX = '.part'


class NoReportError(StateError):
    def __init__(self) -> None:
        super().__init__('the scout left no report text, so there is no report to keep')


class ReportTooLargeError(StateError):
    def __init__(self, size: int) -> None:
        super().__init__(
            f'the report as a spool file is {size} bytes and the most the server takes in is '
            f'{SPOOL_FILE_BYTES}, so it was not written'
        )


class SpoolNotWrittenError(StateError):
    def __init__(self, spool: Path, cause: OSError) -> None:
        super().__init__(f'the spool {spool} could not be written: {cause}')


@dataclass(slots=True, kw_only=True, frozen=True)
class ScoutStop:
    scout: Scout
    target: str
    report: str

    def spool_file_content(self, key: RepositoryKey) -> bytes:
        document = {
            'repository_key': key.root,
            'scout': self.scout,
            'target': self.target,
            'report': self.report,
        }
        return encode_compact(document)


def scout_report_of(fields: dict[str, object], report: object) -> ScoutStop | NoReportError | None:
    worker = plugin_worker(fields)
    if worker not in SCOUTS:
        return None
    if not isinstance(report, str) or not report.strip():
        return NoReportError()
    scout = Scout(worker)
    agent_id = fields.get('agent_id')
    target = f'{scout} {agent_id}'[:NAME_LIMIT] if isinstance(agent_id, str) else str(scout)
    return ScoutStop(scout=scout, target=target, report=report)


def scout_stop_of(fields: dict[str, object]) -> ScoutStop | NoReportError | None:
    return scout_report_of(fields, fields.get('last_assistant_message'))


def write_to_spool(spool: Path, name: str, content: bytes) -> SpoolNotWrittenError | None:
    unfinished = spool.joinpath(f'{name}{UNFINISHED_SUFFIX}')
    try:
        spool.mkdir(parents=True, exist_ok=True)
        unfinished.write_bytes(content)
        unfinished.replace(spool.joinpath(f'{name}{REPORT_SUFFIX}'))
    except OSError as error:
        return SpoolNotWrittenError(spool, error)
    return None


def spool_report(stop: ScoutStop, context: HookContext, part: str) -> StateError | None:
    data_directory = context.data_directory()
    if isinstance(data_directory, DataDirectoryMissingError):
        return data_directory
    checkout = git_at(find_root(context.environ, context.cwd)).checkout()
    if not isinstance(checkout, Checkout):
        return checkout
    key = checkout.repository_key()
    content = stop.spool_file_content(key)
    if len(content) > SPOOL_FILE_BYTES:
        return ReportTooLargeError(len(content))
    name = f'{spool_file_prefix(key)}{part}{uuid4().hex}'
    return write_to_spool(data_directory.joinpath(SPOOL_DIRECTORY), name, content)


def run_hook(context: HookContext) -> int:
    fields = context.fields()
    if isinstance(fields, StateError):
        return skipped(fields)
    stop = scout_stop_of(fields)
    if stop is None:
        return 0
    failure = stop if isinstance(stop, NoReportError) else spool_report(stop, context, CLOSING_PART)
    return 0 if failure is None else skipped(failure)
