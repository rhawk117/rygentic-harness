# Contributing

This repository is the rygentic-harness plugin marketplace: every capability ships as a plugin
under `plugins/`, and mightymodels, the ticket-scoped dev loop, is its first plugin. It is a
working harness, not a sample gallery. The bar for a change is that the loop still measures
better with it than without it, and that the artifacts agents parse keep their contracts. This
file is the whole gate; there is no hidden tribal knowledge beyond it.

## The rule that governs everything

A skill edit ships with a re-run of its evals and a new dated result, or it does not ship. This
repo exists partly because earlier versions of these skills had good evals whose results were
lost along the way. `evals/results/` holds the dated JSON and HTML per run; the per-skill
`RESULTS-*.md` files inside `plugins/mightymodels/skills/*/evals/` are the historical trail and
stay where they are.

## Setup

The project targets Python 3.14; the hook scripts under `scripts/` stay 3.12-compatible so a
contributor's system Python can run them. One command prepares a checkout:

```sh
./scripts/precheck.sh    # uv sync --all-groups, then installs the git hooks
```

## Running the harness

All commands run from the repository root:

```sh
uv run plugin-evals fixtures      # deterministic fixture repos
uv run plugin-evals datasets      # regenerate datasets/ from the registered case modules
uv run plugin-evals replay --runs <root>    # grade existing run dirs
uv run plugin-evals report --results evals/results/RESULTS-<date>.json --html <out>
```

Behavior datasets are generated from the specs registered in `evals/src/plugin_evals/case_modules/`,
which is their source of truth; edit the cases, not the YAML. Trigger datasets are the opposite: the
YAML under `evals/datasets/<plugin>/<skill>/` is hand-editable data. Both carry committed `.schema.json`
files so your editor validates them offline.

## The gate

`make ci` is the whole thing, and `make lint` / `make format` / `make security` are its pieces.
The lint leg runs ruff (format check plus the curated rule set in `.ruff.toml`, adopted from the
humansays profile), ty at `error-on-warning` with the escalations in `pyproject.toml`,
shellcheck and shfmt over `scripts/`, markdownlint over the prose set, and the prompt-injection
scan. The test leg compiles everything, then runs pytest 9 with coverage, random test order, and
warnings-as-errors (see `.pytest.toml`).

Every suppression is targeted and carries its reason, whether a `noqa`, a config ignore, or a
scanner pattern note. If your change needs a new blanket ignore, the comment explaining it is
part of the change.

Python style, enforced by the gate where tooling can and by review where it cannot: Python 3.14
with PEP 695 type aliases, single quotes, `Protocol` over ABC, guard clauses over nesting,
functions at or under 50 lines, comments only for rationale that the code cannot carry.

## Adding a plugin

A plugin is a directory under `plugins/` carrying a `.claude-plugin/plugin.json` that names it,
plus its `skills/` and `agents/` trees. Add a matching entry to the repo-root marketplace
manifest and the shared machinery covers the rest: `tests/test_plugin.py` discovers every
plugin, checks its manifest against its marketplace entry, and holds its skills and agents to
the frontmatter contracts; `scripts/security.sh` scans every plugin's skill and agent text
without configuration. Nothing in the gate is hardcoded to one plugin.

## Adding a plugin's evals

A plugin registers its behavior cases through the same registry every other plugin uses, in
`evals/src/plugin_evals/`. Follow these steps in order:

1. Create `evals/src/plugin_evals/case_modules/<plugin>.py`. Give it a `PLUGIN` constant holding
   the plugin's name and a `SPECS` tuple of `CaseSpec` values, one per case, built with checks
   from `plugin_evals.evaluators`. Use `case_modules/mightymodels.py` as the shape to follow: a
   small builder function per case, a real task prompt, and a modest set of checks.
2. Add the module to `CASE_MODULES` in `evals/src/plugin_evals/registry.py`. This is the only
   registry edit; skill names must stay unique across every registered plugin.
3. Generate the dataset: `uv run plugin-evals datasets --plugin <plugin>`. This writes
   `evals/datasets/<plugin>/<skill>/behavior.yaml` and its `behavior.schema.json` for each spec.
4. Commit the generated `evals/datasets/<plugin>/<skill>/` files alongside the case module and
   registry edit. Hand-written trigger datasets are optional and separate; add
   `evals/datasets/<plugin>/<skill>/trigger.yaml` yourself if you want one.

## Adding or editing a skill

A skill is a directory under its plugin's `skills/` tree (`plugins/<plugin>/skills/<name>`)
whose `SKILL.md` frontmatter carries
`name` (matching the directory, lowercase with hyphens) and `description`. The description is
the retrieval surface in Claude Code's skill selection, so write it as trigger phrases plus
boundaries, and add a
near-miss to the trigger dataset when the name or description is anywhere close to an existing
skill.
`tests/test_plugin.py` enforces the frontmatter contract; a new behavior case belongs in the
skill's plugin case module under `evals/src/plugin_evals/case_modules/` (see "Adding a plugin's
evals" above) with checks from the evaluator library. Skill text is code: `scripts/security.sh`
scans it for injection indicators on every commit, and a finding blocks the commit.

Skills that participate in the loop cite the shared contracts instead of restating them. If your
change needs a new severity, verdict, or brief field, it goes in
`plugins/mightymodels/skills/agents-assemble/references/contracts.md` first, and the consuming
skills reference it.

## Documentation

Prose in `README.md` and `docs/` is written under the humanizer rules: no em or en dashes,
sentence-case headings, plain copulas, concrete claims over ceremony. markdownlint enforces the
mechanical half (see `.markdownlint.yaml`); keep doc files roughly 100 to 200 lines and split by
subject rather than growing one page. Reference files under
`plugins/mightymodels/skills/*/references/` are contracts consumed by agents; change their
meaning only with a version note in the changelog.

## Commits and PRs

Commit subjects follow `prefix(scope): summary` with a lowercase summary and no trailing period;
valid prefixes are feat, chore, ops, fix, release, and docs. The commit-msg hook enforces this
(`scripts/check_commit_msg.py`). Branch from `main`, keep commits scoped to one concern, and
arrive with the gate already green; for skill changes, the dated eval result belongs in the
diff. The PR template asks for the ticket, what changed, and the verification evidence.

## Releases

Each plugin versions independently: its `plugin.json` and its marketplace entry move together
(`tests/test_plugin.py` enforces the agreement), with a CHANGELOG.md entry describing the
change in one paragraph. `pyproject.toml` versions the eval harness and currently tracks
mightymodels. The changelog is written for the person deciding whether to upgrade, not as a
commit list.
