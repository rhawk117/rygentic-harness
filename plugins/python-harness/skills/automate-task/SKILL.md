---
name: automate-task
description: >-
  Turns one automation request into one runnable Python script with inline dependencies, a command
  line, logging, a dry run and exit codes. Confirms the domain with the user, presents package and
  design options with a recommendation, maps a parallelism level to worker counts, keeps every
  technical choice the user stated, and checks the script before handing it to tactical-slop-review.
when_to_use: >-
  Use when the user wants a manual or repeated task turned into a script that runs unattended:
  cleaning or converting files, checking hosts or services, calling an API or downloading in bulk,
  release and CI chores, or a job for cron or a nightly schedule. Typical requests are "automate
  this", "write a script that does X" and "make this a cron job". Not for HTTP services or
  endpoints (build-web-service), writing unit tests (design-tests) or database schema design
  (design-persistence).
argument-hint: "[what to automate]"
paths:
  - "**/*.py"
  - "**/*.pyi"
  - "**/pyproject.toml"
allowed-tools:
  - Read
  - Grep
  - Glob
  - AskUserQuestion
  - Agent
  - mcp__plugin_python-harness_python-harness__survey
  - mcp__plugin_python-harness_python-harness__gate
  - mcp__plugin_python-harness_python-harness__collect_python_facts
  - mcp__plugin_python-harness_python-harness__search_python_docs
  - mcp__plugin_python-harness_python-harness__read_python_docs
  - mcp__plugin_python-harness_python-harness__check_citations
  - mcp__plugin_python-harness_python-harness__map_python_calls
  - mcp__plugin_python-harness_python-harness__plan_review_surface
  - Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/*)
---

# Automate task

<purpose>
Turn one automation request into one production-shaped Python script the user can run
unattended. Asked to "automate X", an agent left alone writes a happy-path one-off: no CLI, no
logging, no dry-run, no retries, and concurrency that is arbitrary or absent. It also overrides
choices the user stated. This skill fixes that order of work. The user confirms the domain,
sees the package and design options with a recommendation and the reason for it, and picks.
Only then is the script written from a fixed template and checked by a script.
</purpose>

<inputs>
- The script track starts here. The skill can be invoked directly, by name or when the request matches the description.
- Paths below that start with `scripts/`, `references/` or `assets/` are inside this skill's directory, `${CLAUDE_SKILL_DIR}`. Run bundled scripts as `uv run ${CLAUDE_SKILL_DIR}/scripts/NAME.py`. The script you generate goes in the user's working directory at `./scripts/<script_name>.py`, unless the user named a path.
- The plugin's MCP server names each tool `mcp__plugin_python-harness_python-harness__<tool>`; the steps below use the short names. The project tools take no root argument: the project is the session's project directory (`CLAUDE_PROJECT_DIR`). If these tools are not available, tell the user to check the plugin in `/plugin` (its Errors tab) and the server in `/mcp`; the steps below say what to do without them.
- Before the first dispatch below, call `survey` for the project root, the Python version and the toolchain; the dispatches pass them on.
</inputs>

<workflow>
### 1. Intake

1. Restate the request in one line: inputs, outputs, trigger (once, on a schedule, in CI),
   and where it runs.
2. Pull out everything the user already decided: paths, hosts, schedule, output format,
   Python version, a named package, a named concurrency mechanism, a worker count, a
   parallelism level. Explicit technical choices are binding (see section 4, Overrides), so record
   them now, before any analysis can quietly replace them.
3. If the script will live inside an existing Python project, call the `python-harness`
   MCP tool `collect_python_facts` on the project root. It reports `requires-python` and
   existing dependencies, so the script does not bring in a second library for a job the
   project already covers. If the server is not available, read `pyproject.toml` directly.

### 2. Domain

1. Suggest one or more domains from the request's signals. Then let the user choose, with a
   multi-select `AskUserQuestion` that has the suggestion preselected. The user's selection wins over
   the suggestion, because the domain decides which packages are even on the menu.

| domain                              | reference                  | signals                                                          |
| ----------------------------------- | -------------------------- | ---------------------------------------------------------------- |
| data, including dirty-data cleaning | `references/data.md`       | CSV, Excel, JSON, parquet, dedupe, clean, validate, chart, numpy |
| system administration               | `references/sysadmin.md`   | hosts, SSH, systemd, disk, services, cron, certificates          |
| CI and release                      | `references/ci.md`         | GitHub Actions, workflow, changelog, version bump, release       |
| test orchestration                  | `references/testing.md`    | pytest, matrix, flaky, coverage, nox, tox                        |
| code quality                        | `references/quality.md`    | ruff, ty, lint, complexity, coverage report, audit               |
| filesystem                          | `references/filesystem.md` | files, directories, archive, rotate, watch, images               |
| network and HTTP APIs               | `references/network.md`    | URLs, API, download, scrape, webhook, ports                      |
| cloud                               | `references/cloud.md`      | AWS, S3, boto3, GCP, Azure, buckets, tags                        |

2. Read only the references for the chosen domains. Each one holds the package menu, the
   design choices to put to the user, the domain's concurrency profile, pitfalls, and a
   skeleton.
3. Read `references/concurrency.md` and `references/parallelism-and-overrides.md` unless the
   work is plainly a short sequential job and the user said nothing about speed or mechanism.
   When the user names `multiprocessing` or the work is CPU-bound pure Python, the
   `multiprocessing` section of `concurrency.md` is the one that applies.
4. Before relying on a standard-library API, default, or version, confirm it with the
   `python-harness` MCP tools `search_python_docs` and `read_python_docs`. A reference line
   marked `[stdlib: confirm via search_python_docs "..."]` names the query to run. If the
   server is not available, fetch the page from docs.python.org instead. Third-party facts
   come from the reference's cited official docs. Do not assert an API that neither source
   shows. When several facts need confirming, dispatch `python-harness:pep-talk` with the
   questions and the Python version from `survey`. Treat its return as cited facts: open the
   cited lines before relying on them.

### 3. Design

1. Classify the workload as `cpu`, `subprocess`, `io`, or `library`, citing the words in the
   request that decided it.
2. Run `uv run ${CLAUDE_SKILL_DIR}/scripts/parallelism.py --workload KIND --level LEVEL`, using the level
   the user gave or the one you recommend. Add `--requested-workers N` when the user named a
   count. Quote its JSON numbers in the brief rather than computing them yourself; the script
   is what keeps "moderate", "a lot" and "toaster" consistent between runs.
3. Fill `assets/design-brief.template.md` and show it in chat. For every need, give the
   recommended package, the alternatives, and the reason tied to this user's constraints
   (scale, where it runs, dependencies allowed, Python version). Use the version from the
   reference. Then list the domain's design choices from its reference, the concurrency
   section, and any overrides. Every brief also carries two output choices:
   - **Pretty terminal output?** Recommend plain `logging` to stderr for cron, CI, systemd,
     and piped runs, and `rich` for scripts a person watches. See
     `references/terminal-output.md`.
   - **Report rendering**, only when the output is a report: f-strings for short text, Jinja2
     for HTML, row loops, or templates others edit. See `references/reports-jinja.md`.
4. Ask one `AskUserQuestion` form: one field per open decision, with the recommended option
   preselected and labelled "(rec.)". The fields are each package choice, each design choice,
   the two output choices, the parallelism level (always asked when the user gave none), and
   the mechanism when more
   than one is viable. Do not ask again about anything the user already decided. Show it as
   fixed in the brief.
5. If the level or mechanism changed in the form, rerun `scripts/parallelism.py` with the
   final values.
6. When the prompt already answers everything (for example "Everything you'd otherwise ask
   me: take your recommendation"), skip the form. Use the recommendations, and say in the
   brief which defaults you took.

### 4. Overrides

An explicit technical choice from the user (a named mechanism, a worker count, or a package)
is kept even when the analysis disagrees:

- State it once in the brief: "You asked for X; the analysis suggests Y because Z; keeping X."
  Never swap it silently and never argue it twice.
- Implement X as well as X allows. The checklist for each mechanism is in
  `references/parallelism-and-overrides.md`.
- Vague wishes such as "make it fast" are not overrides; the analysis decides.
- If X cannot work at all, ask with concrete options rather than substituting.
- A count above a hard cap is kept with the warning that `scripts/parallelism.py` prints.

The hard caps hold at every level, including toaster: the per-host connection limit, the API
rate limit and `Retry-After`, timeouts, memory per worker, and the file-descriptor limit.

### 5. Build

1. Copy `assets/script.template.py` to `./scripts/<script_name>.py`, replace the
   placeholders, and build the automation inside it.
2. Declare `requires-python = ">=3.12"`. Raise it only when the chosen design needs a newer
   feature (for example `InterpreterPoolExecutor` or `compression.zstd` need 3.14), and say
   so in the brief. List each dependency in the PEP 723 block with a lower bound taken from
   the reference version (`"polars>=2.0"`).
3. Every generated script has:
   - `--dry-run`, which logs every action it would take and changes nothing, locally or
     remotely
   - logging to stderr and results to stdout
   - an `ExitCode` IntEnum: `0` all succeeded, `1` some items failed, `2` usage error
   - a timeout on every network call and subprocess, and retries with backoff only for
     transient failures
   - idempotent re-runs, and atomic output writes (temporary file, then `os.replace`)
   - secrets read from the environment or a keyring, never logged, never put in argv
   - `--workers`, defaulting to the mapped value, whenever the script is concurrent
   - a rejects or errors file whenever items can fail individually
   - when pretty output was chosen, one stderr `rich` console for logs, progress, and the
     summary table, with stdout left for data
   - when Jinja2 was chosen, a `templates/` directory next to the script and an environment
     with `StrictUndefined` and autoescaping for HTML

   These are what separate a script that can run unattended from a one-off, so do not drop
   one without the user agreeing.
4. Follow the repository's house style for the generated code:
   - a frozen `slots=True, kw_only=True` options dataclass built in `main`
   - `build_parser()` plus `main(argv) -> int`, ending with `raise SystemExit(main())`
   - module-level functions with verb-phrase names
   - no lambdas, no comments beyond the module docstring, no `while True`
   - `asyncio.TaskGroup` and `asyncio.timeout` for async code
5. When the user chose a schedule or CI trigger, also write the companion artifact the brief
   promised: a crontab line, a systemd `.service` and `.timer` pair, or the workflow step. Use
   the domain reference's hint for each.

### 6. Verify

1. Run `scripts/check_script.py` on the generated script:
   `uv run ${CLAUDE_SKILL_DIR}/scripts/check_script.py ./scripts/<script_name>.py`. It checks:
   - the PEP 723 header, CLI, `--dry-run`, logging, and `main() -> int` with the guard
   - `--workers` when the script is concurrent
   - no `shell=True`, and a timeout on every subprocess call

   It then runs ruff, and ty as advisory. Exit code `0` means every required check passed.
2. Run `uv run ./scripts/<script_name>.py --help`.
3. Run with `--dry-run` only when that touches nothing but local files or the fixtures in the
   working directory. Skip it when even a dry run would reach remote hosts, APIs, or cloud
   accounts, and say that you skipped it and why.
4. When the script lands inside a Python project and the `python-harness` MCP server is
   available, run its `gate` tool on the project so the script meets the project's own
   quality gate.
5. On a failure, fix it and re-run the failing check, at most twice. Then stop and report
   what still fails, with the check's output. Never weaken a check to make it pass.

When the user asked for tests of the script, dispatch `python-harness:test-engineer` to write
them, briefing it with the script path, the behaviours to pin, and the project root and Python
version from `survey`. When the script lands inside a Python project, dispatch
`python-harness:reviewer` on the script's path before reporting, with the design brief the user settled as the agreed contract,
the behaviours the script must show as the acceptance criteria, the verification output, and the
project root and Python version from `survey`; its findings go into the report.
</workflow>

<dispatch>
Each dispatch in steps 2 and 6 is one `Agent` call to one of these agents. Pass the project root and Python version from `survey` in the request; do not pass a `model`.

- agent: `python-harness:pep-talk`
- model: haiku
- tools: Read, Grep, Glob, `mcp__plugin_python-harness_python-harness__search_python_docs`, `mcp__plugin_python-harness_python-harness__read_python_docs`, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__check_citations`

- agent: `python-harness:test-engineer`
- model: sonnet
- effort: high
- tools: Read, Grep, Glob, Bash, Edit, Write, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__collect_python_facts`, `mcp__plugin_python-harness_python-harness__map_python_calls`, `mcp__plugin_python-harness_python-harness__gate`, `mcp__plugin_python-harness_python-harness__search_python_docs`, `mcp__plugin_python-harness_python-harness__read_python_docs`

- agent: `python-harness:reviewer`
- model: sonnet
- effort: high
- tools: Read, Grep, Glob, Bash, `mcp__plugin_python-harness_python-harness__plan_review_surface`, `mcp__plugin_python-harness_python-harness__check_citations`, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__gate`

If an agent type is not available, stop. The plugin's agents did not load: tell the user to check the plugin in `/plugin` (its Errors tab) or run `claude plugin validate` on it, then start a new session. Do not substitute another agent.
</dispatch>

<gates>
- Intake: every explicit technical choice the user stated is recorded before any analysis (step 1).
- Domain: the user chose it; the suggestion alone does not decide the menu (step 2).
- Design: the brief is shown in chat, every open decision is asked once or the defaults taken are named, and each override is stated once in the "You asked for X..." form (steps 3 and 4).
- Build: every item in the build list is in the script; none is dropped without the user agreeing (step 5).
- Verify: `scripts/check_script.py` exits `0`, `--help` runs, and the dry run is run or its skip is explained (step 6).
- A failing check is fixed and re-run at most twice, then reported with the check's output. No check is weakened to make it pass.
</gates>

<output>
Report:

- the script path and the companion artifacts
- the command to run it and what each flag does
- the chosen packages and design, and every override in the "You asked for X..." form
- the parallelism numbers; when the level was toaster or the user's count went past a hard
  cap, also the caps still enforced (per-host connections, rate limit and `Retry-After`,
  timeouts, memory per worker, file descriptors) with their values
- the verification output
- what was not exercised: for example, remote hosts not contacted, or the dry run skipped and
  why
</output>

<handoff>
The next stage is tactical-slop-review, once code exists. Pass it the script path and the verification output, and say which checks passed, which were skipped and why.
</handoff>
