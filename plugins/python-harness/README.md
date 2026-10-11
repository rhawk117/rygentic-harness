# python-harness

A Claude Code plugin for Python engineering. It ships:

| Component | Path | What it does |
| --- | --- | --- |
| Skill `what-would-ryan-say` | `skills/what-would-ryan-say/` | `/python-harness:what-would-ryan-say pr <num\|branch> \| codebase [path]  report \| plan`: reviews Python against Ryan's guide and philosophy, writes `PYTHON-REVIEW.md` or `REFACTOR-PLAN.md`, never edits code. Runs only when you type it. |
| Agent `pylens` | `agents/pylens.md` | Read-only fact gatherer on Haiku, dispatched by the skill as `python-harness:pylens`. It has `Read`, `Grep`, `Glob` and three of the server's tools (`collect_python_facts`, `map_python_calls`, `check_citations`), and returns cited facts as Markdown tables. CLAUDE.md is not loaded for it. |
| Hooks | `hooks/hooks.json` | SessionStart: briefs the session on the project's Python toolchain. PreToolUse (Bash): adds a note when a command runs plain `python`/`python3`, suggesting `uv run python`. Never blocks. |
| MCP server `python-harness` | `.mcp.json`, `src/python_harness/server.py` | Eight tools over stdio. `search_python_docs` and `read_python_docs` read the standard-library documentation on `docs.python.org`. `survey`, `gate`, `collect_python_facts`, `map_python_calls`, `check_citations` and `plan_review_surface` read the project Claude Code was started in and return JSON. |
| Data commands | `bin/python-harness-data`, `src/python_harness/scripts/` | `alert-budget`, `paired-compare`, `profile-data` and `size-check`: each prints one YAML report. Run as `python-harness-data <subcommand>`. |
| CLI `python-harness inspect` | `src/python_harness/`, launcher `bin/python-harness` | `inspect survey` reports the project's layout, manifest, inferred mode and domains. `inspect gate` runs the project's own ruff check, ruff format check, ty and pytest. Each prints one JSON document: facts, never verdicts. |
| CLI `python-harness hooks` | `src/python_harness/hooks/` | `session-start \| guard-python`: the hook handlers, event JSON on stdin and hook JSON on stdout. |

## Requirements

- Claude Code, with `uv` on `PATH`, on a POSIX system (Linux, macOS, WSL). The launcher does not run on native Windows.
- The CLI and the MCP server need Python 3.14 or newer; `uv` fetches it when it is missing.
- Network access to `docs.python.org` for the two documentation tools, and to a package index the first time `uv` builds each environment.

## Install

```text
/plugin marketplace add <owner>/rygentic-harness
/plugin install python-harness@rygentic-harness
```

To load it from a checkout for one session instead, run this from the repository root:

```sh
claude --plugin-dir plugins/python-harness
```

Start Claude Code in the root of the Python project you want to work on: the server's six project tools read that directory and no other. Hooks and agents are read when a session starts, so start a new session after changing them.

- Claude Code puts the plugin's `bin/` on the Bash tool's `PATH`, after your own entries, so the model can run `python-harness` as a bare command. This plugin is built and tested for Claude Code only.
- Plugin agents cannot be hidden, so `python-harness:pylens` appears in `@` completion. Its description tells Claude not to delegate other work to it.
- pylens runs on Haiku. If many of its citations fail `check_citations`, set `model: sonnet` in `agents/pylens.md`.

## The MCP server

`.mcp.json` declares one stdio server named `python-harness`. It has eight tools, and the skill and `pylens` call each one as `mcp__plugin_python-harness_python-harness__<tool>`.

