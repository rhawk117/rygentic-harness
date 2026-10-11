"""Expected alert load, precision and cost of a detector at one prevalence, as YAML."""

import argparse
import logging
import sys
from dataclasses import dataclass
from math import isfinite

import msgspec

from python_harness.scripts.report import (
    LAUNCHER,
    ContractViolationError,
    Report,
    describe_arguments,
    run_command,
)

COMMAND = f'{LAUNCHER} alert-budget'
TRANSFER_ASSUMPTION = 'recall and false positive rate transfer to this population'
PERIOD_ASSUMPTION = 'events are counted over the same period as the review budget'

logger = logging.getLogger('alert_budget')


class RateOutOfRangeError(ContractViolationError):
    def __init__(self, name: str, value: float) -> None:
        super().__init__(f'{name} must be a probability in [0, 1], got {value}')


class NonPositiveEventsError(ContractViolationError):
    def __init__(self, events: int) -> None:
        super().__init__(f'events must be positive, got {events}')


class UnpairedCostError(ContractViolationError):
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


def check_rate(name: str, value: float) -> None:
    if not (isfinite(value) and 0 <= value <= 1):
        raise RateOutOfRangeError(name, value)


def check_scenario(scenario: DetectorScenario) -> None:
    if scenario.events <= 0:
        raise NonPositiveEventsError(scenario.events)
    for name, value in scenario.rates:
        check_rate(name, value)
    if (scenario.cost_false_negative is None) != (scenario.cost_false_positive is None):
        raise UnpairedCostError


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
    parser = argparse.ArgumentParser(prog=COMMAND, description=__doc__)
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


def build_report(argv: list[str]) -> Report[AlertLoad]:
    arguments = parse_arguments(argv)
    scenario = scenario_from(arguments)
    check_scenario(scenario)
    load = describe_load(scenario)
    return Report(
        command=COMMAND,
        arguments=describe_arguments(arguments),
        result=load,
        caveats=collect_caveats(load),
    )


def main(argv: list[str]) -> int:
    return run_command(logger, build_report, argv)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
