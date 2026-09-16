import pytest
from mightymcp.routing import (
    DEFAULT_MODELS,
    choose_model,
    default_models,
    engineer_model,
    route_finding,
    route_ramp,
)

RAMP_ROWS = [
    ('sm', False, 'yolo', 'scope sm with plan-first false'),
    ('sm', True, 'game-plan', 'plan-first true'),
    ('med', True, 'game-plan', 'plan-first true'),
    ('large', True, 'game-plan', 'plan-first true'),
    ('med', False, 'game-plan', 'scope med is not sm'),
    ('large', False, 'game-plan', 'scope large is not sm'),
]
CRITICAL_ROWS = [
    (severity, security, source, 'engineer', rule)
    for severity, security, rule in [
        ('Critical', False, 'Critical finding'),
        ('Critical', True, 'Critical finding'),
        ('High', True, 'security finding at High or above'),
    ]
    for source in ('uncle-bob', 'merge-vader')
]
SOURCE_ROWS = [
    (severity, security, 'uncle-bob', 'engineer', 'uncle-bob finding below the risk line')
    for severity in ('High', 'Medium', 'Low')
    for security in (False, True)
    if not (severity == 'High' and security)
] + [
    (
        severity,
        security,
        'merge-vader',
        'budgetron',
        'merge-vader finding below the risk line',
    )
    for severity in ('High', 'Medium', 'Low')
    for security in (False, True)
    if not (severity == 'High' and security)
]


@pytest.mark.parametrize('role', sorted(DEFAULT_MODELS))
def test_every_role_has_a_default_model(role: str) -> None:
    choice = choose_model(role, pinned=None, scope=None)

    assert choice.model == DEFAULT_MODELS[role]
    assert choice.source == 'default'
    assert choice.rule == f'default for {role}'


def test_a_pin_wins_over_the_default() -> None:
    choice = choose_model('scout', pinned='claude-opus-5', scope='sm')

    assert choice.model == 'claude-opus-5'
    assert choice.source == 'ticket'
    assert choice.rule == 'ticket pins scout'


@pytest.mark.parametrize(
    'row',
    [('large', 'claude-opus-5'), ('med', 'claude-sonnet-5'), ('sm', 'claude-sonnet-5')],
)
def test_the_engineer_tier_follows_ticket_scope(row: tuple[str, str]) -> None:
    scope, expected = row

    assert engineer_model(scope) == expected
    assert choose_model('engineer', pinned=None, scope=scope).model == expected


def test_the_engineer_tier_without_a_scope_is_sonnet() -> None:
    choice = choose_model('engineer', pinned=None, scope=None)

    assert choice.model == 'claude-sonnet-5'
    assert choice.rule == 'engineer derived from scope unset'


def test_an_unknown_role_is_refused() -> None:
    choice = choose_model('nobody', pinned=None, scope='sm')

    assert choice.model is None
    assert choice.source == 'none'
    assert "unknown role 'nobody'" in choice.refusals[0]


@pytest.mark.parametrize('row', [('large', 'claude-opus-5'), ('sm', 'claude-sonnet-5')])
def test_a_fresh_model_block_carries_every_role(row: tuple[str, str]) -> None:
    scope, engineer = row
    models = default_models(scope)

    assert models['engineer'] == engineer
    assert models['primary-agent'] is None
    assert set(models) == set(DEFAULT_MODELS) | {'engineer'}


@pytest.mark.parametrize('row', RAMP_ROWS, ids=[f'{r[0]}-{r[1]}' for r in RAMP_ROWS])
def test_the_ramp_table(row: tuple[str, bool, str, str]) -> None:
    scope, plan_first, ramp, rule = row
    choice = route_ramp(scope, plan_first=plan_first)

    assert choice.ramp == ramp
    assert choice.rule == rule
    assert choice.refusals == []


def test_an_unknown_scope_has_no_ramp() -> None:
    choice = route_ramp('epic', plan_first=False)

    assert choice.ramp is None
    assert "unknown scope 'epic'" in choice.refusals[0]


@pytest.mark.parametrize(
    'row',
    CRITICAL_ROWS + SOURCE_ROWS,
    ids=[f'{r[0]}-sec{r[1]:d}-{r[2]}' for r in CRITICAL_ROWS + SOURCE_ROWS],
)
def test_the_finding_table(row: tuple[str, bool, str, str, str]) -> None:
    severity, security, source, worker, rule = row
    route = route_finding(severity, source, security=security)

    assert route.worker == worker
    assert route.rule == rule
    assert route.refusals == []


def test_the_finding_table_covers_every_row() -> None:
    assert len(CRITICAL_ROWS + SOURCE_ROWS) == 16


def test_an_unknown_severity_and_source_are_both_refused() -> None:
    route = route_finding('Nasty', 'santa', security=False)

    assert route.worker is None
    assert "unknown severity 'Nasty'" in route.refusals[0]
    assert "unknown source 'santa'" in route.refusals[1]