| Tool | Reads | What it returns |
| --- | --- | --- |
| `search_python_docs` | `docs.python.org` | Standard-library symbols that match a name, for one Python version. Each match is labeled exact, prefix or approximate. |
| `read_python_docs` | `docs.python.org` | One symbol's documentation as Markdown, one page at a time. |
| `survey` | The project | The project's mode, domains and layout, with its manifest, ruff config, ty config and external packages. It takes no arguments. |
| `gate` | The project | The report of the project's ruff check, ruff format check, ty and pytest. It takes no arguments and runs the project's own tools. |
| `collect_python_facts` | The project | Mechanical AST facts for the modules under `paths`, by line and kind. `with_function_shapes` adds one entry per function. `detail` and `budget` set how much comes back. |
| `map_python_calls` | The project | Where the project references the symbols of the modules under `paths`. With `symbol`, every reference of that one symbol by path and line. `detail` and `budget` set how much comes back. |
| `check_citations` | The project | Whether each `path.py:line` citation and its backticked quote in a Markdown document matches the code. The document is a `path` or inline `text`, exactly one. |
| `plan_review_surface` | The project | A review surface as import-graph clusters of modules, for `paths` or for the modules changed since `diff_base`. |

`skills/what-would-ryan-say/references/inspect-cli.md` gives the shape of each JSON document.

### How it starts

`.mcp.json` runs `uv tool run` with `--python >=3.14`, one `--with name==version` for each of twelve dependencies (the CLI's two and the server's ten) and an `--exclude-newer` UTC timestamp, then `python ${CLAUDE_PLUGIN_ROOT}/bin/python-harness-mcp`. The pins sit in `.mcp.json` because twelve of them would make a shebang line much longer than the 127 bytes that Linux kernels before 5.1 read; the shebang of `bin/python-harness-data` carries six pins and is longer than 127 bytes too, as the data commands section says. As with the CLI launcher, `uv tool run` builds an isolated environment from those arguments alone and adopts nothing from the directory it starts in. The launch names `bin/python-harness-mcp` by path, so Python puts `bin/` first on `sys.path`, and a module in the project's directory cannot shadow `python_harness` or `mcp`.

The pins fix the versions of those twelve packages. For the packages those twelve depend on, the timestamp stops `uv` from choosing a release uploaded after it. The pins select versions and do not verify hashes. `tests/plugin/test_mcp_json.py` compares the pins with `pyproject.toml` and the repository's `uv.lock`. It also starts the server from a directory holding a decoy `pyproject.toml`, `.venv`, `python_harness` package and `mcp.py`, and fails if any decoy runs or if the server lists anything but the eight tools.

Measured once on one machine, when the server had only the two documentation tools, it took 6.12 s from process start to its tool listing with an empty `uv` cache and about 2.2 s with a warm one.

When the tools are missing from a session, the server did not start. Check the plugin's Errors tab in `/plugin` and the server in `/mcp`.

### The project tools

`survey`, `gate`, `collect_python_facts`, `map_python_calls`, `check_citations` and `plan_review_surface` read one project: the directory in `CLAUDE_PROJECT_DIR`, which `.mcp.json` passes to the server through `env`. No tool takes another root. Every path input is relative to that directory. An absolute path outside it, a `..` path that leaves it and a symlink that points outside it are tool errors, and a directory input skips entries that resolve outside it. When `CLAUDE_PROJECT_DIR` is unset, empty, relative or names no directory, these six return a tool error and the documentation tools still work.

Each tool returns one JSON document as its text result. `plan_review_surface` runs `git` to list the files a diff changed, and `gate` runs the project's checks through `uv`. Every project tool runs `uv workspace list` to find the workspace members. `gate` is the one project tool registered without the read-only hint, because it runs the project's own tools.

`gate` runs ruff check, ruff format check, ty and pytest. Both ruff checks report and never fix: `ruff check` runs with `--no-fix`, so a project whose ruff config sets `fix = true` keeps its files as they were, and the violations show in the report. When the project has no ruff config, it uses a ruff config packaged with the plugin. When the project has no ty config, it runs ty with a ty config packaged with the plugin. The gate document says where each config came from in `ruff_config_source` and `ty_config_source`: `repository` for the project's own, `fallback` for the packaged one and `defaults` for neither. `survey` reports the ruff config and the ty config it found: a `ty.toml` in the project root, or a `[tool.ty]` table in `pyproject.toml`.

