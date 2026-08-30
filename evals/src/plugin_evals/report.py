import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

from jinja2 import Environment, FileSystemLoader

from plugin_evals.paths import REPORT_TEMPLATE

if TYPE_CHECKING:
    from pydantic_evals.reporting import EvaluationReport

SERIES = {'with_skill': 'With skill', 'without_skill': 'Baseline'}


class AssertionRow(TypedDict):
    name: str
    passed: bool
    reason: str


class CaseRow(TypedDict):
    name: str
    skill: str
    duration: float
    assertions: list[AssertionRow]


class VariantSummary(TypedDict):
    cases: list[CaseRow]
    passed: int
    total: int
    pass_rate: float
    failures: list[str]


class SkillRow(TypedDict, total=False):
    skill: str
    with_skill: float
    without_skill: float


class Payload(TypedDict):
    generated_at: str
    runner: str
    mode: str
    variants: dict[str, VariantSummary]
    skills: list[SkillRow]


class _CasePair(TypedDict):
    skill: str
    variants: dict[str, list[AssertionRow]]


class TileRow(TypedDict):
    label: str
    value: str
    sub: str


class BarRow(TypedDict):
    skill: str
    with_pct: int
    with_label: str
    without_pct: int
    without_label: str


class CheckRow(TypedDict):
    name: str
    cells: list[AssertionRow | None]


class PairRow(TypedDict):
    skill: str
    name: str
    checks: list[CheckRow]


def build_payload(
    reports: dict[str, EvaluationReport], runner: str, mode: str
) -> Payload:
    variants = {variant: _summarize(report) for variant, report in reports.items()}
    return Payload(
        generated_at=datetime.now(tz=UTC).isoformat(timespec='seconds'),
        runner=runner,
        mode=mode,
        variants=variants,
        skills=_skill_rows(variants),
    )


def load_payload(path: Path) -> Payload:
    return cast('Payload', json.loads(path.read_text(encoding='utf-8')))


def write_report(payload: Payload, json_path: Path, html_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    html_path.write_text(render_html(payload), encoding='utf-8')


def render_html(payload: Payload) -> str:
    variants = payload['variants']
    with_v = variants.get('with_skill', _empty_summary())
    without_v = variants.get('without_skill', _empty_summary())
    template = Environment(
        loader=FileSystemLoader(REPORT_TEMPLATE.parent), autoescape=True
    ).get_template(REPORT_TEMPLATE.name)
    return template.render(
        generated_at=payload['generated_at'],
        tiles=_tile_rows(payload, with_v, without_v),
        skills=[_bar_row(row) for row in payload['skills']],
        failures=with_v['failures'] + without_v['failures'],
        case_pairs=_pair_rows(variants),
    )


def _summarize(report: EvaluationReport) -> VariantSummary:
    cases = [_case_row(case) for case in report.cases]
    passed = sum(a['passed'] for c in cases for a in c['assertions'])
    total = sum(len(c['assertions']) for c in cases)
    return VariantSummary(
        cases=cases,
        passed=passed,
        total=total,
        pass_rate=round(passed / total, 4) if total else 0.0,
        failures=[str(f) for f in report.failures],
    )


def _case_row(case: object) -> CaseRow:
    metadata = getattr(case, 'metadata', None) or {}
    assertions = [
        AssertionRow(name=r.name, passed=bool(r.value), reason=r.reason or '')
        for r in getattr(case, 'assertions', {}).values()
    ]
    return CaseRow(
        name=getattr(case, 'name', ''),
        skill=str(metadata.get('skill', '')),
        duration=round(getattr(case, 'task_duration', 0.0), 2),
        assertions=assertions,
    )


def _empty_summary() -> VariantSummary:
    return VariantSummary(cases=[], passed=0, total=0, pass_rate=0.0, failures=[])


def _skill_rows(variants: dict[str, VariantSummary]) -> list[SkillRow]:
    rows: dict[str, SkillRow] = {}
    for variant, summary in variants.items():
        for case in summary['cases']:
            key = case['skill'] or case['name']
            row = rows.setdefault(key, SkillRow(skill=key))
            checks = case['assertions']
            rate = (
                round(sum(a['passed'] for a in checks) / len(checks), 4)
                if checks
                else 0.0
            )
            if variant == 'with_skill':
                row['with_skill'] = rate
            else:
                row['without_skill'] = rate
    return [rows[key] for key in sorted(rows)]


def _pair_cases(variants: dict[str, VariantSummary]) -> dict[str, _CasePair]:
    pairs: dict[str, _CasePair] = {}
    for variant, summary in variants.items():
        for case in summary['cases']:
            pair = pairs.setdefault(
                case['name'], _CasePair(skill=case['skill'], variants={})
            )
            pair['variants'][variant] = case['assertions']
    return pairs


def _tile_rows(
    payload: Payload, with_v: VariantSummary, without_v: VariantSummary
) -> list[TileRow]:
    delta = with_v['pass_rate'] - without_v['pass_rate']
    return [
        TileRow(
            label='With skill',
            value=f'{with_v["pass_rate"]:.0%}',
            sub=f'{with_v["passed"]}/{with_v["total"]} checks',
        ),
        TileRow(
            label='Baseline',
            value=f'{without_v["pass_rate"]:.0%}',
            sub=f'{without_v["passed"]}/{without_v["total"]} checks',
        ),
        TileRow(label='Delta', value=f'{delta:+.0%}', sub='pass-rate lift'),
        TileRow(label='Mode', value=payload['mode'], sub=payload['runner']),
    ]


def _bar_row(row: SkillRow) -> BarRow:
    with_rate = row.get('with_skill', 0.0)
    without_rate = row.get('without_skill', 0.0)
    return BarRow(
        skill=row.get('skill', ''),
        with_pct=round(with_rate * 100),
        with_label=f'{with_rate:.0%}',
        # a zero baseline keeps a 1% sliver so the bar reads as present-but-empty
        without_pct=round(max(without_rate, 0.01) * 100),
        without_label=f'{without_rate:.0%}',
    )


def _pair_rows(variants: dict[str, VariantSummary]) -> list[PairRow]:
    return [
        PairRow(skill=pair['skill'], name=name, checks=_check_rows(pair))
        for name, pair in _pair_cases(variants).items()
    ]


def _check_rows(pair: _CasePair) -> list[CheckRow]:
    names = sorted({a['name'] for rows in pair['variants'].values() for a in rows})
    return [
        CheckRow(
            name=check,
            cells=[
                next(
                    (a for a in pair['variants'].get(variant, []) if a['name'] == check),
                    None,
                )
                for variant in SERIES
            ],
        )
        for check in names
    ]
