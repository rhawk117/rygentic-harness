"""The statistics are load-bearing, so they are checked against known values."""

from __future__ import annotations

import unittest

from skilleng.stats import (cohens_kappa, mcnemar_exact, mde_paired, mde_proportion,
                            n_for_mde, paired_bootstrap, wilson)


class Wilson(unittest.TestCase):
    def test_matches_published_values(self):
        i = wilson(7, 8)
        self.assertAlmostEqual(i.point, 0.875)
        self.assertAlmostEqual(i.low, 0.529, places=2)
        self.assertAlmostEqual(i.high, 0.978, places=2)

    def test_small_n_interval_is_wide_enough_to_be_honest(self):
        self.assertGreater(wilson(7, 8).high - wilson(7, 8).low, 0.4,
                           "a 7/8 result cannot be reported as a precise number")

    def test_degenerate_inputs_do_not_explode(self):
        self.assertEqual(wilson(0, 0).n, 0)
        self.assertAlmostEqual(wilson(0, 10).point, 0.0)
        self.assertAlmostEqual(wilson(10, 10).point, 1.0)


class Bootstrap(unittest.TestCase):
    def test_is_deterministic_for_a_given_seed(self):
        d = [0.2, 0.4, 0.1, 0.5, 0.3]
        self.assertEqual(paired_bootstrap(d).low, paired_bootstrap(d).low)

    def test_interval_brackets_the_point_estimate(self):
        i = paired_bootstrap([0.2, 0.4, 0.1, 0.5, 0.3])
        self.assertLess(i.low, i.point)
        self.assertGreater(i.high, i.point)

    def test_single_observation_yields_no_interval(self):
        self.assertIn("undefined", paired_bootstrap([0.4]).method)


class McNemar(unittest.TestCase):
    def test_no_discordance_is_p_one(self):
        self.assertEqual(mcnemar_exact(0, 0), 1.0)

    def test_symmetric_discordance_is_not_significant(self):
        self.assertEqual(mcnemar_exact(3, 3), 1.0)

    def test_lopsided_discordance_lowers_p(self):
        self.assertLess(mcnemar_exact(10, 0), 0.01)

    def test_typical_small_sample_is_not_significant(self):
        self.assertGreater(mcnemar_exact(6, 1), 0.05,
                           "6-vs-1 on a 20-query set is not evidence, however tempting")


class DetectableEffect(unittest.TestCase):
    def test_more_samples_detect_smaller_effects(self):
        self.assertGreater(mde_paired(5, 0.25), mde_paired(50, 0.25))

    def test_twenty_query_trigger_eval_is_coarse(self):
        self.assertGreater(mde_proportion(20), 0.3,
                           "a 20-query trigger eval cannot resolve small differences and must say so")

    def test_n_for_mde_inverts_mde_paired(self):
        n = n_for_mde(0.10, 0.25)
        self.assertLessEqual(mde_paired(n, 0.25), 0.10 + 1e-9)


class Kappa(unittest.TestCase):
    def test_perfect_agreement(self):
        self.assertAlmostEqual(cohens_kappa([True, False, True], [True, False, True]), 1.0)

    def test_disagreement_lowers_kappa(self):
        self.assertLess(cohens_kappa([True, True, False, False], [True, False, True, False]), 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
