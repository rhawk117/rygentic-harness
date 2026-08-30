# Contributing

mightymodels is a working harness, not a sample gallery. The bar for a change is that the loop
still measures better with it than without it, and that the artifacts agents parse keep their
contracts. This file is the whole gate; there is no hidden tribal knowledge beyond it.

## The rule that governs everything

A skill edit ships with a re-run of its evals and a new dated result, or it does not ship. This
repo exists partly because earlier versions of these skills had good evals whose results were
lost along the way. `evals/results/` holds the dated JSON and HTML per run; the per-skill
`RESULTS-*.md` files inside `skills/*/evals/` are the historical trail and stay where they are.

## Setup

The project targets Python 3.14; the hook scripts under `scripts/` stay 3.12-compatible so a
contributor's system Python can run them. One command prepares a checkout:

```sh
./scripts/precheck.sh    # uv sync --all-groups, then installs the git hooks
```

## Running the harness

All commands run from the repository root:

```sh
uv run mightymodels-evals fixtures      # deterministic fixture repos
uv run mightymodels-evals datasets      # regenerate datasets/ from cases.py
uv run mightymodels-evals replay --runs <root>    # grade existing run dirs
uv run mightymodels-evals report --results evals/results/RESULTS-<date>.json --html <out>
```

Behavior datasets are generated from `evals/src/mightymodels_evals/cases.py`, which is their source
of truth; edit the cases, not the YAML. Trigger datasets are the opposite: the YAML under
`evals/datasets/<skill>/` is hand-editable data. Both carry committed `.schema.json` files so
your editor validates them offline.

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

## Adding or editing a skill

A skill is a directory under `skills/` whose `SKILL.md` frontmatter carries `name` (matching the
directory, lowercase with hyphens) and `description`. The description is the retrieval surface
in Claude Code's skill selection, so write it as trigger phrases plus boundaries, and add a
near-miss to the trigger dataset when the name or description is anywhere close to an existing
skill.
`tests/test_plugin.py` enforces the frontmatter contract; a new behavior case belongs in
`cases.py` with checks from the evaluator library. Skill text is code: `scripts/security.sh`
scans it for injection indicators on every commit, and a finding blocks the commit.

Skills that participate in the loop cite the shared contracts instead of restating them. If your
change needs a new severity, verdict, or brief field, it goes in
`skills/agents-assemble/references/contracts.md` first, and the consuming skills reference it.

## Documentation

Prose in `README.md` and `docs/` is written under the humanizer rules: no em or en dashes,
sentence-case headings, plain copulas, concrete claims over ceremony. markdownlint enforces the
mechanical half (see `.markdownlint.yaml`); keep doc files roughly 100 to 200 lines and split by
subject rather than growing one page. Reference files under `skills/*/references/` are contracts
consumed by agents; change their meaning only with a version note in the changelog.

## Commits and PRs

Commit subjects follow `prefix(scope): summary` with a lowercase summary and no trailing period;
valid prefixes are feat, chore, ops, fix, release, and docs. The commit-msg hook enforces this
(`scripts/check_commit_msg.py`). Branch from `main`, keep commits scoped to one concern, and
arrive with the gate already green; for skill changes, the dated eval result belongs in the
diff. The PR template asks for the ticket, what changed, and the verification evidence.

## Releases

Versions move in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and
`pyproject.toml` together, with a CHANGELOG.md entry describing the change in one paragraph. The
changelog is written for the person deciding whether to upgrade, not as a commit list.
