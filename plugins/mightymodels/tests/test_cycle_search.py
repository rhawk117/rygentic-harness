"""The cycles `tarjan_sccs` finds in named graphs, and the order it lists them in."""

import pytest
from mightymodels_plugin.review_metrics.components import tarjan_sccs
from mightymodels_plugin.review_metrics.shapes import Graph


class TestTarjanSccs:
    @pytest.mark.parametrize(
        ('graph', 'cycles'),
        [
            pytest.param({'a': set(), 'b': set(), 'c': set()}, [], id='no-edges'),
            pytest.param({'a': {'b'}, 'b': {'c'}, 'c': set()}, [], id='chain-without-a-cycle'),
            pytest.param({'a': {'a'}, 'b': {'a'}}, [], id='self-loop'),
            pytest.param({'a': {'b'}, 'b': {'a'}, 'c': {'a'}}, [['a', 'b']], id='two-node-cycle'),
            pytest.param(
                {'d': {'c'}, 'c': {'d'}, 'b': {'a'}, 'a': {'b'}},
                [['a', 'b'], ['c', 'd']],
                id='two-disjoint-cycles',
            ),
            pytest.param(
                {'a': {'b'}, 'b': {'a', 'x'}, 'x': {'y'}, 'y': {'z'}, 'z': {'x'}},
                [['x', 'y', 'z'], ['a', 'b']],
                id='cycle-reached-from-another-cycle',
            ),
            pytest.param(
                {'a': {'b', 'gone'}, 'b': {'a'}}, [['a', 'b']], id='target-that-is-not-a-key'
            ),
        ],
    )
    def test_the_cycles_and_their_order_are_those_the_script_reported(
        self, graph: Graph, cycles: list[list[str]]
    ) -> None:
        assert tarjan_sccs(graph) == cycles
