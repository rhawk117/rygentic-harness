"""The ticket service: ticket.yml stays a file, and validating it stages a row.

`write` renders the interview answers into ticket.yml and refuses to overwrite a ticket the
user may have tweaked. `validate` reads the file back, hand edits included, and stages or
refreshes the ticket's row without touching task progress. `update_context` replaces the
context lines in the file and restages it. `show` reads the staged ticket back. `branch_named` turns
the user's branch answer into the name `write` records.

A ticket may link investigations, and each link must name one that has a ledger. `validate` and
`update_context` read the ledgers in the transaction that stages the row. `write` stages nothing,
so it opens a transaction only when its answers link an investigation.

The service is built once by whoever owns the workspace, and holds it with the ticket store and
git. A method that reads or writes a ticket opens one transaction on the store, which hands it the
repository. Everything above the class reads no service state: it checks a parsed ticket, or maps
one shape of a ticket to another.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from mightymodels.clock import now
from mightymodels.core.errors import StateError
from mightymodels.core.routing import FIXED_WORKERS, Scope, Worker, fixed_model
from mightymodels.core.slug import InvalidSlugError, Slug, parsed_slug
from mightymodels.core.workspace import GitQueries, Workspace
from mightymodels.tools.ticket.schema import (
    BranchChoice,
    TicketAnswers,
    TicketContext,
    TicketSection,
    TicketView,
    WorkUnit,
)
from mightymodels.tools.ticket.store import TicketRepository, TicketStore
from mightymodels.tools.ticket.ticket_file import (
    CONTEXT_KEY,
    PRIMARY_AGENT,
    Node,
    Tree,
    parse,
    ticket_text,
    with_context,
)

CONTEXT_LIMIT = 6
TOP_LEVEL_KEYS = frozenset(
    {
        'task',
        'summary',
        'triaged-at',
        CONTEXT_KEY,
        'companion-docs',
        'subagent-models',
        'handoff-context',
        'investigations',
    }
)
COMPANION_KEYS = frozenset({'issue-number', 'jira-key', 'reference-urls'})
AUTO_ESCALATE_KEY = 'auto-escalate'
HANDOFF_KEYS = frozenset(
    {'scope', 'plan-first', 'branch-name', 'worktrees-okay', AUTO_ESCALATE_KEY}
)
KNOWN_WORKERS = frozenset({PRIMARY_AGENT, *(worker.value for worker in Worker)})
IMPLEMENTERS = frozenset({Worker.ENGINEER.value, Worker.ARCHITECT.value})

type Check = tuple[bool, str]


class TicketExistsError(StateError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} exists; edit it by hand, then run validate')
        self.path = path


class BranchNameRequiredError(StateError):
    def __init__(self) -> None:
        super().__init__('a new branch needs a name')


class DetachedHeadError(StateError):
    def __init__(self) -> None:
        super().__init__('HEAD is detached, so there is no current branch; ask for a branch name')


class MissingTicketError(StateError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} does not exist; run write first')
        self.path = path


class InvalidTicketError(StateError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__('ticket.yml is invalid:\n  ' + '\n  '.join(problems))
        self.problems = problems


def as_mapping(node: Node) -> Tree:
    return node if isinstance(node, dict) else {}


def as_list(node: Node) -> list[Node]:
    return node if isinstance(node, list) else []


def failed_messages(checks: Iterable[Check]) -> list[str]:
    return [message for passed, message in checks if not passed]


def top_level_problems(tree: Tree, slug: Slug) -> list[str]:
    unknown = sorted(set(tree) - TOP_LEVEL_KEYS)
    context = tree.get(CONTEXT_KEY)
    return failed_messages(
        (
            (not unknown, f'unknown top-level keys {unknown}; no consumer reads them'),
            (tree.get('task') == slug.root, f'task must be {slug.root!r}'),
            (bool(tree.get('summary')), 'summary is empty'),
            (
                isinstance(context, list) and 1 <= len(context) <= CONTEXT_LIMIT,
                f'context must be a list of 1 to {CONTEXT_LIMIT} lines',
            ),
        )
    )


def changed_fixed_workers(models: Tree) -> list[str]:
    return [
        f'{worker.value} runs on {fixed_model(worker)}'
        for worker in sorted(FIXED_WORKERS)
        if models.get(worker.value) not in (None, '', fixed_model(worker).value)
    ]


def model_problems(models: Tree) -> list[str]:
    unknown = sorted(set(models) - KNOWN_WORKERS)
    missing = sorted(IMPLEMENTERS - {worker for worker, model in models.items() if model})
    changed = changed_fixed_workers(models)
    return failed_messages(
        (
            (not unknown, f'subagent-models has unknown workers {unknown}'),
            (not missing, f'subagent-models needs a model for {missing}'),
            (not changed, f'subagent-models cannot change a fixed worker: {changed}'),
        )
    )


def handoff_problems(handoff: Tree) -> list[str]:
    unknown = sorted(set(handoff) - HANDOFF_KEYS)
    scopes = sorted(scope.value for scope in Scope)
    return failed_messages(
        (
            (not unknown, f'handoff-context has unknown keys {unknown}'),
            (handoff.get('scope') in scopes, f'scope must be one of {scopes}'),
            (isinstance(handoff.get('plan-first'), bool), 'plan-first must be a bool'),
            (
                isinstance(handoff.get(AUTO_ESCALATE_KEY, False), bool),
                f'{AUTO_ESCALATE_KEY} must be a bool',
            ),
            (bool(handoff.get('branch-name')), 'branch-name is empty'),
        )
    )


def companion_problems(companions: Tree) -> list[str]:
    unknown = sorted(set(companions) - COMPANION_KEYS)
    issue = companions.get('issue-number')
    return failed_messages(
        (
            (not unknown, f'companion-docs has unknown keys {unknown}'),
            (issue is None or isinstance(issue, int), 'issue-number must be a number'),
        )
    )


def linked_slugs(tree: Tree) -> list[Slug]:
    parsed = map(parsed_slug, declared_investigations(tree))
    return [slug for slug in parsed if isinstance(slug, Slug)]


def investigation_problem(investigation: Node, unrecorded: Collection[Slug]) -> str | None:
    slug = parsed_slug(str(investigation))
    if isinstance(slug, InvalidSlugError):
        return f'investigation {investigation} is not a valid id'
    if slug in unrecorded:
        return f'investigation {investigation} has no ledger'
    return None


def investigation_problems(tree: Tree, unrecorded: Collection[Slug]) -> list[str]:
    investigations = tree.get('investigations') or []
    if not isinstance(investigations, list):
        return ['investigations must be a list']
    problems = (
        investigation_problem(investigation, unrecorded) for investigation in investigations
    )
    return [problem for problem in problems if problem is not None]


def ticket_error(tree: Tree, slug: Slug, unrecorded: Collection[Slug]) -> InvalidTicketError | None:
    problems = [
        *top_level_problems(tree, slug),
        *model_problems(as_mapping(tree.get('subagent-models'))),
        *handoff_problems(as_mapping(tree.get('handoff-context'))),
        *companion_problems(as_mapping(tree.get('companion-docs'))),
        *investigation_problems(tree, unrecorded),
    ]
    return InvalidTicketError(problems) if problems else None


def section_of(tree: Tree, *, ticket: str, validated_at: str) -> TicketSection:
    handoff = as_mapping(tree.get('handoff-context'))
    companions = as_mapping(tree.get('companion-docs'))
    fields = {
        'ticket': ticket,
        'summary': tree.get('summary'),
        'branch': handoff.get('branch-name'),
        'scope': handoff.get('scope'),
        'plan_first': handoff.get('plan-first'),
        'auto_escalate': handoff.get(AUTO_ESCALATE_KEY, False),
        'models': as_mapping(tree.get('subagent-models')),
        'tracker': {'issue': companions.get('issue-number'), 'jira': companions.get('jira-key')},
        'context': as_list(tree.get(CONTEXT_KEY)),
        'validated_at': validated_at,
    }
    try:
        return TicketSection.model_validate(fields)
    except ValidationError as error:
        problems = [
            f'{".".join(map(str, detail["loc"]))}: {detail["msg"]}' for detail in error.errors()
        ]
        raise InvalidTicketError(problems) from error


def declared_investigations(tree: Tree) -> list[str]:
    return [str(investigation) for investigation in as_list(tree.get('investigations'))]


def staged_text(unit: WorkUnit) -> str:
    return f'staged {unit.slug} (status {unit.status}, {len(unit.investigations)} investigations)\n'


def staged_unit(tickets: TicketRepository, tree: Tree, *, slug: Slug, ticket: str) -> WorkUnit:
    unrecorded = tickets.unrecorded_investigations(linked_slugs(tree))
    if (error := ticket_error(tree, slug, unrecorded)) is not None:
        raise error
    section = section_of(tree, ticket=ticket, validated_at=now())
    return tickets.stage(slug, section, declared_investigations(tree))


def atomic_write(path: Path, text: str, *, temporary: Path) -> None:
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketService:
    workspace: Workspace
    store: TicketStore
    git: GitQueries

    def unrecorded_investigations(self, linked: Sequence[Slug]) -> list[Slug]:
        if not linked:
            return []
        with self.store.transaction() as repository:
            return repository.unrecorded_investigations(linked)

    def branch_named(self, choice: BranchChoice, name: str) -> str:
        if choice is BranchChoice.NEW:
            if not name.strip():
                raise BranchNameRequiredError
            return name.strip()
        if (current := self.git.current_branch()) is None:
            raise DetachedHeadError
        return current

    def write(self, slug: Slug, answers: TicketAnswers) -> TicketView:
        path = self.workspace.ticket_file(slug)
        if path.exists():
            raise TicketExistsError(path)
        text = ticket_text(slug, answers, triaged_at=now())
        tree = parse(text)
        unrecorded = self.unrecorded_investigations(linked_slugs(tree))
        if (error := ticket_error(tree, slug, unrecorded)) is not None:
            raise error
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, text, temporary=self.workspace.ticket_draft(slug))
        relative = self.workspace.relative_to_root(path)
        return TicketView(text=f'wrote {relative}; review it, then run validate\n')

    def validate(self, slug: Slug) -> TicketView:
        path = self.workspace.ticket_file(slug)
        if not path.is_file():
            raise MissingTicketError(path)
        tree = parse(path.read_text(encoding='utf-8'))
        ticket = self.workspace.relative_to_root(path)
        with self.store.transaction() as repository:
            unit = staged_unit(repository, tree, slug=slug, ticket=ticket)
        return TicketView(text=f'valid; {staged_text(unit)}', unit=unit)

    def show(self, slug: Slug) -> TicketView:
        with self.store.transaction() as repository:
            unit = repository.staged_ticket(slug)
        return TicketView(text=staged_text(unit), unit=unit)

    def update_context(self, slug: Slug, change: TicketContext) -> TicketView:
        path = self.workspace.ticket_file(slug)
        if not path.is_file():
            raise MissingTicketError(path)
        text = with_context(path.read_text(encoding='utf-8'), change.context)
        tree = parse(text)
        ticket = self.workspace.relative_to_root(path)
        with self.store.transaction() as repository:
            unit = staged_unit(repository, tree, slug=slug, ticket=ticket)
            atomic_write(path, text, temporary=self.workspace.ticket_draft(slug))
        return TicketView(text=f'context updated; {staged_text(unit)}', unit=unit)
