import argparse
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport

from mightymodels_evals.cases import load_behavior_dataset, write_behavior_datasets
from mightymodels_evals.executors import (
    CliExecutor,
    Executor,
    ReplayExecutor,
    Variant,
    as_task,
)
from mightymodels_evals.fixtures import build_all
from mightymodels_evals.paths import EVALS_ROOT
from mightymodels_evals.report import (
    Payload,
    build_payload,
    load_payload,
    render_html,
    write_report,
)


def _stamp() -> str:
    return datetime.now(tz=UTC).strftime('%Y-%m-%d')


def cmd_fixtures(args: argparse.Namespace) -> int:
    built = build_all(Path(args.dest))
    print(f'built {len(built)} fixtures under {args.dest}: {", ".join(built)}')
    return 0


def cmd_datasets(args: argparse.Namespace) -> int:
    # behavior datasets regenerate from cases.py; trigger YAMLs are hand-edited data
    datasets_dir = Path(args.dir)
    datasets_dir.mkdir(parents=True, exist_ok=True)
    written = write_behavior_datasets(datasets_dir)
    print(f'wrote {len(written)} behavior datasets under {datasets_dir}')
    return 0


def _evaluate_variants(
    dataset: Dataset, make_executor: Callable[[Variant], Executor]
) -> dict[str, EvaluationReport]:
    reports = {}
    for variant in Variant:
        executor = make_executor(variant)
        reports[variant.value] = dataset.evaluate_sync(
            as_task(executor), name=f'{dataset.name}-{variant.value}', progress=False
        )
    return reports


def cmd_replay(args: argparse.Namespace) -> int:
    dataset = load_behavior_dataset(Path(args.datasets), args.skill)
    reports = _evaluate_variants(
        dataset,
        lambda variant: ReplayExecutor(runs_root=Path(args.runs), variant=variant),
    )
    return _emit(reports, args, mode='replay')


def cmd_run(args: argparse.Namespace) -> int:
    dataset = load_behavior_dataset(Path(args.datasets), args.skill)
    fixtures_root = Path(args.fixtures)
    if not fixtures_root.is_dir():
        print(
            f'fixtures missing at {fixtures_root}; '
            'run `mightymodels-evals fixtures` first',
            file=sys.stderr,
        )
        return 2

    reports = _evaluate_variants(
        dataset,
        lambda variant: CliExecutor(
            command=args.command,
            fixtures_root=fixtures_root,
            staging_root=Path(args.staging),
            skills_root=Path(args.skills_root),
            variant=variant,
            include_sim_notes=args.sim_notes,
            timeout=args.timeout,
        ),
    )
    return _emit(reports, args, mode=f'cli:{args.command.split()[0]}')


def _emit(
    reports: dict[str, EvaluationReport], args: argparse.Namespace, mode: str
) -> int:
    payload = build_payload(reports, runner=args.runner, mode=mode)
    out_dir = Path(args.out_dir)
    json_path = out_dir.joinpath(f'RESULTS-{_stamp()}.json')
    html_path = out_dir.joinpath(f'RESULTS-{_stamp()}.html')
    write_report(payload, json_path, html_path)

    for variant, data in payload['variants'].items():
        print(f'{variant}: {data["passed"]}/{data["total"]} ({data["pass_rate"]:.0%})')
        if data['failures']:
            print(f'  task failures: {len(data["failures"])}')

    print(f'results: {json_path}')
    print(f'report:  {html_path}')
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    payload: Payload = load_payload(Path(args.results))
    Path(args.html).write_text(render_html(payload), encoding='utf-8')
    print(f'report: {args.html}')
    return 0


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--datasets', default=str(EVALS_ROOT.joinpath('datasets')))
    parser.add_argument('--skill', default=None)
    parser.add_argument('--out-dir', default=str(EVALS_ROOT.joinpath('results')))
    parser.add_argument('--runner', default='unspecified')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='mightymodels-evals')
    sub = parser.add_subparsers(dest='command_name', required=True)

    fixtures = sub.add_parser('fixtures', help='build the deterministic fixture repos')
    fixtures.add_argument('--dest', default=str(EVALS_ROOT.joinpath('fixtures')))
    fixtures.set_defaults(func=cmd_fixtures)

    datasets = sub.add_parser('datasets', help='regenerate per-skill behavior datasets')
    datasets.add_argument('--dir', default=str(EVALS_ROOT.joinpath('datasets')))
    datasets.set_defaults(func=cmd_datasets)

    replay = sub.add_parser('replay', help='grade existing run directories')
    replay.add_argument('--runs', required=True)
    _add_common_run_args(replay)
    replay.set_defaults(func=cmd_replay)

    run = sub.add_parser('run', help='execute cases through an agent CLI, then grade')
    run.add_argument(
        '--command', required=True, help='template with {prompt_file} and {workdir}'
    )
    run.add_argument('--fixtures', default=str(EVALS_ROOT.joinpath('fixtures')))
    run.add_argument('--staging', default=str(EVALS_ROOT.joinpath('staging')))
    run.add_argument(
        '--skills-root',
        default=str(EVALS_ROOT.parent.joinpath('plugins/mightymodels/skills')),
    )
    run.add_argument(
        '--sim-notes',
        action='store_true',
        help='append worker-simulation constraints (no-subagent CLIs)',
    )
    run.add_argument('--timeout', type=int, default=2400)
    _add_common_run_args(run)
    run.set_defaults(func=cmd_run)

    report = sub.add_parser('report', help='re-render HTML from a results JSON')
    report.add_argument('--results', required=True)
    report.add_argument('--html', required=True)
    report.set_defaults(func=cmd_report)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
