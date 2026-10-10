# Contributing

This repository is the rygentic-harness plugin marketplace: every capability ships as a plugin
under `plugins/`, and mightymodels, the ticket-scoped dev loop, is its first plugin. It is a
working harness, not a sample gallery. The bar for a change is that the loop still measures
better with it than without it, and that the artifacts agents parse keep their contracts. This
file is the whole gate; there is no hidden tribal knowledge beyond it.

## Setup

Prerequisites:

- [uv](https://docs.astral.sh/uv/)
- Node 22 or newer
- the Claude Code CLI, pinned to the version the gate was built against:
  `npm install -g @anthropic-ai/claude-code@2.1.285`

One command prepares a checkout:

```sh
make setup    # scripts/setup.sh
```

It installs the pre-commit hook (`uv run pre-commit install --install-hooks`) and runs
`uv sync --all-packages --all-groups`. The root `pyproject.toml` is a uv workspace root named
`rygentic-harness-plugins`; `plugins/mightymodels`, `plugins/vibe-code` and
`plugins/python-harness` are its members.

## The gate

`make check` is the whole thing. It runs three targets in order:

1. `make sync` runs `uv sync --locked --all-packages --group check` and `uv lock --check`, so a
   stale lockfile fails the gate.
2. `make pre-commit` runs `uv run pre-commit run --all-files`.
3. `make quality` runs `scripts/quality.sh`, which formats and then lints.

`make format` and `make lint` are the two halves of `make quality`, and they map to
`scripts/quality.sh --format` and `scripts/quality.sh --lint`. Run `make format` first when you
want the tools to fix what they can. `make lint` only reports.

`scripts/quality.sh --lint` runs these checks, and keeps going after a failure so you see every
problem in one pass:

- `ruff format --check` and `ruff check --no-fix`, both with `.ruff.toml`
- `mdformat --check` on `docs/` and the root `*.md` files only
- `ty` at Python 3.14, then a second `ty` pass at Python 3.12 over the skills trees and
  `plugins/vibe-code/src` and `plugins/vibe-code/tests`
- `pytest`, which runs the vibe-code tests in `plugins/vibe-code/tests` and the python-harness
  tests in `plugins/python-harness/tests`
- `claude plugin validate --strict` for each plugin under `plugins/`, then for the root
  marketplace

The `claude` check fails if the CLI is not on your `PATH`, so install it first (see Setup).

Pre-commit runs the standard file hygiene hooks, `ruff format`, `mdformat` on markdown outside
`plugins/`, and a `quality` hook that runs `scripts/quality.sh --lint` on every commit. Only the
pre-commit hook type is installed, so commit messages are not checked by a hook.

CI runs on pull requests to `main` with three jobs: `labeler`, `quality`, and `workflow-narrator`.
The `quality` job runs `uv run pre-commit run --all-files`, which is the same gate as `make check`,
and CI's bootstrap syncs with `uv sync --locked`, so a stale lockfile fails CI too. Pull requests
from forks skip the `labeler` job, but `workflow-narrator` still runs: it reports the result in the
job summary instead of a PR comment, and it still fails the run when `quality` fails.

## Python and markdown rules

Skill scripts under `plugins/*/skills/**` must run on Python 3.12, so a contributor's system
Python can run them. The vibe-code CLI source and tests under `plugins/vibe-code/src` and
`plugins/vibe-code/tests` follow the same rule. Ruff applies a per-file `py312` target to
those paths and the second `ty` pass checks them at 3.12. The rest of the repo targets Python 3.14.

Plugin markdown is excluded from mdformat because mdformat escapes underscore-named XML prompt
tags, which breaks the prompts. Only `docs/` and the root `*.md` files are formatted.

Fix the finding instead of suppressing it. A blanket ignore in config is not acceptable, and a
targeted `noqa` or `ty: ignore` needs a comment with the reason.

## The vibe-code package

`plugins/vibe-code` is also a uv workspace member, the `vibe-code-plugin` package. Its source
is `plugins/vibe-code/src/vibe_code_cli`, with one sub-package per concept (`skill`, `hook`,
`subagent`, `instruction`, `mcp`, `plugin`, `tune`) and the shared modules beside them. Its tests are in
`plugins/vibe-code/tests`. The plugin's skills run the CLI through the `bin/vibe-code` launcher,
which needs `uv` on `PATH`. Its first line is a shebang that runs `uv tool run` with the runtime
dependencies pinned by version, and `bin/vibe-code.cmd` runs the same command for `cmd.exe`.
[plugins/vibe-code/README.md](plugins/vibe-code/README.md) describes both.

Tests are methods of `Test...` classes in `plugins/vibe-code/tests`. The fixtures every concept
uses are in `plugins/vibe-code/tests/conftest.py`: `fake_services`, `unavailable_services`,
`assert_error`, `assert_warning`, `sections` and `fill`. Each concept has a support module at
`plugins/vibe-code/src/vibe_code_cli/<concept>/tests/support.py`, which holds the fixtures only
that concept's tests use. The `pytest_configure` hook in the conftest registers the seven modules
through `config.pluginmanager.import_plugin`, looping over its `CONCEPTS` tuple.

A registered fixture is visible to every test, and when two support modules define the same
name, the later one is taken without an error. A support fixture's name therefore starts with its
concept, as in `skill_root` and `hook_scripts`. Types, constants and plain functions in a support
module are imported by dotted name. `wheel-exclude = ["tests"]` in `plugins/vibe-code/pyproject.toml`
keeps these directories out of the built wheel. The "Tests" section of `.claude/rules/python.md`
holds the rules the tests follow.

The pins select versions and do not verify hashes. To change a dependency, edit
`plugins/vibe-code/pyproject.toml`, run `uv lock` from the repository root, then put the same
versions in line 1 of `plugins/vibe-code/bin/vibe-code` and in `plugins/vibe-code/bin/vibe-code.cmd`.
`plugins/vibe-code/tests/test_shim.py` compares both files with `uv.lock` and fails when they
differ. The launcher stays on `uv tool run` rather than `uv run`, which would adopt the caller's
`.venv`, `pyproject.toml` and `uv.toml`.

The vibe-code eval cases are in `plugins/vibe-code/evals`. Running them with
`claude plugin eval` costs money and is not part of the gate.

`.gitattributes` keeps `plugins/vibe-code/bin/vibe-code` and `plugins/vibe-code/bin/vibe-code.cmd`
on LF line endings, which the `mixed-line-ending` hook requires. `.python-version` at the root and
in `plugins/vibe-code` says 3.14, the development interpreter; the CLI source and tests still have
to run on 3.12.

On WSL, a checked-in script such as `plugins/vibe-code/bin/vibe-code` can lose its
executable bit. Restore it in the index with
`git update-index --chmod=+x <file>`.

## Adding a plugin

A plugin is a directory under `plugins/` carrying a `.claude-plugin/plugin.json` that names it,
plus its `skills/` and `agents/` trees. Add a matching entry to `.claude-plugin/marketplace.json`.
`claude plugin validate --strict` runs for every directory under `plugins/` and for the root
marketplace, and it checks manifests and the skill and agent frontmatter, so a new plugin is
covered without configuration.

## Adding or editing a skill

A skill is a directory under its plugin's `skills/` tree (`plugins/<plugin>/skills/<name>`)
whose `SKILL.md` frontmatter carries `name` (matching the directory, lowercase with hyphens) and
`description`. The description is the retrieval surface in Claude Code's skill selection, so
write it as trigger phrases plus boundaries. `claude plugin validate --strict` enforces the
frontmatter.

Skills that participate in the loop cite the shared contracts instead of restating them. If your
change needs a new severity, verdict, or brief field, it goes in
`plugins/mightymodels/skills/agents-assemble/references/contracts.md` first, and the consuming
skills reference it.

## Documentation

Prose in `README.md` and `docs/` is written under the humanizer rules: no em or en dashes,
sentence-case headings, plain copulas, concrete claims over ceremony. mdformat enforces the
mechanical half (see `.mdformat.toml`); keep doc files roughly 100 to 200 lines and split by
subject rather than growing one page. Reference files under
`plugins/mightymodels/skills/*/references/` are contracts consumed by agents; change their
meaning only with a version note in the changelog.

## Commits and PRs

Commit subjects follow `prefix(scope): summary` with a lowercase summary and no trailing period;
valid prefixes are feat, chore, ops, fix, release, and docs. No hook enforces this, so reviewers
do. Branch from `main`, keep commits scoped to one concern, and arrive with `make check` already
green. The PR template asks for the ticket, what changed, and the verification evidence.

## Releases

Each plugin versions independently: its `plugin.json` and its marketplace entry move together,
with a CHANGELOG.md entry describing the change in one paragraph. The root `pyproject.toml` is
the workspace root `rygentic-harness-plugins`, not a plugin, so it is versioned separately. The changelog is written for the person
deciding whether to upgrade, not as a commit list.
