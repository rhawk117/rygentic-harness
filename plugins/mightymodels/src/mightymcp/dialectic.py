from pydantic import BaseModel, Field

from mightymcp.artifacts import cap_refusals, missing_refusals, ticket_directory
from mightymcp.paths import TicketPathError, safe_name
from mightymcp.routing import CRITICAL, HIGH, SEVERITIES

NO_FINDING = 'none'
# best last: an option nothing was found against wins rung 1
WORST_FOUND = (*SEVERITIES, NO_FINDING)
CHEAP = 'cheap'
EXPENSIVE = 'expensive'
REVERSAL_COSTS = (CHEAP, EXPENSIVE)
MIN_OPTIONS = 2
MAX_OPTIONS = 3
RUNGS = {
    1: 'found defects',
    2: 'reversal cost',
    3: 'conformance',
    4: 'surface',
    5: 'spike',
    6: 'coin flip',
}
SPIKE_RUNG = 5
COIN_FLIP_RUNG = 6
RECORD_CAP = 40


class DialecticOption(BaseModel):
    """One branch of the fork, scored the way the ladder reads it."""

    name: str = Field(description='The option, as the user listed it')
    worst: str = Field(
        default=NO_FINDING, description=f'Worst severity found: {", ".join(WORST_FOUND)}'
    )
    reversal_cost: str = Field(
        default=EXPENSIVE, description=f'{CHEAP} or {EXPENSIVE} to undo'
    )
    conforms: bool = Field(
        default=False, description='True when it does what the repository already does'
    )
    surface: int = Field(
        default=0, description='Files, interfaces, and dependencies it touches'
    )
    spike: str = Field(
        default='', description='The bounded experiment that would separate the options'
    )


class DialecticDecision(BaseModel):
    """Which option the ladder picked, and the rung that picked it."""

    winner: str | None = Field(
        default=None, description='The option that won, or null when a spike is owed'
    )
    rung: int | None = Field(default=None, description='The rung that decided, 1-6')
    rung_name: str = Field(default='', description="That rung's name")
    rule: str = Field(default='', description='The evidence the rung decided on')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was decided'
    )


class DialecticRecord(BaseModel):
    """The seven lines the decision record carries, per the dialectic skill."""

    fork: str = Field(description='The fork, in one line')
    options: list[str] = Field(description='Each option with its reversal cost')
    worst_found: list[str] = Field(description='Worst severity and location per option')
    decided_by: str = Field(description='rung <n> (<name>), or user on an override')
    decision: str = Field(description='The option chosen, and the rung evidence')
    reopen_if: str = Field(description='The signal that sends this back to rung 1')
    unexamined: str = Field(description='What neither worker covered')


class DialecticWrite(BaseModel):
    """The decision record as written, or why nothing was written."""

    path: str | None = Field(default=None, description='Absolute path of the record')
    text: str = Field(default='', description='The record as written')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was written'
    )


def dialectic_score(options: list[DialecticOption]) -> DialecticDecision:
    """Walk the tie-break ladder and stop at the first rung that separates them."""
    refusals = _option_refusals(options)
    if refusals:
        return DialecticDecision(refusals=refusals)

    for rung, climb in ((1, _defects), (2, _reversal), (3, _conformance), (4, _surface)):
        decided = climb(options)
        if decided is not None:
            winner, rule = decided
            return DialecticDecision(
                winner=winner, rung=rung, rung_name=RUNGS[rung], rule=rule
            )
    spike = next((option.spike for option in options if option.spike), '')
    if spike:
        return DialecticDecision(
            rung=SPIKE_RUNG,
            rung_name=RUNGS[SPIKE_RUNG],
            rule=f'{spike} would separate them; run it and score again from rung 1',
        )
    return DialecticDecision(
        winner=options[0].name,
        rung=COIN_FLIP_RUNG,
        rung_name=RUNGS[COIN_FLIP_RUNG],
        rule='equivalent by every measure; the option the user listed first',
    )


