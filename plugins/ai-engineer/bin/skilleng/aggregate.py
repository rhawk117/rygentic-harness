"""Turn run records into a benchmark — or refuse to.

Two rules, both learned from watching skill-creator produce a confident report from
nothing:

  1. Zero runs is an error, not a table of zeros.
  2. A delta is (treatment − control) looked up by arm role. It is never
     configs[0] − configs[1] over a sorted directory listing, which silently inverts
     whenever the baseline directory happens to sort first.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from skilleng import SCHEMA_VERSION
from skilleng.schema import (
    DELTAS,
    Arm,
    AssertionKind,
    Outcome,
    Provenance,
    RunRecord,
    SchemaError,
    Tier,
)
from skilleng.stats import (
    Interval,
    mde_paired,
    n_for_mde,
    paired_bootstrap,
    spread,
    wilson,
)


class NoDataError(SchemaError):
    """Raised instead of emitting a benchmark nobody should trust."""


@dataclass
class ArmSummary:
    arm: str
    runs: int
    errors: int
    error_rate: float
    scored_runs: int
    mean_score: float | None
    score_sd: float | None
    score_interval: dict | None
    trigger_rate: dict | None
    mean_duration_seconds: float | None
    mean_tokens: float | None  # None when the host reported none — never chars
    tokens_available: bool


@dataclass
class DeltaSummary:
    name: str
    treatment: str
    control: str
    paired_evals: int
    point: float | None
    interval: dict | None
    interpretation: str


@dataclass
class Benchmark:
    schema_version: int
    provenance: dict
    arms: list[dict]
    deltas: list[dict]
    per_eval: list[dict]
    diagnostics: list[str] = field(default_factory=list)
    claims_permitted: dict = field(default_factory=dict)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def summarise_arm(runs: list[RunRecord], arm: Arm, tier: Tier) -> ArmSummary:
    mine = [r for r in runs if r.arm is arm]
    errors = [r for r in mine if r.outcome is Outcome.ERROR]
    scores = [s for s in (r.score() for r in mine) if s is not None]

    passes = sum(
        1
        for r in mine
        for a in r.assertions
        if a.kind is not AssertionKind.HUMAN and a.outcome is Outcome.PASS
    )
    total = sum(
        1
        for r in mine
        for a in r.assertions
        if a.kind is not AssertionKind.HUMAN and a.outcome is not Outcome.ERROR
    )
    interval = wilson(passes, total) if (total and tier.may_claim_intervals) else None

    trig = [r.skill_invoked for r in mine if r.skill_invoked is not None]
    trigger = None
    if trig:
        t = (
            wilson(sum(trig), len(trig))
            if tier.may_claim_intervals
            else Interval(
                sum(trig) / len(trig), 0.0, 1.0, 'point-estimate-only', len(trig)
            )
        )
        trigger = asdict(t)

    toks = [r.tokens for r in mine if r.tokens is not None]
    return ArmSummary(
        arm=arm.value,
        runs=len(mine),
        errors=len(errors),
        error_rate=(len(errors) / len(mine)) if mine else 0.0,
        scored_runs=len(scores),
        mean_score=_mean(scores),
        score_sd=spread(scores) if scores else None,
        score_interval=asdict(interval) if interval else None,
        trigger_rate=trigger,
        mean_duration_seconds=_mean([
            r.duration_seconds for r in mine if r.duration_seconds is not None
        ]),
        mean_tokens=_mean([float(t) for t in toks]) if toks else None,
        tokens_available=bool(toks),
    )


def _per_eval_scores(runs: list[RunRecord], arm: Arm) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for r in runs:
        if r.arm is not arm:
            continue
        s = r.score()
        if s is not None:
            buckets.setdefault(r.eval_id, []).append(s)
    return {k: sum(v) / len(v) for k, v in buckets.items()}


def build(runs: list[RunRecord], provenance: Provenance) -> Benchmark:
    if not runs:
        raise NoDataError(
            'no run records found. Refusing to emit a benchmark from zero runs — '
            'a table of zeros is indistinguishable from a real result and skill-creator '
            'prints one, with placeholder labels, and exits 0.'
        )

    tier = Tier(provenance.tier)
    present = [a for a in Arm if any(r.arm is a for r in runs)]
    arms = [summarise_arm(runs, a, tier) for a in present]
    diagnostics: list[str] = []

    # -- deltas, by role ---------------------------------------------------
    deltas: list[DeltaSummary] = []
    for name, (treat, ctrl) in DELTAS.items():
        if treat not in present or ctrl not in present:
            continue
        t_scores, c_scores = _per_eval_scores(runs, treat), _per_eval_scores(runs, ctrl)
        shared = sorted(set(t_scores) & set(c_scores))
        if not shared:
            diagnostics.append(
                f'delta {name!r} skipped: no eval was scored in both '
                f'{treat.value} and {ctrl.value}'
            )
            continue
        paired = [t_scores[e] - c_scores[e] for e in shared]
        ci = (
            paired_bootstrap(paired)
            if tier.may_claim_intervals and len(paired) > 1
            else None
        )
        deltas.append(
            DeltaSummary(
                name=name,
                treatment=treat.value,
                control=ctrl.value,
                paired_evals=len(paired),
                point=sum(paired) / len(paired),
                interval=asdict(ci) if ci else None,
                interpretation=(
                    'execution quality with trigger variance removed'
                    if name == 'lift'
                    else 'what a user actually gets end to end'
                ),
            )
        )

    # -- per-eval rows -----------------------------------------------------
    per_eval: list[dict] = []
    for eid in sorted({r.eval_id for r in runs}):
        row: dict = {'eval_id': eid}
        for a in present:
            rs = [r for r in runs if r.eval_id == eid and r.arm is a]
            ss = [s for s in (r.score() for r in rs) if s is not None]
            row[a.value] = {
                'runs': len(rs),
                'errors': sum(1 for r in rs if r.outcome is Outcome.ERROR),
                'mean_score': _mean(ss),
                'score_sd': spread(ss) if ss else None,
            }
        per_eval.append(row)

    # -- diagnostics -------------------------------------------------------
    total_err = sum(a.errors for a in arms)
    if total_err:
        diagnostics.append(
            f'{total_err} of {len(runs)} runs errored. Errors are excluded from scores, '
            'not counted as failures — but a high error rate means the numbers below '
            'rest on less data than they look like.'
        )
    if not any(a.tokens_available for a in arms):
        diagnostics.append(
            'token counts unavailable from this host; the tokens column is omitted '
            'rather than filled with a character count.'
        )
    diagnostics.extend(
        f'the skill fired in only {a.trigger_rate["point"]:.0%} of `available` runs — '
        'read the `lift` delta (which forces invocation) before concluding the '
        'instructions are weak.'
        for a in arms
        if a.arm == Arm.AVAILABLE.value
        and a.trigger_rate
        and a.trigger_rate['point'] < 0.5
    )
    if any(r.skill_invoked is None for r in runs if r.arm is not Arm.BASELINE):
        diagnostics.append(
            'some runs produced no hook events, so triggering is unknown (not false) '
            'for those. Run `skilleng doctor --probe-hooks` to check the adapter mapping.'
        )

    # non-discriminating assertions
    for eid in {r.eval_id for r in runs}:
        for aid in {a.id for r in runs if r.eval_id == eid for a in r.assertions}:
            outcomes = {
                a.outcome
                for r in runs
                if r.eval_id == eid
                for a in r.assertions
                if a.id == aid
            }
            if outcomes == {Outcome.PASS} and len(present) > 1:
                diagnostics.append(
                    f'assertion {eid}/{aid} passes in every arm — it does not '
                    'discriminate, so it cannot contribute evidence that the skill helps.'
                )

    # -- resolving power ---------------------------------------------------
    lift = next((d for d in deltas if d.name == 'lift'), None)
    if lift and lift.paired_evals >= 2:
        sd = (
            spread([
                t - c
                for t, c in zip(
                    list(_per_eval_scores(runs, Arm.FORCED).values()),
                    list(_per_eval_scores(runs, Arm.BASELINE).values()),
                    strict=False,
                )
            ])
            or 0.25
        )
        mde = mde_paired(lift.paired_evals, sd)
        diagnostics.append(
            f'resolving power: at {lift.paired_evals} paired evals this configuration '
            f'can detect a difference of about {mde:.2f}; resolving 0.10 would need '
            f'roughly {n_for_mde(0.10, sd)} evals.'
        )

    return Benchmark(
        schema_version=SCHEMA_VERSION,
        provenance=asdict(provenance),
        arms=[asdict(a) for a in arms],
        deltas=[asdict(d) for d in deltas],
        per_eval=per_eval,
        diagnostics=diagnostics,
        claims_permitted={
            'tier': tier.value,
            'intervals': tier.may_claim_intervals,
            'significance': tier.may_claim_significance,
            'note': (
                'At quick tier this report shows point estimates only. It cannot tell '
                'you whether a difference is real; re-run at standard or rigorous '
                'for that.'
                if not tier.may_claim_intervals
                else (
                    'Intervals are shown. Only rigorous tier adds a confirmation run '
                    'on a fresh sample.'
                )
            ),
        },
    )