When the project does not declare ruff, `gate` runs it as `uvx ruff@<version>`. The version is the plugin option `ruff_version`, which defaults to `0.16.9`, the ruff that this repository's `uv.lock` pins and that accepts the packaged ruff config. An unpinned `uvx ruff` resolved to 0.16.0 on one machine, which rejects that config (`unknown field output-prefer-rule-codes`), so both ruff checks exited 2. A project that declares ruff runs the ruff in its own environment, and the option does not apply. Change the option when a project's own ruff config needs a different ruff, for example a setting that 0.16.9 does not know. Claude Code stores the value per user, and `.mcp.json` passes it to the server as `PYTHON_HARNESS_RUFF_VERSION`; `python-harness inspect gate` reads the same variable. The value is three numbers joined by dots, like `0.16.9`. An unset or empty variable, or a `${...}` that Claude Code did not expand, means the default. Any other value is a tool error from `gate` that names the option, and no check runs. The option is user configuration, not a tool argument: no tool argument selects a command, a path or a config file, and `gate` still takes no arguments.

#### Workspace diagnostics

Every project tool's document says how the project's source roots were found. The tools run `uv workspace list --paths --offline --color never` in the project root and give it 5 seconds. Each workspace member contributes its `src` directory, or the member directory when it has no `src`. A module is named from the deepest source root that holds its file, or from the project root when no source root does.

When `uv` is not on `PATH`, exits with an error, times out, lists no members, lists a relative path or lists a path outside the project root, the project root's `src` directory is the only source root (when it exists) and the reason is listed in `fallback_diagnostics`.

The diagnostics hold `source_roots`, `fallback_diagnostics` and `unindexed_packages`. `unindexed_packages` lists each imported package that has a directory under a source root or the project root and no Python module the tools read, with its `name` and its `directory`. The diagnostics are under `workspace` in every project tool's document: at the top level for `survey`, `gate`, `plan_review_surface` and `check_citations`, and in the envelope of the two budgeted tools.

#### Detail and budget

`collect_python_facts` and `map_python_calls` take two more parameters.

| Parameter | Values | Default |
| --- | --- | --- |
| `detail` | `full`, `summary` or `counts` | `summary` |
| `budget` | An estimate of the response size in tokens, at least 256 | 4000 |

A `budget` below 256 is a tool error. The response is an envelope:

| Field | Holds |
| --- | --- |
| `detail` | The level of the document under `result`: the level that fit, which is not always the one asked for. |
| `budget` | The budget the call used. |
| `tokens` | The estimated size of the whole response. |
| `truncated` | `true` when `result` leaves items out or when `degraded` is `true`. |
| `degraded` | `true` when the requested `detail` did not fit the budget and the tool stepped down from `full` to `summary` to `counts`. |
| `result` | The document. |
| `workspace` | The workspace diagnostics. |

`full` is every fact (`collect_python_facts`) or every reference (`map_python_calls`) for the requested paths. `summary` holds `counts`, the highest-ranked modules (at most 20), for `map_python_calls` also `top_referenced_symbols` (at most 20), and a `narrowing` entry with the arguments for a `full` call. `counts` holds totals only. When even `counts` does not fit the budget, the call is a tool error.

### The documentation tools

`search_python_docs` and `read_python_docs` request `docs.python.org` over HTTPS and no other host. They do not follow redirects, so a redirect to another host comes back as a tool error. `tests/test_server.py` asserts both. Inventories and pages are cached in memory for up to 24 hours and nothing is written to disk. A call that takes longer than 45 seconds ends with a tool error. Those limits and the others are fields of `src/python_harness/documentation/settings.py`, and an environment variable named `PYTHON_HARNESS_DOCS_<FIELD_NAME>` overrides one.

## Hooks

Both hooks run `bin/python-harness hooks <event> || exit 1`, so Claude Code only ever gets exit code 0 or 1 from them. On exit 1 it shows a hook-error notice and the session or the Bash call goes on. That covers a payload a handler cannot read, a usage error, and a failure before the CLI starts: `uv` missing from `PATH` (127 from `env`), or `uv` unable to build the environment. The `|| exit 1` is there for that last case. Claude Code reads exit code 2 from a PreToolUse hook as "block this call", `uv` exits 2 for some of its own errors, such as finding no Python 3.14 while downloads are turned off, and the launcher itself maps no exit codes. `tests/plugin/test_launcher.py` runs both commands from `hooks/hooks.json` against a failing `uv` and fails if any other code comes out.