def dialectic_record_write(
    slug: str, fork_slug: str, record: DialecticRecord
) -> DialecticWrite:
    """Write the fork's decision record into the ticket directory."""
    directory, refusals = ticket_directory(slug)
    name = ''
    try:
        name = safe_name(fork_slug)
    except TicketPathError as err:
        refusals.append(str(err))
    refusals.extend(
        missing_refusals({
            'fork': record.fork,
            'decided-by': record.decided_by,
            'decision': record.decision,
            'reopen-if': record.reopen_if,
            'unexamined': record.unexamined,
        })
    )
    if not record.options:
        refusals.append('options is empty; a record names what it chose between')
    text = _render(record)
    refusals.extend(cap_refusals('the decision record', text, RECORD_CAP))
    if directory is None or refusals:
        return DialecticWrite(refusals=refusals)

    path = directory.joinpath(f'dialectic-{name}.md')
    path.write_text(text, encoding='utf-8')
    return DialecticWrite(path=str(path), text=text)


def _render(record: DialecticRecord) -> str:
    lines = (
        f'# {record.fork}',
        '',
        f'Options: {" | ".join(record.options)}',
        f'Worst found: {" | ".join(record.worst_found)}',
        f'Decided by: {record.decided_by}',
        f'Decision: {record.decision}',
        f'Reopen if: {record.reopen_if}',
        f'Unexamined: {record.unexamined}',
    )
    return '\n'.join(lines) + '\n'


def _defects(options: list[DialecticOption]) -> tuple[str, str] | None:
    """Rung 1: the option with the least damaging worst finding, when it is alone."""
    best, *rest = sorted(
        options, key=lambda option: WORST_FOUND.index(option.worst), reverse=True
    )
    if best.worst == rest[0].worst:
        return None
    risky = [option.name for option in rest if option.worst in (CRITICAL, HIGH)]
    if risky and best.worst not in (CRITICAL, HIGH):
        return (
            best.name,
            f'{CRITICAL} or {HIGH} against {", ".join(risky)}, not {best.name}',
        )
    return best.name, (
        f'{best.name} is worst at {best.worst}, a level better than '
        f'{rest[0].name} at {rest[0].worst}'
    )


def _reversal(options: list[DialecticOption]) -> tuple[str, str] | None:
    """Rung 2: being wrong cheaply is a fix, being wrong expensively is a rewrite."""
    best, *rest = sorted(
        options, key=lambda option: REVERSAL_COSTS.index(option.reversal_cost)
    )
    if best.reversal_cost == rest[0].reversal_cost:
        return None
    return best.name, f'{best.name} is {best.reversal_cost} to undo; the others are not'


def _conformance(options: list[DialecticOption]) -> tuple[str, str] | None:
    """Rung 3: two ways to do one thing cost more than either option's author pays."""
    conforming = [option.name for option in options if option.conforms]
    if len(conforming) != 1:
        return None
    return conforming[0], f'{conforming[0]} does what the repository already does'


def _surface(options: list[DialecticOption]) -> tuple[str, str] | None:
    """Rung 4: the option touching fewer files, interfaces, and dependencies."""
    best, *rest = sorted(options, key=lambda option: option.surface)
    if best.surface == rest[0].surface:
        return None
    return best.name, (
        f'{best.name} touches {best.surface}, fewer than {rest[0].name} '
        f'at {rest[0].surface}'
    )


def _option_refusals(options: list[DialecticOption]) -> list[str]:
    if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
        return [
            (
                f'{len(options)} options; a fork has {MIN_OPTIONS} or {MAX_OPTIONS}, '
                'and a wider one is a design problem for cross-examine'
            )
        ]
    refusals = [
        f'{option.name!r} is worst at {option.worst!r}; expected {", ".join(WORST_FOUND)}'
        for option in options
        if option.worst not in WORST_FOUND
    ]
    refusals.extend(
        f'{option.name!r} reverses {option.reversal_cost!r}; expected '
        f'{", ".join(REVERSAL_COSTS)}'
        for option in options
        if option.reversal_cost not in REVERSAL_COSTS
    )
    if len({option.name for option in options}) != len(options):
        refusals.append('two options carry the same name; the record could not name one')
    return refusals
