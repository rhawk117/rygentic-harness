"""The close service: what still blocks closing a ticket, and the closing itself.

Live work is what a closed ticket would strand: a task that is not verified, a review finding
with no decision or chosen for fixing and not fixed, a debug note still present, and a ticket
branch with commits on no remote or checked out with uncommitted changes. `check` returns it as a
result that says blocked, never as an error, and answers for a closed ticket too.

`close` refuses while live work remains and then needs what the ticket shipped. The closing lines
are redacted and held to one line each, and a line that redaction lengthens past its limit is
refused. The ticket's closed status and its closing are stored in
one transaction, and the archive goes back as text with its paths: the service writes no file
and the agent writes both.

Git is optional to the service. With no git binary, or outside a repository, the branch is not
asked about and the text says git was not consulted. Inside a repository a branch that is not
there has nothing to strand, and one git cannot be asked about, for its name or for a read that
failed, is a blocker that says so. The server and `verify run` refuse sooner: neither opens
the state without a git work tree to key the database by.

Everything above the class reads no service state.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import count

from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.declarative import PROSE_LIMIT
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import (
    LIVE_DEBUG_FILE,
    Git,
    GitRefusal,
    RecordFiles,
    UntrackedFiles,
    Workspace,
    revision_error,
)
from mightymodels_plugin.redaction import redact, redact_within
from mightymodels_plugin.tools.close.rendering import DECISION_LIMIT, archive_markdown
from mightymodels_plugin.tools.close.repository import CloseRepository, close_transaction
from mightymodels_plugin.tools.close.schema import (
    ArchivedCommand,
    ArchivedDecision,
    ArchivedReview,
    ArchivedTask,
    ArchiveRecord,
    ClosedArchive,
    CloseView,
    Closing,
)
from mightymodels_plugin.tools.contract.assessment import NEVER_RUN
from mightymodels_plugin.tools.contract.tables import CommandRow, ReceiptRow
from mightymodels_plugin.tools.investigation.ledger import Ledger, linked_ledgers
from mightymodels_plugin.tools.investigation.schema import EntryKind
from mightymodels_plugin.tools.review.schema import Result
from mightymodels_plugin.tools.snapshot.latest_review import LatestReview, latest_review_of
from mightymodels_plugin.tools.snapshot.repository import SnapshotRepository
from mightymodels_plugin.tools.task.gates import plan_task_problem
from mightymodels_plugin.tools.task.schema import Status, TaskRecord
from mightymodels_plugin.tools.task.service import problem_lines, records_of
from mightymodels_plugin.tools.ticket.schema import WorkUnit
from mightymodels_plugin.tools.ticket.service import unit_of

GOTCHA_LIMIT = 3
NO_VERIFIED_WORK = 'no verified task work is recorded'
LIVE_DEBUG = f'{LIVE_DEBUG_FILE} is present: a debug is still live'


class ShippedRequiredError(StateError):
    def __init__(self) -> None:
        super().__init__('shipped is required: what this ticket delivered, one line')


class TooManyGotchasError(StateError):
    def __init__(self, given: int) -> None:
        super().__init__(f'at most {GOTCHA_LIMIT} gotchas; the rest belong in the docs or nowhere')
        self.given = given


def one_line(text: str) -> str:
    return redact(' '.join(text.split()))


def closing_line(text: str, field: str) -> str:
    return redact_within(' '.join(text.split()), field, PROSE_LIMIT)


def one_lined(closing: Closing) -> Closing:
    pr = '' if closing.pr is None else closing_line(closing.pr, 'pr')
    return Closing(
        shipped=closing_line(closing.shipped, 'shipped'),
        pr=pr or None,
        gotchas=tuple(
            closing_line(gotcha, 'gotchas') for gotcha in closing.gotchas if gotcha.strip()
        ),
    )


def closing_error(closing: Closing) -> StateError | None:
    if not closing.shipped:
        return ShippedRequiredError()
    if len(closing.gotchas) > GOTCHA_LIMIT:
        return TooManyGotchasError(len(closing.gotchas))
    return None


def unverified_lines(records: Sequence[TaskRecord]) -> list[str]:
    problems = map(plan_task_problem, records)
    return [problem for problem in problems if problem is not None]


def task_blockers(records: Sequence[TaskRecord]) -> list[str]:
    never_started = [record for record in records if record.status is Status.PENDING]
    started = [record for record in records if record.status is not Status.PENDING]
    return [
        *unverified_lines(never_started),
        *([] if started else [NO_VERIFIED_WORK]),
        *unverified_lines(started),
    ]


def review_blockers(review: LatestReview | None) -> list[str]:
    if review is None:
        return []
    return [
        *(f'review finding {finding_id} has no decision' for finding_id in review.undecided()),
        *(
            f'review finding {finding_id} was chosen for fixing and is not fixed'
            for finding_id in review.open_remediation()
        ),
    ]


def unchecked(branch: str, reason: str) -> str:
    return f'branch {branch} could not be checked: {reason}'


def unpushed_blockers(git: Git, branch: str) -> list[str]:
    unpushed = git.commits_on_no_remote(branch)
    if unpushed is None:
        return [unchecked(branch, 'git could not count its commits on no remote')]
    return [f'branch {branch} has {unpushed} commits on no remote'] if unpushed > 0 else []


def uncommitted_blockers(git: Git, branch: str) -> list[str]:
    if git.current_branch() != branch:
        return []
    dirty = git.dirty_paths(untracked=UntrackedFiles.NO)
    if dirty is None:
        return [unchecked(branch, 'git could not read the working-tree status')]
    return [f'branch {branch} is checked out with uncommitted changes'] if len(dirty) > 0 else []


def branch_blockers(git: Git, branch: str) -> list[str]:
    if (error := revision_error(branch)) is not None:
        return [unchecked(branch, str(error))]
    if git.resolve_commit(f'refs/heads/{branch}') is None:
        return []
    return [*unpushed_blockers(git, branch), *uncommitted_blockers(git, branch)]


def git_note(refusal: GitRefusal | None) -> str:
    return '' if refusal is None else f'git was not consulted: {refusal}\n'


def blocked_view(heading: str, blockers: Sequence[str], refusal: GitRefusal | None) -> CloseView:
    text = f'{heading}\n{problem_lines(blockers)}{git_note(refusal)}'
    return CloseView(text=text, blocked=True, blockers=tuple(blockers))


def archived_command(command: CommandRow, receipt: ReceiptRow | None) -> ArchivedCommand:
    return ArchivedCommand(
        id=command.command_id,
        argv=tuple(command.argv),
        expect_exit=command.expect_exit,
        outcome=NEVER_RUN if receipt is None else receipt.outcome,
        head=None if receipt is None else receipt.head,
        digest=None if receipt is None else receipt.digest,
    )


def archived_review(review: LatestReview | None) -> ArchivedReview | None:
    if review is None:
        return None
    decided = review.decided()
    by_decision: dict[str, tuple[str, ...]] = {}
    for finding_id, disposition in decided.items():
        label = Result.FIXED if review.is_fixed(finding_id) else disposition.decision
        by_decision[label] = (*by_decision.get(label, ()), finding_id)
    run = review.standing.run
    return ArchivedReview(
        run=run.run_id.root,
        depth=run.depth,
        findings=len(review.findings),
        by_decision=by_decision,
        reasons={
            finding_id: one_line(disposition.reason)
            for finding_id, disposition in decided.items()
            if disposition.reason
        },
    )


def archived_decisions(ledgers: Sequence[Ledger]) -> tuple[ArchivedDecision, ...]:
    decisions = [
        ArchivedDecision(text=one_line(record.text), origin=ledger.origin_of(record))
        for ledger in ledgers
        for record in ledger.live_of_kind(EntryKind.DECISION)
    ]
    return tuple(decisions[-DECISION_LIMIT:])


def archive_record(
    recorded: SnapshotRepository, unit: WorkUnit, closing: Closing, *, head: str | None
) -> ArchiveRecord:
    slug = unit.slug
    receipts = recorded.contracts.latest_receipts(slug)
    return ArchiveRecord(
        slug=slug,
        closed_at=now(),
        head=head,
        shipped=closing.shipped,
        pr=closing.pr,
        tracker=unit.ticket.tracker,
        summary=unit.ticket.summary,
        investigations=unit.investigations,
        tasks={
            record.id: ArchivedTask(status=record.status, attempts=record.attempts)
            for record in records_of(recorded.tasks, slug).values()
        },
        verification=tuple(
            archived_command(command, receipts.get(command.command_id))
            for command in recorded.contracts.commands(slug)
        ),
        decisions=archived_decisions(
            linked_ledgers(recorded.investigations, unit.investigations).ledgers
        ),
        review=archived_review(latest_review_of(recorded.reviews, slug)),
        gotchas=closing.gotchas,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CloseService:
    workspace: Workspace
    database: Database

    def live_work(
        self, repository: CloseRepository, unit: WorkUnit, refusal: GitRefusal | None
    ) -> list[str]:
        recorded = repository.recorded
        debug_note = self.workspace.handoffs.live_debug(unit.slug)
        git = self.workspace.git
        return [
            *task_blockers(tuple(records_of(recorded.tasks, unit.slug).values())),
            *([LIVE_DEBUG] if debug_note.is_file() else []),
            *review_blockers(latest_review_of(recorded.reviews, unit.slug)),
            *([] if refusal is not None else branch_blockers(git, unit.ticket.branch)),
        ]

    def free_archive_files(self, slug: Slug) -> RecordFiles:
        candidates = (self.workspace.handoffs.archive(slug, repeat) for repeat in count(1))
        return next(files for files in candidates if not files.markdown.exists())

    def check(self, slug: Slug) -> CloseView:
        refusal = self.workspace.git.refusal()
        with close_transaction(self.database) as repository:
            unit = unit_of(repository.recorded.tickets.staged_row(slug))
            blockers = self.live_work(repository, unit, refusal)
        if blockers:
            return blocked_view('live work remains', blockers, refusal)
        return CloseView(text=f'{slug} has no live work\n{git_note(refusal)}', blocked=False)

    def close(self, slug: Slug, closing: Closing) -> CloseView:
        git = self.workspace.git
        refusal = git.refusal()
        with close_transaction(self.database) as repository:
            unit = unit_of(repository.recorded.tickets.staged_row(slug))
            blockers = self.live_work(repository, unit, refusal)
            if blockers:
                return blocked_view('not closed; live work remains', blockers, refusal)
            redacted = one_lined(closing)
            if (error := closing_error(redacted)) is not None:
                raise error
            record = archive_record(repository.recorded, unit, redacted, head=git.resolve_head())
            files = self.free_archive_files(slug)
            archive = self.workspace.relative_to_root(files.markdown)
            repository.record_closing(record, archive=archive)
        return CloseView(
            text=f'closed {slug}; archive at {archive}\n{git_note(refusal)}',
            blocked=False,
            archive=ClosedArchive(
                markdown=archive_markdown(record, files.record.name),
                record=record,
                markdown_path=archive,
                record_path=self.workspace.relative_to_root(files.record),
            ),
        )