### SessionStart: the toolchain briefing

On every session start, resume, `/clear` and compaction, the hook adds a short Markdown briefing to Claude's context. It covers:

- the project root;
- the dependency files (`uv.lock`, `poetry.lock`, `pdm.lock`, `pixi.lock`, `Pipfile.lock`, `requirements.txt`);
- the Python pin (`.python-version`), `requires-python`, and the `.venv` interpreter, plus whether it runs a different minor version than the pin;
- ruff: the config file, its `extend` chain (each target shown as written; `${VAR}` and `~` are expanded only to find the file) and the effective settings. Rule selection is layered the way ruff layers it: a child `select` starts over, and a child `extend-select` re-enables the parent's ignored codes it covers. A parent ignore broader than the child's selector is still listed as written;
- ty: its config and settings;
- the test suite: the pytest config file by pytest's own precedence, plugins (`pytest-*`, `hypothesis`, `coverage`), tox or nox, and the test directories;
- the declared tools' commands, as `uv run <tool>` (PEP 621, PEP 735, uv and Poetry dependency tables are read);
- the `uv run python` rule.

The search boundary is the nearest directory holding `.git` (or else a `pyproject.toml`) at or above the session's directory. The project root is the nearest `pyproject.toml` inside that boundary. Tool configs and the pin are searched from the root up to the boundary, nearest first. The lock, the dependency files and `.venv` are searched only up to the uv workspace root, and only when `[tool.uv.workspace]` there lists the project as a member and does not exclude it. So a member sees the workspace's lock and `.venv`, and a standalone project nested in a uv repository does not. Nothing above the boundary is read, and a ruff `extend` target that resolves outside it, directly or through a symlink, becomes a problem line and is not opened; the exception is a file the search itself finds inside the boundary, which is read even when it is a symlink that points outside. User-level configs such as `~/.config/ruff/ruff.toml` are not read either, so a missing project config reads "no project config found" rather than "defaults".

The scan only reads files: no subprocess, no network, nothing written. A file that cannot be read becomes a "problem" line instead of a failure. Config values, versions and file paths read from the repository appear in code spans that the text cannot close, with whitespace collapsed and a cap of 240 characters; the root path, test plugin names and parser error messages are plain text with whitespace collapsed, so repository text cannot start a line of its own. The whole briefing is capped at 9,000 characters; Claude Code's limit is 10,000.

### PreToolUse: the interpreter note

When a Bash command runs `python`, `python3`, `python3.X`, `python3.Xt` or `python2` by bare name, the hook returns `additionalContext` and no permission decision. Per the hooks reference, Claude reads that note next to the tool result, and your permission rules and prompts apply as usual. The command is never blocked. The note says the result may be incorrect, because plain python can pick a different interpreter or packages than the project environment, and lists each call with its `uv run python` rewrite:

```text
Note from the python-harness plugin: this command ran plain `python3`, which can pick a different interpreter or packages than the project environment, so its result may be incorrect. Run Python with `uv run python`, and rerun it that way if the result matters:
- `python3 -m pytest` -> `uv run python -m pytest`
```

The command is parsed with tree-sitter-bash, so a bare name counts anywhere it is the command word: lists and pipelines, subshells, `$(...)`, backticks, and the bodies of conditionals, loops and functions. Up to 10 calls are listed.

