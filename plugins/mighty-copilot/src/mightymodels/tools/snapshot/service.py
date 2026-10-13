"""The snapshot service: a ticket's objective state, read from the database and from git.

A snapshot is what a handoff needs and nothing a model wrote from memory: the ticket, the
repository, every task with its attempts, each contract command judged at HEAD from its latest
receipt, the passing commands, the failed and blocked attempts not to repeat, and where the
latest review run stands. Each list is cut to the caller's limit. The decisions and the open
questions are the live entries of the investigations the ticket links, the latest of each kept,
and a linked investigation with no ledger is a warning. The answer and subagent sections are in
the record and read empty: the database holds no row for them yet.

The service works without git. With no git binary, or outside a repository, the repository
section is empty and a warning says why. The server refuses sooner: it opens no state without a
git work tree to key the database by.

The service writes no file. It returns the record, its Markdown and the two paths under the
ticket's handoffs directory, and the agent writes them. Everything above the class reads no
service state.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import islice

from mightymodels.clock import now
from mightymodels.core.slug import Slug
from mightymodels.core.workspace import (
    GitQueries,
    GitRefusal,
    UntrackedFiles,
    Workspace,
)
from mightymodels.head import short_head
from mightymodels.tools.contract.assessment import Assessment, Taken
from mightymodels.tools.contract.schema import Outcome, Receipt
from mightymodels.tools.contract.store import RecordedCommand
from mightymodels.tools.investigation.ledger import Ledger, LinkedLedgers, linked_ledgers
from mightymodels.tools.investigation.schema import EntryKind
from mightymodels.tools.review.schema import Decision
from mightymodels.tools.snapshot.latest_review import LatestReview, latest_review_of
from mightymodels.tools.snapshot.rendering import snapshot_markdown
from mightymodels.tools.snapshot.schema import (
    CheckState,
    FailedAttempt,
    LedgerLine,
    PassingCommand,
    RepositoryState,
    ReviewDecision,
    ReviewState,
    SnapshotRecord,
    SnapshotView,
    TaskState,
    TicketSummary,
)
from mightymodels.tools.snapshot.store import SnapshotStore
from mightymodels.tools.task.gates import STUCK
from mightymodels.tools.task.schema import Status, TaskRecord
from mightymodels.tools.task.service import records_of
from mightymodels.tools.task.store import Transition
from mightymodels.tools.ticket.schema import WorkUnit

NOT_STARTED = 'not started'


def git_warnings(refusal: GitRefusal | None) -> tuple[str, ...]:
    return () if refusal is None else (f'git was not consulted: {refusal}',)


def repository_state(git: GitQueries, limit: int) -> RepositoryState:
    dirty = git.dirty_paths(untracked=UntrackedFiles.NORMAL)
    return RepositoryState(
        branch=git.current_branch(),
        head=git.resolve_head(),
        dirty_count=None if dirty is None else len(dirty),
        dirty=() if dirty is None else tuple(dirty[:limit]),
    )


def ticket_summary(unit: WorkUnit) -> TicketSummary:
    return TicketSummary(
        summary=unit.ticket.summary,
        status=unit.status,
        scope=unit.ticket.scope,
        tracker=unit.ticket.tracker,
    )


def task_state(record: TaskRecord) -> TaskState:
    return TaskState(
        task=record.id,
        status=NOT_STARTED if record.status is Status.PENDING else record.status,
        attempts=record.attempts,
        reasons=record.reasons,
    )


def check_state(receipt: Receipt | None, head: str | None) -> str:
    taken = None if receipt is None else Taken(outcome=receipt.outcome, head=receipt.head)
    return Assessment(taken=taken, head=head).text


def check_states(
    commands: Sequence[RecordedCommand], receipts: Mapping[str, Receipt], head: str | None
) -> tuple[CheckState, ...]:
    return tuple(
        CheckState(id=command.id, state=check_state(receipts.get(command.id), head))
        for command in commands
    )


def last_passed(command: RecordedCommand, receipts: Mapping[str, Receipt]) -> bool:
    receipt = receipts.get(command.id)
    return receipt is not None and receipt.outcome == Outcome.PASSED


def passing_commands(
    commands: Sequence[RecordedCommand], receipts: Mapping[str, Receipt], limit: int
) -> tuple[PassingCommand, ...]:
    passing = (
        PassingCommand(id=command.id, argv=command.argv)
        for command in commands
        if last_passed(command, receipts)
    )
    return tuple(islice(passing, limit))


def failed_attempts(stuck: Sequence[Transition]) -> tuple[FailedAttempt, ...]:
    return tuple(
        FailedAttempt(
            task=transition.task_id,
            to=transition.after,
            reason='; '.join(transition.reasons),
            head=short_head(transition.head),
            at=transition.at,
        )
        for transition in stuck
    )


def ledger_lines(ledgers: Sequence[Ledger], kind: EntryKind, limit: int) -> tuple[LedgerLine, ...]:
    lines = [
        LedgerLine(
            kind=record.kind, text=record.text, cite=record.cite, origin=ledger.origin_of(record)
        )
        for ledger in ledgers
        for record in ledger.live_of_kind(kind)
    ]
    return tuple(lines[-limit:])


def ledger_warnings(linked: LinkedLedgers) -> tuple[str, ...]:
    return tuple(f'investigation {investigation} is missing' for investigation in linked.missing)


def review_state(review: LatestReview | None, limit: int) -> ReviewState | None:
    if review is None:
        return None
    run = review.standing.run
    decisions = (
        ReviewDecision(finding=finding_id, decision=decided.decision, reason=decided.reason)
        for finding_id, decided in review.decided().items()
        if decided.decision is not Decision.FIX
    )
    return ReviewState(
        run=run.run_id.root,
        depth=run.depth,
        head=short_head(run.head),
        findings=len(review.findings),
        undecided=tuple(review.undecided()),
        remediation_open=tuple(review.open_remediation()),
        decisions=tuple(islice(decisions, limit)),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotService:
    workspace: Workspace
    store: SnapshotStore
    git: GitQueries

    def take(self, slug: Slug, limit: int) -> SnapshotView:
        repository_now = repository_state(self.git, limit)
        with self.store.transaction() as repository:
            unit = repository.tickets.staged_ticket(slug)
            commands = repository.contracts.commands(slug)
            receipts = repository.contracts.latest_receipts(slug)
            linked = linked_ledgers(repository.investigations, unit.investigations)
            record = SnapshotRecord(
                slug=slug,
                generated_at=now(),
                ticket=ticket_summary(unit),
                repository=repository_now,
                tasks=tuple(map(task_state, records_of(repository.tasks, slug).values())),
                checks=check_states(commands, receipts, repository_now.head),
                works=passing_commands(commands, receipts, limit),
                decisions=ledger_lines(linked.ledgers, EntryKind.DECISION, limit),
                open_questions=ledger_lines(linked.ledgers, EntryKind.OPEN, limit),
                do_not_retry=failed_attempts(
                    repository.tasks.latest_transitions_into(slug, STUCK, limit)
                ),
                review=review_state(latest_review_of(repository.reviews, slug), limit),
                warnings=(*git_warnings(self.git.refusal()), *ledger_warnings(linked)),
            )
        files = self.workspace.handoffs.snapshot(slug)
        return SnapshotView(
            markdown=snapshot_markdown(record),
            record=record,
            markdown_path=self.workspace.relative_to_root(files.markdown),
            record_path=self.workspace.relative_to_root(files.record),
        )
