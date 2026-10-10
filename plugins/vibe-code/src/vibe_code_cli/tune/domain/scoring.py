from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from statistics import fmean

from vibe_code_cli.tune.domain.values import Split, TriggerExample

type Verdicts = Mapping[str, frozenset[str]]


@dataclass(slots=True, kw_only=True, frozen=True)
class Scorecard:
    train: float
    validation: float


@dataclass(slots=True, kw_only=True, frozen=True)
class SkillFailures:
    skill: str
    missed: tuple[str, ...]
    false_triggers: tuple[str, ...]
    f1: float

    @property
    def count(self) -> int:
        return len(self.missed) + len(self.false_triggers)


def jaccard(expected: frozenset[str], chosen: frozenset[str]) -> float:
    union = expected | chosen
    if not union:
        return 1.0

    return len(expected & chosen) / len(union)


def score_split(examples: Iterable[TriggerExample], verdicts: Verdicts, split: Split) -> float:
    scores = [
        jaccard(example.expected, verdicts[example.request_id])
        for example in examples
        if example.split is split
    ]

    return fmean(scores)


def score_verdicts(examples: tuple[TriggerExample, ...], verdicts: Verdicts) -> Scorecard:
    return Scorecard(
        train=score_split(examples, verdicts, Split.TRAIN),
        validation=score_split(examples, verdicts, Split.VALIDATION),
    )


def f1_score(true_positives: int, false_positives: int, false_negatives: int) -> float:
    denominator = 2 * true_positives + false_positives + false_negatives
    if not denominator:
        return 1.0

    return 2 * true_positives / denominator


def skill_failures(
    examples: tuple[TriggerExample, ...],
    verdicts: Verdicts,
    skill: str,
) -> SkillFailures:
    train = [example for example in examples if example.split is Split.TRAIN]
    expected = [example for example in train if skill in example.expected]
    chosen = [example for example in train if skill in verdicts[example.request_id]]
    missed = tuple(example.request for example in expected if example not in chosen)

    false_triggers = tuple(example.request for example in chosen if example not in expected)
    hits = len(expected) - len(missed)
    f1 = f1_score(hits, len(false_triggers), len(missed))
    return SkillFailures(
        skill=skill,
        missed=missed,
        false_triggers=false_triggers,
        f1=f1,
    )