- **Bare names only.** `/usr/bin/python3`, `.venv/bin/python`, `sudo python3`, `env python3` and `bash -c "python3 ..."` get no note. Neither do `uv run python`, `which python3` or `command -v python`.
- **Always `uv run python`.** The rewrite drops a version suffix (`python3.14t x` becomes `uv run python x`). It is the same in a Poetry, PDM or Pipenv project, where `uv run` can create its own `uv.lock` and `.venv` (inferred from uv's project behavior, not tested here).
- **Heredocs.** tree-sitter puts the `-` of `python3 - <<EOF` inside the heredoc, so that call is listed as `python3` -> `uv run python`.
- **The `if: "Bash(*python*)"` filter.** It keeps the hook from even starting for Bash commands that do not mention python. A warm run costs about 150 ms. On the first run `uv` builds the launcher's environment; the SessionStart hook (300 s timeout) usually does that first.

Try it by hand:

```sh
printf '%s' '{"hook_event_name":"PreToolUse","cwd":".","tool_name":"Bash","tool_input":{"command":"python3 -m pytest"}}' \
  | bin/python-harness hooks guard-python
printf '%s' "{\"hook_event_name\":\"SessionStart\",\"cwd\":\"$PWD\"}" | bin/python-harness hooks session-start
```

## The launcher

`bin/python-harness` is a Python script. Its first line runs it through `uv tool run`, with the Python version and one `--with name==version` per runtime dependency pinned on that line. It uses `uv tool run` and not `uv run`, because `uv run` adopts the `.venv`, `pyproject.toml` and `uv.toml` of the directory it is called from, and that directory is the project under review. The script finds the plugin from its own path (`bin/..`), puts the plugin's `src` on `sys.path` and calls the CLI, so the CLI's exit codes pass through. `uv` builds the environment in its own cache on the first run and reuses it afterwards. Python caches bytecode in `__pycache__` directories beside the plugin's sources.

The pins select versions and do not verify hashes. `tests/plugin/test_launcher.py` compares them with `pyproject.toml` and the repository's `uv.lock`, and fails when they differ.

Nothing is checked before the CLI starts:

| Problem | What you see |
| --- | --- |
| `uv` is not on `PATH` | `env` prints `'uv': No such file or directory` and exits 127 |
| `uv` cannot build the environment (no network on the first run, no Python 3.14) | `uv`'s own error and exit code |

`uv tool run` puts its environment's `bin` first on `PATH` and sets `UV`. `inspect gate` removes both, and an inherited `VIRTUAL_ENV` with that virtualenv's `bin`, before running the reviewed project's tools. It runs them through `uv run --isolated` with caches and bytecode writing turned off, so the gate leaves no lockfile, `.venv` or cache behind. Some build backends still write into the tree (setuptools writes `*.egg-info`). The gate reports any path that appeared in `created_paths` and never deletes anything.

Command groups load only when they run, so a hook never imports the `inspect` commands, and the interpreter hook never imports the session scan.

## The data commands

`bin/python-harness-data <subcommand>` runs one of four commands, and each prints one YAML report with `schema_version`, `command`, `arguments`, `result` and `caveats`. With no subcommand, or one it does not know, it prints a usage line to stderr and exits 2. Claude Code puts the plugin's `bin/` on the Bash tool's `PATH`, so it runs as a bare command.

| Subcommand | Arguments | What it reports |
| --- | --- | --- |
| `alert-budget` | `--events`, `--prevalence`, `--recall` and `--fpr`, all required; `--budget`, `--cost-fn` and `--cost-fp` | The expected alert load, precision and cost of a detector at one prevalence. |
| `paired-compare` | A CSV or Parquet `results` file, with `--old` and `--new` naming the 0/1 outcome columns; `--key`, `--level` (0.95), `--resamples` (20000) and `--seed` (42) | A paired pass/fail comparison of two configurations on the same tasks. |
| `profile-data` | `profile PATH`, with `--key` repeated for a composite key; `join LEFT RIGHT`, with `--key` repeated and required | The schema, nulls, distinct counts and key check of a Parquet or CSV file, or the observed cardinality of `LEFT` joined to `RIGHT`, read with DuckDB. |
| `size-check` | `dense --rows --cols`; `pairwise --n`; `embeddings --n --dim`; `sparse --rows --cols --nnz`; `join --left-matches --right-matches`; `fits --configs --folds` | Size arithmetic before the work runs: bytes, rows and fit counts. `dense`, `pairwise`, `embeddings` and `sparse` take `--dtype` (`float64`), and `sparse` takes `--index-dtype` (`int32`); `fits` takes `--repeats` (1) and `--seconds-per-fit`. |

The launcher is a Python script whose first line runs it through `uv tool run`, as `bin/python-harness` does, with `--python >=3.14`, an `--exclude-newer` timestamp and one `--with name==version` for each of duckdb, msgspec, numpy, polars, pyyaml and scipy. That first line is 216 bytes. Linux kernels before 5.1 cut a shebang line at 127 bytes, so on Linux this launcher needs kernel 5.1 or later. `bin/python-harness` and `bin/python-harness-mcp` do not carry those six packages. The pyproject lists the same six under the `data` extra.

## Limitations

- As of 0.1.0, the server and both hooks have not been run inside a live Claude Code session. The tests run the hook handlers and both launch commands directly and call the tools through an MCP client. Three things in particular are unconfirmed: that Claude Code expands `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PROJECT_DIR}` in `.mcp.json`, that it names the tools `mcp__plugin_python-harness_python-harness__<tool>`, and that `pylens` on Haiku can drive its three tools. If the name form is wrong, `pylens` starts without them.
- The six project tools are plain synchronous functions, which `mcp` 2.3.0 (the pinned version) runs on a worker thread. In `tests/tools/test_concurrent_calls.py`, a `search_python_docs` call returned while a `collect_python_facts` call was held open on a FIFO, so on that version a slow project call did not delay a documentation call. That test uses an in-memory client. Nothing has been observed over stdio, which is how Claude Code talks to the server.
- The six project tools cannot be pointed at a sub-project. They read `CLAUDE_PROJECT_DIR` and take no other root, and from a parent directory they would resolve the sub-project's imports against the wrong root. To review a project nested in a larger repository, start Claude Code inside it.
- A review's citations can be re-checked only by calling `check_citations`. No shell command does it. After editing `PYTHON-REVIEW.md` or `REFACTOR-PLAN.md`, ask Claude Code, in a session started in the project with the plugin enabled, to call `check_citations` on the file.
- No test sends a real request to `docs.python.org`. All HTTP in the tests is faked.
- Each `gate` check runs in its own session, and the server does not stop its checks when it shuts down. A check still running when the MCP server is terminated keeps running, and the plugin no longer enforces its 600-second timeout. This was reproduced by terminating a process that was running the gate. It has not been observed through a stdio server.
- The `ruff_version` option has not been set through Claude Code's option dialog, and the Claude Code documentation does not say what `${user_config.ruff_version}` expands to when the user never set it. The server treats an unset, empty or unexpanded value as the default, and the tests cover those three forms with the environment variable set by hand.
- There is no Windows launcher. The plugin needs a POSIX system.

## Develop

The plugin is a member of the repository's uv workspace, the `python-harness-plugin` package. It has no lint, type or test configuration of its own: the root `.ruff.toml`, `.ty.toml` and `.pytest.toml` apply. Run the repository's commands from the repository root:

```sh
make setup    # once: install the pre-commit hook and sync the workspace
make check    # the gate: sync the locked environment, run pre-commit, then scripts/quality.sh
make format   # let the formatters fix what they can
make lint     # report only
uv run pytest plugins/python-harness/tests   # this plugin's tests alone
```

`make lint` runs ruff, mdformat on the root Markdown, `ty`, the whole pytest suite, and `claude plugin validate --strict` for each plugin and for the marketplace, so `claude` has to be on `PATH`. [CONTRIBUTING.md](../../CONTRIBUTING.md) has the rest.

The pins are in two places. Line 1 of `bin/python-harness` has the CLI's two dependencies, and the `args` of `.mcp.json` have those two plus the server's ten. When `uv.lock` moves one of them to a new version, put that version wherever the package is pinned; `tests/plugin/test_launcher.py` and `tests/plugin/test_mcp_json.py` fail while they differ. Move the `--exclude-newer` timestamp in `.mcp.json` forward when a pin needs a release uploaded after it.

With the plugin loaded, the interpreter note fires on your own Bash calls here too: run Python as `uv run python`.
