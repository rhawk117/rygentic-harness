"""skilleng — one entry point.

    python -m skilleng lint      <skill>
    python -m skilleng doctor    [--probe-hooks] [--host H]
    python -m skilleng calibrate --host H --skill <skill> --queries q.json
    python -m skilleng run       --skill <skill> --evals e.json --workspace W --host H
    python -m skilleng bench     --workspace W --iteration N
    python -m skilleng trigger   --skill <skill> --queries q.json --host H [--roster D]
    python -m skilleng package   <skill> [--out DIR]
    python -m skilleng gate      --workspace W --phase improve

Every command that produces a number refuses to produce one it cannot stand behind.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .aggregate import NoDataError, build
from .grade import grade_case
from .report import to_html, to_markdown
from .schema import (Arm, AssertionKind, EvalSet, Outcome, Provenance, RunRecord,
                     SchemaError, Tier, dir_hash, dump, git_sha)
from .skillmd import errors as lint_errors
from .skillmd import lint, load
from .workspace import Workspace


def _p(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- lint

def cmd_lint(args: argparse.Namespace) -> int:
    findings = lint(Path(args.skill))
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for f in findings:
            print(f)
        blocking = lint_errors(findings)
        print(f"\n{len(findings)} finding(s); {len(blocking)} block packaging.")
    return 1 if lint_errors(findings) else 0


# ---------------------------------------------------------------- doctor / calibrate

def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import main as doctor_main
    argv: list[str] = []
    for h in (args.host or []):
        argv += ["--host", h]
    if args.probe_hooks:
        argv.append("--probe-hooks")
    if args.model:
        argv += ["--model", args.model]
    if args.json:
        argv.append("--json")
    return doctor_main(argv)


def cmd_calibrate(args: argparse.Namespace) -> int:
    from .doctor import calibrate
    queries = json.loads(Path(args.queries).read_text())
    out = calibrate(args.host, queries, model=args.model, tier=Tier(args.tier),
                    min_separation=args.min_separation)
    print(json.dumps(out, indent=2))
    if args.workspace:
        ws = Workspace.create(Path(args.workspace))
        ws.set_gate("controls", bool(out["ok"]), out.get("reason") or out.get("resolving_power_note", ""))
    return 0 if out["ok"] else 1


# ---------------------------------------------------------------- run

def cmd_run(args: argparse.Namespace) -> int:
    from .events import ENV_ARM, ENV_LOG, ENV_RUN, read, skill_invoked, tool_calls
    from .runners import RunRequest, get_adapter

    skill_dir = Path(args.skill).resolve()
    findings = lint(skill_dir)
    if lint_errors(findings) and not args.force:
        for f in lint_errors(findings):
            _p(str(f))
        _p("\nRefusing to measure a skill that will not load. Fix the errors, or pass --force.")
        return 2

    skill = load(skill_dir)
    eval_set = EvalSet.load(Path(args.evals))
    tier = Tier(args.tier)
    adapter = get_adapter(args.host)
    if not adapter.available():
        _p(f"{adapter.cli!r} is not on PATH. Nothing was run — this is an error, not a score of zero.")
        return 2

    ws = Workspace.create(Path(args.workspace))
    if args.require_controls and not ws.gate("controls"):
        _p("controls gate not passed. Run `skilleng calibrate` first, or pass --no-require-controls "
           "to measure with an unverified instrument (and say so when you quote the result).")
        return 2

    iteration = args.iteration or (ws.state().get("iteration", 0) + 1)
    ws.iteration_dir(iteration).mkdir(parents=True, exist_ok=True)
    log = ws.events_path(iteration)

    prov = Provenance(
        host=adapter.name, host_version=adapter.version(), model=args.model,
        surface=args.surface, tier=tier.value, skill_name=skill.name,
        skill_content_hash=dir_hash(skill_dir), assertion_set_hash=eval_set.assertion_set_hash(),
        eval_set_hash=eval_set.eval_set_hash(), git_sha=git_sha(skill_dir),
    )
    ws.save_provenance(iteration, prov)

    arms = [Arm(a) for a in (args.arms or [Arm.BASELINE.value, Arm.AVAILABLE.value, Arm.FORCED.value])]
    sandboxes: dict[Arm, Path] = {}
    for arm in arms:
        sb = Path(tempfile.mkdtemp(prefix=f"skilleng-{arm.value}-"))
        adapter.prepare_sandbox(sb)
        if arm is not Arm.BASELINE:
            adapter.install_skill(sb, skill_dir)
        sandboxes[arm] = sb

    total = len(eval_set.cases) * len(arms) * tier.runs_per_eval
    _p(f"{total} runs: {len(eval_set.cases)} evals x {len(arms)} arms x {tier.runs_per_eval} "
       f"({tier.value} tier) on {adapter.name}")

    for case in eval_set.cases:
        for arm in arms:
            for idx in range(1, tier.runs_per_eval + 1):
                run_id = uuid.uuid4().hex[:12]
                out_dir = ws.prepare_run(iteration, case.id, arm, idx)
                for f in case.files:
                    src = Path(args.evals).parent / f
                    if src.exists():
                        shutil.copy2(src, out_dir.parent / src.name)
                prompt = (adapter.forced_prompt(case.prompt, skill.name)
                          if arm is Arm.FORCED else case.prompt)
                req = RunRequest(prompt=prompt, arm=arm, run_id=run_id, cwd=out_dir,
                                 event_log=log, skill_dir=skill_dir, skill_name=skill.name,
                                 model=args.model, timeout=args.timeout,
                                 extra_env={ENV_LOG: str(log), ENV_RUN: run_id, ENV_ARM: arm.value})
                res = adapter.run(req, sandboxes[arm])
                (out_dir.parent / "stdout.log").write_text(res.stdout or "")
                (out_dir.parent / "stderr.log").write_text(res.stderr or "")

                if not res.ok:
                    rec = RunRecord(eval_id=case.id, arm=arm, run_index=idx, outcome=Outcome.ERROR,
                                    error=res.error or "unknown failure",
                                    duration_seconds=res.duration_seconds)
                    ws.save_run(iteration, rec)
                    _p(f"  {case.id}/{arm.value}#{idx}: ERROR — {res.error}")
                    continue

                mech = [a for a in case.assertions if a.kind is AssertionKind.MECHANICAL]
                results = grade_case(mech, out_dir) if mech else []
                events = read(log)
                rec = RunRecord(
                    eval_id=case.id, arm=arm, run_index=idx, outcome=Outcome.PASS,
                    assertions=results,
                    skill_invoked=(None if arm is Arm.BASELINE else skill_invoked(events, run_id, skill.name)),
                    duration_seconds=res.duration_seconds, tokens=res.tokens,
                    tool_calls=tool_calls(events, run_id),
                    output_files=sorted(p.name for p in out_dir.iterdir() if p.is_file()),
                )
                ws.save_run(iteration, rec)
                _p(f"  {case.id}/{arm.value}#{idx}: ok ({res.duration_seconds:.1f}s, "
                   f"fired={rec.skill_invoked})")

    st = ws.state()
    st["iteration"] = iteration
    st["phase"] = "review"
    ws.write_state(st)
    judged = [a for c in eval_set.cases for a in c.assertions if a.kind is AssertionKind.JUDGED]
    if judged:
        _p(f"\n{len(judged)} judged assertion(s) still need the blinded grader (agents/grader.md).")
    _p(f"\nRuns written to {ws.iteration_dir(iteration)}")
    return 0


# ---------------------------------------------------------------- bench

def cmd_bench(args: argparse.Namespace) -> int:
    ws = Workspace(Path(args.workspace))
    iteration = args.iteration or ws.state().get("iteration", 1)
    try:
        runs = ws.load_runs(iteration)
        prov = ws.load_provenance(iteration)
        bench = build(runs, prov)
    except NoDataError as e:
        _p(f"error: {e}")
        return 2
    except SchemaError as e:
        _p(f"error: {e}")
        return 2

    dump(asdict(bench), ws.benchmark_path(iteration))
    md = to_markdown(asdict(bench))
    (ws.iteration_dir(iteration) / "benchmark.md").write_text(md + "\n")
    ws.report_path(iteration).write_text(to_html(asdict(bench)))
    print(md)
    _p(f"\nwrote {ws.benchmark_path(iteration)} and {ws.report_path(iteration)}")

    if args.compare_to:
        prev = ws.load_provenance(int(args.compare_to))
        ok, blockers = prov.comparable_with(prev)
        if not ok:
            _p("\nNOT COMPARABLE with iteration " + str(args.compare_to) + ":")
            for b in blockers:
                _p(f"  - {b}")
            _p("A trend line across these would be meaningless.")
            return 1
        _p(f"\ncomparable with iteration {args.compare_to} (same model, same assertion set)")
    return 0


# ---------------------------------------------------------------- trigger

def cmd_trigger(args: argparse.Namespace) -> int:
    from .runners import get_adapter
    from .trigger import evaluate
    a = get_adapter(args.host)
    if not a.available():
        _p(f"{a.cli!r} is not on PATH.")
        return 2
    queries = json.loads(Path(args.queries).read_text())
    roster = [Path(p) for p in (args.roster or [])]
    rep = evaluate(a, Path(args.skill), queries, tier=Tier(args.tier), model=args.model, roster=roster)
    print(json.dumps(asdict(rep), indent=2))
    return 0


# ---------------------------------------------------------------- package

def cmd_package(args: argparse.Namespace) -> int:
    from .package import package
    archive, rep, findings = package(Path(args.skill), args.out, include_evals=not args.no_evals)
    print(rep.to_markdown())
    if archive is None:
        _p("\npackaging refused:")
        for f in lint_errors(findings):
            _p(f"  {f}")
        for s in rep.secrets:
            _p(f"  [ERROR] secret: {s}")
        return 1
    _p(f"\npackaged: {archive}")
    _p(f"security report: {Path(args.out or '.').resolve() / (Path(args.skill).resolve().name + '-SECURITY.md')}")
    return 0


# ---------------------------------------------------------------- gate

GATES = {"measure": ["controls"], "improve": ["controls", "review"], "package": ["controls", "review"]}


def cmd_gate(args: argparse.Namespace) -> int:
    ws = Workspace.create(Path(args.workspace))
    if args.set:
        ws.set_gate(args.set, not args.fail, args.detail or "")
        print(f"gate {args.set} = {not args.fail}")
        return 0
    needed = GATES.get(args.phase, [])
    missing = [g for g in needed if not ws.gate(g)]
    if missing:
        _p(f"cannot enter phase {args.phase!r}: gate(s) not passed: {', '.join(missing)}")
        return 1
    st = ws.state()
    st["phase"] = args.phase
    ws.write_state(st)
    print(f"phase = {args.phase}")
    return 0


# ---------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skilleng", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"skilleng {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("lint", help="check a skill for load-blocking and budget problems")
    s.add_argument("skill"); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_lint)

    s = sub.add_parser("doctor", help="verify the harness before trusting it")
    s.add_argument("--host", action="append"); s.add_argument("--probe-hooks", action="store_true")
    s.add_argument("--model"); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("calibrate", help="positive/negative control run; measures resolving power")
    s.add_argument("--host", required=True); s.add_argument("--queries", required=True)
    s.add_argument("--model"); s.add_argument("--tier", default=Tier.QUICK.value)
    s.add_argument("--min-separation", type=float, default=0.5); s.add_argument("--workspace")
    s.set_defaults(fn=cmd_calibrate)

    s = sub.add_parser("run", help="execute evals across arms")
    s.add_argument("--skill", required=True); s.add_argument("--evals", required=True)
    s.add_argument("--workspace", required=True); s.add_argument("--host", required=True)
    s.add_argument("--model"); s.add_argument("--surface", default="cli")
    s.add_argument("--tier", default=Tier.STANDARD.value); s.add_argument("--iteration", type=int)
    s.add_argument("--arms", nargs="*"); s.add_argument("--timeout", type=int, default=300)
    s.add_argument("--force", action="store_true")
    s.add_argument("--require-controls", dest="require_controls", action="store_true", default=True)
    s.add_argument("--no-require-controls", dest="require_controls", action="store_false")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("bench", help="aggregate runs into a benchmark and report")
    s.add_argument("--workspace", required=True); s.add_argument("--iteration", type=int)
    s.add_argument("--compare-to")
    s.set_defaults(fn=cmd_bench)

    s = sub.add_parser("trigger", help="measure trigger accuracy against a real install")
    s.add_argument("--skill", required=True); s.add_argument("--queries", required=True)
    s.add_argument("--host", required=True); s.add_argument("--model")
    s.add_argument("--tier", default=Tier.STANDARD.value); s.add_argument("--roster", nargs="*")
    s.set_defaults(fn=cmd_trigger)

    s = sub.add_parser("package", help="package a skill and emit its security report")
    s.add_argument("skill"); s.add_argument("--out"); s.add_argument("--no-evals", action="store_true")
    s.set_defaults(fn=cmd_package)

    s = sub.add_parser("gate", help="advance the workflow only when preconditions hold")
    s.add_argument("--workspace", required=True); s.add_argument("--phase", default="measure")
    s.add_argument("--set"); s.add_argument("--fail", action="store_true"); s.add_argument("--detail")
    s.set_defaults(fn=cmd_gate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
