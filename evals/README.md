# mightymodels-evals

The eval harness for the mightymodels plugin, built on pydantic-evals (API verified against the
installed 2.32.1 source, not training priors). It replaces the ad-hoc scripts from the original
build with one package: typed evaluators, serialized datasets, pluggable executors, and a
self-contained HTML report.

## Method

A behavior case is a fixture repo plus a task prompt plus a tuple of typed checks. Checks are
pydantic-evals `Evaluator` dataclasses (`src/mightymodels_evals/evaluators.py`) with labeled
evaluation names, so a report row reads "no source commits by the finish session", not
"GitCommitsTouchingAtMost_3". Every check returns an `EvaluationReason` carrying evidence, and
the same dataset always runs twice, with-skill and baseline, because a pass rate without its
baseline is a vibe, not a measurement.

Two lessons from the first iteration are structural here. `GitDiffEmpty` alone misses work that
was *committed* to look clean: `GitCommitsTouchingAtMost` exists because the baseline
stick-the-landing run did exactly that. And fixture state must be committed state: an uncommitted
edit inside a fixture reads as agent activity to any git-based check (the sendoff fixture now
commits its stale-claims issue body).

## Layout

`datasets/<skill>/` holds everything eval-related for one skill: `behavior.yaml` +
`behavior.schema.json` (regenerated from `cases.py`, the source of truth) and `trigger.yaml` +
`trigger.schema.json` (hand-editable data, the YAML is the source of truth). Schema files use
the `.schema.json` suffix and are committed so editors validate without running the tool.
Fixture file bodies live as real files under `src/mightymodels_evals/templates/` (bases plus
per-fixture overlays); builders in `fixtures.py` compose them and run git steps through
`repo.Repo`, the one place repository operations are defined, shared by builders and evaluators
alike. A builder editing a template string that no longer exists raises `TemplateDriftError`
instead of silently no-opping; it caught its first real bug during its own commit.

## Commands

```sh
uv run mightymodels-evals fixtures                  # deterministic fixture repos -> evals/fixtures/
uv run mightymodels-evals datasets                  # (re)write datasets/ from cases.py
uv run mightymodels-evals replay --runs <root>      # grade existing run dirs (<root>/<case>/<variant>/work + response.md)
uv run mightymodels-evals run --command '<cli> -p {prompt_file}' --sim-notes   # execute through an agent CLI, then grade
uv run mightymodels-evals report --results <json> --html <out>                 # re-render
```

Executors: `replay` is the tested path (it reproduced this repo's iteration-1 verdict:
with-skill 58/58, baseline 27/58). `run`'s CliExecutor is design-verified but not exercised
against a real agent CLI in this environment; treat the command template as the
integration point and expect one round of fitting. Pass `--sim-notes` only for CLIs without
subagents; harnesses with real workers should run the cases without simulation constraints.

Trigger datasets (`datasets/<skill>/trigger.yaml`, sprint collision pairs included) ship
without an executor on purpose: triggering is retrieval-specific. Wire them to your retrieval
oracle: embed `"{name}: {description}"` and assert should-trigger queries rank the skill top-k.

## Results retention

Each run writes `results/RESULTS-<date>.json` and `.html`; commit both. The per-skill
`RESULTS-*.md` files inside `skills/*/evals/` are the historical evidence trail from the
original build sessions and stay where they are. The rule stands: a skill edit ships with a
re-run and a new dated result, or it doesn't ship.

## Fixtures

Built deterministically by `fixtures.py` (gitignored; rebuild anytime). Deliberate traps, kept
on purpose: fx-finish's REPORT.md claims commits that were never applied (discriminates
surface-the-discrepancy from paper-over-it); fx-sendoff's issue claims a file that was renamed
after `triaged-at`; fx-debug's symptom lives in `report.py` while the cause sits in
`appconfig.py` behind a tempting one-line hack. Known soft spots to harden in iteration 2:
fx-debug's cause is one `git log` away (bury it under noisier history), and lets-investigate
needs a scope-creep trap.

## Gate

`make ci` from the repository root: ruff format check plus the curated `.ruff.toml` rule set,
ty 0.0.73 at error-on-warning with the pyproject escalations, shellcheck and markdownlint, the
skills prompt-injection scan, compileall, and pytest 9 (coverage, random order,
warnings-as-errors) on Python 3.14; all legs ran clean at commit time with 42 tests. Every
remaining suppression is a targeted noqa carrying its reason. `tests/test_plugin.py` doubles as
the plugin layout contract: skill frontmatter stays on the keys Claude Code accepts, agent
files stay complete, and the two plugin manifests keep matching versions.
