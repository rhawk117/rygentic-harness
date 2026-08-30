"""The statistics are load-bearing, so they are checked against known values."""

from __future__ import annotations

import pytest
from skilleng.stats import (
    cohens_kappa,
    mcnemar_exact,
    mde_paired,
    mde_proportion,
    n_for_mde,
    paired_bootstrap,
    wilson,
)


class TestWilson:
    def test_matches_published_values(self) -> None:
        i = wilson(7, 8)
        assert i.point == pytest.approx(0.875)
        assert i.low == pytest.approx(0.529, abs=1e-2)
        assert i.high == pytest.approx(0.978, abs=1e-2)

    def test_small_n_interval_is_wide_enough_to_be_honest(self) -> None:
        assert wilson(7, 8).high - wilson(7, 8).low > 0.4, (
            'a 7/8 result cannot be reported as a precise number'
        )

    def test_degenerate_inputs_do_not_explode(self) -> None:
        assert wilson(0, 0).n == 0
        assert wilson(0, 10).point == pytest.approx(0.0)
        assert wilson(10, 10).point == pytest.approx(1.0)


class TestBootstrap:
    def test_is_deterministic_for_a_given_seed(self) -> None:
        d = [0.2, 0.4, 0.1, 0.5, 0.3]
        assert paired_bootstrap(d).low == paired_bootstrap(d).low

    def test_interval_brackets_the_point_estimate(self) -> None:
        i = paired_bootstrap([0.2, 0.4, 0.1, 0.5, 0.3])
        assert i.low < i.point
        assert i.high > i.point

    def test_single_observation_yields_no_interval(self) -> None:
        assert 'undefined' in paired_bootstrap([0.4]).method


class TestMcNemar:
    def test_no_discordance_is_p_one(self) -> None:
        assert mcnemar_exact(0, 0) == 1.0

    def test_symmetric_discordance_is_not_significant(self) -> None:
        assert mcnemar_exact(3, 3) == 1.0

    def test_lopsided_discordance_lowers_p(self) -> None:
        assert mcnemar_exact(10, 0) < 0.01

    def test_typical_small_sample_is_not_significant(self) -> None:
        assert mcnemar_exact(6, 1) > 0.05, (
            '6-vs-1 on a 20-query set is not evidence, however tempting'
        )


class TestDetectableEffect:
    def test_more_samples_detect_smaller_effects(self) -> None:
        assert mde_paired(5, 0.25) > mde_paired(50, 0.25)

    def test_twenty_query_trigger_eval_is_coarse(self) -> None:
        assert mde_proportion(20) > 0.3, (
            'a 20-query trigger eval cannot resolve small differences and must say so'
        )

    def test_n_for_mde_inverts_mde_paired(self) -> None:
        n = n_for_mde(0.10, 0.25)
        assert mde_paired(n, 0.25) <= 0.10 + 1e-9


class TestKappa:
    def test_perfect_agreement(self) -> None:
        assert cohens_kappa([True, False, True], [True, False, True]) == pytest.approx(
            1.0
        )

    def test_disagreement_lowers_kappa(self) -> None:
        assert cohens_kappa([True, True, False, False], [True, False, True, False]) < 0.5
