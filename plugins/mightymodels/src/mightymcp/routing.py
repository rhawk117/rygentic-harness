from typing import Literal, get_args

from pydantic import BaseModel, Field

HAIKU = 'claude-haiku-4-5'
SONNET = 'claude-sonnet-5'
OPUS = 'claude-opus-5'

# Defaults from using-mightymodels; engineer is derived from ticket scope instead.
PRIMARY = 'primary-agent'
DEFAULT_MODELS = {
    PRIMARY: SONNET,
    'scout': HAIKU,
    'budgetron': SONNET,
    'gitty-up': HAIKU,
    'grumpy': SONNET,
    'sunny': OPUS,
    'wingman': OPUS,
    'merge-vader': OPUS,
    'uncle-bob': OPUS,
}
ENGINEER = 'engineer'
MODEL_ROLES = (*DEFAULT_MODELS, ENGINEER)
LARGE_SCOPE = 'large'
CRITICAL = 'Critical'
HIGH = 'High'
SEVERITIES = (CRITICAL, HIGH, 'Medium', 'Low')
FINDING_SOURCES = ('uncle-bob', 'merge-vader')
Scope = Literal['sm', 'med', 'large']
SCOPES = get_args(Scope)


class ModelChoice(BaseModel):
    """Which model a role runs on, and where that answer came from."""

    role: str = Field(description='The fleet role the model was resolved for')
    model: str | None = Field(
        default=None, description='Resolved model, or null when refused'
    )
    source: Literal['ticket', 'default', 'none'] = Field(
        description='ticket when the ticket pinned it, default from the table, '
        'none when refused'
    )
    rule: str = Field(default='', description='The rule that fired')
    refusals: list[str] = Field(
        default_factory=list, description='Why no model was resolved'
    )


class RampChoice(BaseModel):
    """Which ramp a fresh session runs."""

    ramp: str | None = Field(default=None, description='yolo or game-plan')
    rule: str = Field(default='', description='The rule that fired')
    refusals: list[str] = Field(
        default_factory=list, description='Why no ramp was chosen'
    )


class FindingRoute(BaseModel):
    """Which worker fixes a review finding."""

    worker: str | None = Field(default=None, description='engineer or budgetron')
    rule: str = Field(default='', description='The rule that fired')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was routed'
    )


def default_models(scope: str) -> dict[str, str | None]:
    """The subagent-models block a fresh ticket of this scope is written with."""
    models: dict[str, str | None] = dict(DEFAULT_MODELS)
    # the ticket records the primary as a user hint, so a fresh ticket leaves it empty
    models[PRIMARY] = None
    models[ENGINEER] = engineer_model(scope)
    return models


def engineer_model(scope: str | None) -> str:
    """Derive the engineer tier: large scope is opus, every other scope is sonnet."""
    return OPUS if scope == LARGE_SCOPE else SONNET


def choose_model(role: str, pinned: str | None, scope: str | None) -> ModelChoice:
    """Apply the model table to one role, given the ticket's pin and scope."""
    if pinned:
        return ModelChoice(
            role=role, model=pinned, source='ticket', rule=f'ticket pins {role}'
        )
    if role == ENGINEER:
        return ModelChoice(
            role=role,
            model=engineer_model(scope),
            source='default',
            rule=f'engineer derived from scope {scope or "unset"}',
        )
    default = DEFAULT_MODELS.get(role)
    if default is None:
        return ModelChoice(
            role=role,
            source='none',
            refusals=[f'unknown role {role!r}; known roles are {", ".join(MODEL_ROLES)}'],
        )
    return ModelChoice(
        role=role, model=default, source='default', rule=f'default for {role}'
    )


def route_ramp(scope: str, *, plan_first: bool) -> RampChoice:
    """Pick the ramp for a ticket: yolo only for sm with plan-first false."""
    if scope not in SCOPES:
        return RampChoice(
            refusals=[f'unknown scope {scope!r}; expected {", ".join(SCOPES)}']
        )
    if scope == 'sm' and not plan_first:
        return RampChoice(ramp='yolo', rule='scope sm with plan-first false')
    if plan_first:
        return RampChoice(ramp='game-plan', rule='plan-first true')
    return RampChoice(ramp='game-plan', rule=f'scope {scope} is not sm')


def route_finding(severity: str, source: str, *, security: bool) -> FindingRoute:
    """Route a review finding by risk first, then by the reviewer that found it."""
    refusals = []
    if severity not in SEVERITIES:
        refusals.append(
            f'unknown severity {severity!r}; expected {", ".join(SEVERITIES)}'
        )
    if source not in FINDING_SOURCES:
        refusals.append(
            f'unknown source {source!r}; expected {", ".join(FINDING_SOURCES)}'
        )
    if refusals:
        return FindingRoute(refusals=refusals)
    if severity == CRITICAL:
        return FindingRoute(worker='engineer', rule='Critical finding')
    if security and severity == HIGH:
        return FindingRoute(worker='engineer', rule='security finding at High or above')
    if source == 'uncle-bob':
        return FindingRoute(
            worker='engineer', rule='uncle-bob finding below the risk line'
        )
    return FindingRoute(
        worker='budgetron', rule='merge-vader finding below the risk line'
    )
