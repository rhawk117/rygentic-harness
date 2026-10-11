"""Expected alert load, precision and cost of a detector at one prevalence, as YAML."""

import argparse
import logging
import sys
from dataclasses import dataclass
from math import isfinite

import msgspec

SCHEMA_VERSION = 2
CONTRACT_VIOLATION = 2
TRANSFER_ASSUMPTION = 'recall and false positive rate transfer to this population'
PERIOD_ASSUMPTION = 'events are counted over the same period as the review budget'

logger = logging.getLogger('alert_budget')

type ArgumentValue = str | int | float | bool | tuple[str, ...] | None


class Report[ResultT](msgspec.Struct, frozen=True, kw_only=True):
    schema_version: int
    command: str
    arguments: dict[str, ArgumentValue]
    result: ResultT
    caveats: tuple[str, ...]


class RateOutOfRangeError(ValueError):
    def __init__(self, name: str, value: float) -> None:
        super().__init__(f'{name} must be a probability in [0, 1], got {value}')


class NonPositiveEventsError(ValueError):
    def __init__(self, events: int) -> None:
        super().__init__(f'events must be positive, got {events}')


class UnpairedCostError(ValueError):
    def __init__(self) -> None:
        super().__init__('give both --cost-fn and --cost-fp, or neither')


@dataclass(frozen=True, slots=True, kw_only=True)
class DetectorScenario:
    events: int
    prevalence: float
    recall: float
    false_positive_rate: float
    review_budget: float | None = None
    cost_false_negative: float | None = None
    cost_false_positive: float | None = None

    @property
    def positives(self) -> float:
        return self.events * self.prevalence

    @property
    def negatives(self) -> float:
        return self.events * (1 - self.prevalence)

    @property
    def rates(self) -> tuple[tuple[str, float], ...]:
        return (
            ('prevalence', self.prevalence),
            ('recall', self.recall),
            ('false_positive_rate', self.false_positive_rate),
        )

    @property
    def has_costs(self) -> bool:
        return self.cost_false_negative is not None and self.cost_false_positive is not None


class ExpectedCounts(msgspec.Struct, frozen=True, kw_only=True):
    positives: float
    true_alerts: float
    false_alerts: float
    alerts: float
    missed_positives: float


class BudgetFit(msgspec.Struct, frozen=True, kw_only=True):
    review_budget: float
    alerts_over_budget: float
    fits: bool
    max_true_alerts_within_budget: float


class ExpectedCost(msgspec.Struct, frozen=True, kw_only=True):
    per_event: float
    total: float


class AlertLoad(msgspec.Struct, frozen=True, kw_only=True, omit_defaults=True):
    expected: ExpectedCounts
    precision: float | None
    accuracy_of_always_negative: float
    budget: BudgetFit | None = None
    cost: ExpectedCost | None = None


def normalize_argument(value: object) -> ArgumentValue:
    match value:
        case str() | int() | float() | bool() | None:
            return value
        case list() | tuple():
            return tuple(map(str, value))
        case _:
            return str(value)


def describe_arguments(arguments: argparse.Namespace) -> dict[str, ArgumentValue]:
    return {
        name: normalize_argument(value)
        for name, value in vars(arguments).items()
        if not callable(value)
    }


def find_rate_violation(name: str, value: float) -> ValueError | None:
    return None if isfinite(value) and 0 <= value <= 1 else RateOutOfRangeError(name, value)


def find_scenario_violation(scenario: DetectorScenario) -> ValueError | None:
    if scenario.events <= 0:
        return NonPositiveEventsError(scenario.events)
    rate_problems = (find_rate_violation(name, value) for name, value in scenario.rates)
    if problem := next(filter(None, rate_problems), None):
        return problem
    has_one_cost = (scenario.cost_false_negative is None) != (scenario.cost_false_positive is None)
    return UnpairedCostError() if has_one_cost else None


def expected_counts(scenario: DetectorScenario) -> ExpectedCounts:
    true_alerts = scenario.positives * scenario.recall
    false_alerts = scenario.negatives * scenario.false_positive_rate
    return ExpectedCounts(
        positives=scenario.positives,
        true_alerts=true_alerts,
        false_alerts=false_alerts,
        alerts=true_alerts + false_alerts,
        missed_positives=scenario.positives - true_alerts,
    )


def fit_budget(scenario: DetectorScenario, counts: ExpectedCounts) -> BudgetFit | None:
    if scenario.review_budget is None:
        return None
    return BudgetFit(
        review_budget=scenario.review_budget,
        alerts_over_budget=max(0.0, counts.alerts - scenario.review_budget),
        fits=counts.alerts <= scenario.review_budget,
        max_true_alerts_within_budget=min(counts.positives, scenario.review_budget),
    )


def expected_cost(scenario: DetectorScenario, counts: ExpectedCounts) -> ExpectedCost | None:
    if scenario.cost_false_negative is None or scenario.cost_false_positive is None:
        return None
    total = (
        scenario.cost_false_negative * counts.missed_positives
        + scenario.cost_false_positive * counts.false_alerts
    )
    return ExpectedCost(per_event=total / scenario.events, total=total)


def describe_load(scenario: DetectorScenario) -> AlertLoad:
    counts = expected_counts(scenario)
    return AlertLoad(
        expected=counts,
        precision=counts.true_alerts / counts.alerts if counts.alerts else None,
        accuracy_of_always_negative=1 - scenario.prevalence,
        budget=fit_budget(scenario, counts),
        cost=expected_cost(scenario, counts),
    )


def collect_caveats(load: AlertLoad) -> tuple[str, ...]:
    undefined = ('precision is undefined: no alerts are expected',)
    return (
        *(undefined if load.precision is None else ()),
        TRANSFER_ASSUMPTION,
        PERIOD_ASSUMPTION,
    )


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=int, required=True, help='events per period')
    parser.add_argument('--prevalence', type=float, required=True)
    parser.add_argument('--recall', type=float, required=True, help='true positive rate')
    parser.add_argument('--fpr', type=float, required=True, help='false positive rate')
    parser.add_argument('--budget', type=float, help='alerts reviewable per period')
    parser.add_argument('--cost-fn', type=float, help='cost of one missed positive')
    parser.add_argument('--cost-fp', type=float, help='cost of one false alert')
    return parser.parse_args(argv)


def scenario_from(arguments: argparse.Namespace) -> DetectorScenario:
    return DetectorScenario(
        events=arguments.events,
        prevalence=arguments.prevalence,
        recall=arguments.recall,
        false_positive_rate=arguments.fpr,
        review_budget=arguments.budget,
        cost_false_negative=arguments.cost_fn,
        cost_false_positive=arguments.cost_fp,
    )


def main(argv: list[str]) -> int:
    logging.basicConfig(stream=sys.stderr, format='%(levelname)s %(message)s')
    arguments = parse_arguments(argv)
    scenario = scenario_from(arguments)
    if violation := find_scenario_violation(scenario):
        logger.error('%s', violation)
        return CONTRACT_VIOLATION
    load = describe_load(scenario)
    report = Report(
        schema_version=SCHEMA_VERSION,
        command='alert_budget',
        arguments=describe_arguments(arguments),
        result=load,
        caveats=collect_caveats(load),
    )
    sys.stdout.write(msgspec.yaml.encode(report).decode())
    return 0


def console_main() -> int:
    return main(sys.argv[1:])


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
