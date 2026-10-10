import random
from collections.abc import Sequence


def seeded_rng(seed: int, label: str) -> random.Random:
    return random.Random(f'{seed}:{label}')  # noqa: S311  # reproducible shuffling, not security


def shuffled[T](items: Sequence[T], rng: random.Random) -> tuple[T, ...]:
    pool = list(items)
    rng.shuffle(pool)
    return tuple(pool)
