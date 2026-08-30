"""Statistics, with the tier deciding what may be claimed.

Standard library only — no numpy, no scipy. A harness people cannot install is a
harness people do not run, and an unrun harness measures nothing.

What this module refuses to do is as important as what it does: at `quick` tier it
will not produce an interval, because printing `± 0.06` off n=3 (skill-creator's
default output) is worse than printing nothing.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import NormalDist, fmean, stdev

_ND = NormalDist()


@dataclass
class Interval:
    point: float
    low: float
    high: float
    method: str
    n: int

    def fmt(self, pct: bool = False, digits: int = 2) -> str:
        f = (lambda v: f'{v * 100:.0f}%') if pct else (lambda v: f'{v:+.{digits}f}')
        return f'{f(self.point)} [{f(self.low)}, {f(self.high)}]'


def wilson(successes: int, n: int, confidence: float = 0.95) -> Interval:
    """Wilson score interval for a proportion. Correct at small n, where the
    normal approximation is not — which is the only n this harness ever has."""
    if n <= 0:
        return Interval(0.0, 0.0, 1.0, 'wilson', 0)
    z = _ND.inv_cdf(1 - (1 - confidence) / 2)
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return Interval(p, max(0.0, centre - half), min(1.0, centre + half), 'wilson', n)


def paired_bootstrap(
    deltas: list[float],
    confidence: float = 0.95,
    iterations: int = 5000,
    seed: int = 20260827,
) -> Interval:
    """Percentile bootstrap over per-eval paired deltas.

    Pairing is the whole point: the same prompt is run in both arms, so the natural
    unit is the delta per eval. skill-creator pools every run from every eval into one
    mean ± stddev, which throws the pairing away and conflates between-eval variance
    with between-run variance."""
    n = len(deltas)
    if n == 0:
        return Interval(0.0, 0.0, 0.0, 'bootstrap', 0)
    point = fmean(deltas)
    if n == 1:
        return Interval(
            point, float('-inf'), float('inf'), 'bootstrap(n=1, undefined)', 1
        )
    rng = random.Random(seed)  # noqa: S311 — statistical resampling, not cryptographic
    means = sorted(fmean(rng.choices(deltas, k=n)) for _ in range(iterations))
    lo = means[int((1 - confidence) / 2 * iterations)]
    hi = means[min(iterations - 1, int((1 + confidence) / 2 * iterations))]
    return Interval(point, lo, hi, f'bootstrap({iterations})', n)


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value on discordant pairs.

    The right test for "does description B trigger differently from A on the same
    queries", because the queries are shared and the outcomes are paired."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def mde_paired(n_pairs: int, sd: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest paired difference detectable at this n. Printed *before* spending."""
    if n_pairs < 2 or sd <= 0:
        return float('inf')
    z = _ND.inv_cdf(1 - alpha / 2) + _ND.inv_cdf(power)
    return z * sd / math.sqrt(n_pairs)


def mde_proportion(
    n: int, p: float = 0.5, alpha: float = 0.05, power: float = 0.8
) -> float:
    """Smallest detectable difference between two proportions at this n per arm."""
    if n < 2:
        return float('inf')
    z = _ND.inv_cdf(1 - alpha / 2) + _ND.inv_cdf(power)
    return z * math.sqrt(2 * p * (1 - p) / n)


def n_for_mde(target: float, sd: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Invert mde_paired: how many pairs to resolve a difference this size."""
    if target <= 0 or sd <= 0:
        return 0
    z = _ND.inv_cdf(1 - alpha / 2) + _ND.inv_cdf(power)
    return max(2, math.ceil((z * sd / target) ** 2))


def cohens_kappa(a: list[bool], b: list[bool]) -> float:
    """Grader agreement. If the ruler is inconsistent, the score has a noise floor
    and the user should be told what it is."""
    n = len(a)
    if n == 0 or n != len(b):
        return float('nan')
    obs = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    exp = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if exp >= 1.0 else (obs - exp) / (1 - exp)


def spread(values: list[float]) -> float:
    return stdev(values) if len(values) > 1 else 0.0
