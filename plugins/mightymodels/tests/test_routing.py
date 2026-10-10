from typing import TYPE_CHECKING

import pytest
from mightymodels_plugin.core.routing import (
    EFFORT,
    FIXED_WORKERS,
    OVERRIDE_MODEL,
    REVIEWER_WORKERS,
    ROUTING,
    Depth,
    Model,
    Scope,
    Worker,
    models_at,
    reviewer_model,
)
from mightymodels_plugin.tools.ticket.service import model_problems

if TYPE_CHECKING:
    from mightymodels_plugin.tools.ticket.ticket_file import Tree


class TestRoutingTable:
    EVERY_SCOPE = (Scope.SM, Scope.MED, Scope.LARGE)

    @pytest.mark.parametrize(
        ('worker', 'models'),
        [
            pytest.param('code-scout', ('haiku', 'haiku', 'haiku'), id='code-scout'),
            pytest.param('web-scout', ('haiku', 'haiku', 'haiku'), id='web-scout'),
            pytest.param('qualitylens', ('haiku', 'haiku', 'haiku'), id='qualitylens'),
            pytest.param('gitty-up', ('haiku', 'haiku', 'haiku'), id='gitty-up'),
            pytest.param('engineer', ('sonnet', 'sonnet', 'sonnet'), id='engineer'),
            pytest.param('architect', ('opus', 'opus', 'opus'), id='architect'),
            pytest.param('uncle-bob-reviewer', ('opus', 'opus', 'opus'), id='uncle-bob'),
            pytest.param('merge-vader-reviewer', ('opus', 'opus', 'opus'), id='merge-vader'),
            pytest.param('wingman', ('fable', 'fable', 'fable'), id='wingman'),
        ],
    )
    def test_routing_table_maps_each_worker_and_scope_to_its_model_alias(
        self, worker: str, models: tuple[str, str, str]
    ) -> None:
        by_scope = ROUTING[Worker(worker)]

        assert tuple(by_scope[scope] for scope in self.EVERY_SCOPE) == models

    def test_routes_every_worker_at_every_scope(self) -> None:
        assert set(ROUTING) == set(Worker)
        assert all(set(by_scope) == set(Scope) for by_scope in ROUTING.values())

    def test_knows_only_the_four_aliases(self) -> None:
        assert [model.value for model in Model] == ['haiku', 'sonnet', 'opus', 'fable']

    def test_models_at_a_scope_reads_the_one_table(self) -> None:
        assert models_at(Scope.LARGE) == {
            worker: by_scope[Scope.LARGE] for worker, by_scope in ROUTING.items()
        }


class TestFixedWorkers:
    @pytest.mark.parametrize(
        ('worker', 'other'),
        [
            pytest.param(Worker.CODE_SCOUT, 'sonnet', id='code-scout'),
            pytest.param(Worker.WEB_SCOUT, 'opus', id='web-scout'),
            pytest.param(Worker.QUALITYLENS, 'sonnet', id='qualitylens'),
            pytest.param(Worker.ENGINEER, 'opus', id='engineer'),
            pytest.param(Worker.ARCHITECT, 'sonnet', id='architect'),
            pytest.param(Worker.GITTY_UP, 'fable', id='gitty-up'),
            pytest.param(Worker.WINGMAN, 'opus', id='wingman'),
        ],
    )
    def test_a_ticket_value_that_differs_from_the_fixed_model_is_refused(
        self, worker: Worker, other: str
    ) -> None:
        models: Tree = {'engineer': 'sonnet', 'architect': 'opus', worker.value: other}

        problems = model_problems(models)

        assert [problem for problem in problems if 'fixed worker' in problem] != []

    @pytest.mark.parametrize(
        ('worker', 'fixed'),
        [
            pytest.param(Worker.CODE_SCOUT, 'haiku', id='code-scout'),
            pytest.param(Worker.WEB_SCOUT, 'haiku', id='web-scout'),
            pytest.param(Worker.QUALITYLENS, 'haiku', id='qualitylens'),
            pytest.param(Worker.ENGINEER, 'sonnet', id='engineer'),
            pytest.param(Worker.ARCHITECT, 'opus', id='architect'),
            pytest.param(Worker.GITTY_UP, 'haiku', id='gitty-up'),
            pytest.param(Worker.WINGMAN, 'fable', id='wingman'),
        ],
    )
    def test_a_ticket_value_equal_to_the_fixed_model_is_accepted(
        self, worker: Worker, fixed: str
    ) -> None:
        models: Tree = {'engineer': 'sonnet', 'architect': 'opus', worker.value: fixed}

        assert model_problems(models) == []

    def test_fixes_the_seven_workers_a_ticket_cannot_move(self) -> None:
        assert {worker.value for worker in FIXED_WORKERS} == {
            'code-scout',
            'web-scout',
            'qualitylens',
            'engineer',
            'architect',
            'gitty-up',
            'wingman',
        }

    @pytest.mark.parametrize('worker', sorted(REVIEWER_WORKERS))
    def test_a_ticket_value_for_a_reviewer_is_accepted_and_ignored(self, worker: Worker) -> None:
        models: Tree = {'engineer': 'sonnet', 'architect': 'opus', worker.value: 'haiku'}

        assert model_problems(models) == []


class TestEffortPins:
    @pytest.mark.parametrize(
        ('model', 'effort'),
        [
            pytest.param(Model.HAIKU, 'high', id='haiku'),
            pytest.param(Model.SONNET, 'medium', id='sonnet'),
            pytest.param(Model.OPUS, 'medium', id='opus'),
            pytest.param(Model.FABLE, 'high', id='fable'),
        ],
    )
    def test_pins_one_effort_per_model(self, model: Model, effort: str) -> None:
        assert EFFORT[model] == effort


class TestReviewerModels:
    @pytest.mark.parametrize(
        ('depth', 'model'),
        [
            pytest.param(Depth.QUICK, 'sonnet', id='quick'),
            pytest.param(Depth.STANDARD, 'opus', id='standard'),
            pytest.param(Depth.DEEP, 'opus', id='deep'),
        ],
    )
    def test_reviewer_models_follow_the_depth(self, depth: Depth, model: str) -> None:
        assert reviewer_model(depth) == model

    def test_the_one_override_moves_a_reviewer_to_fable(self) -> None:
        assert OVERRIDE_MODEL == Model.FABLE
