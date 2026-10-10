# vibe-code

Eleven skills for authoring Claude Code skills, subagents, hooks, rule files, MCP servers, loops and plugins, and for tuning skill descriptions, plus a small CLI that checks what they write. The name promises vibes; the CLI exists so that the output gets validated instead.

## Requirements

- A Claude Code whose `claude plugin validate` accepts `--json`. The CLI reads that report. Claude Code 2.1.289 has the flag; 2.1.205 does not.
- [uv](https://docs.astral.sh/uv/) on `PATH`.
- Python. uv fetches it, so nothing needs installing by hand. The launcher asks for 3.12 or newer.

## Install

```text
/plugin marketplace add <owner>/rygentic-harness
/plugin install vibe-code@rygentic-harness
```

The plugin was called `ai-engineer` before 0.3.0. An install under the old name is not upgraded in place: remove it, then install `vibe-code`.

While the plugin is enabled, Claude Code puts its `bin/` directory on the `PATH` of the Bash tool, so the skills call `vibe-code` by name.

## Skills

| Skill | Use it when |
| --------------------- | ------------------------------------------------------------------------------------------ |
| `build-a-loop` | You want an agent to keep working until a measurable condition holds; it writes a `LOOP.md` contract |
| `create-agents-md` | A repository needs an `AGENTS.md`, with an optional `CLAUDE.md` that imports it |
| `create-hooks` | You want a Claude Code hook built and tested, as a Python script |
| `create-instructions` | You want a rule file under `.claude/rules/`, or want to know why Claude ignores one |
| `create-mcp` | You want an MCP server in Python; it interviews you, then scaffolds the project and its `.mcp.json` |
| `create-skill` | You want a skill written from scenarios, with eval cases recorded before the skill |
| `create-subagent` | You want a subagent file built and validated |
| `humanizer` | Prose reads like AI-generated text and needs editing |
| `plan-plugin` | You want to plan a plugin; it ends in a phased plan and an empty plugin shell, never a build |
| `promptlint` | You are writing or reviewing a prompt for a coding agent |
| `tune-skill-descriptions` | Skills misfire or steal each other's requests; it tunes their descriptions against real Claude Code routing on a trigger set |

## CLI

`vibe-code <group> <command>`. The skills run these; you can run them yourself.

| Command | What it does |
| -------------------------------------------------- | -------------------------------------------------------------------------------- |
| `skill validate [--strict] SKILL_DIR` | Runs `claude plugin validate` on the skill, then the checks it misses |
| `hook validate [--strict] HOOKS_FILE` | Checks the schema of a `hooks.json` or settings file, runs `claude plugin validate`, then the checks both miss |
| `hook test SCRIPT PAYLOAD` | Pipes a payload into a hook script and checks the Claude Code output contract |
| `subagent validate [--strict] FILE` | Runs `claude plugin validate` on an agent file, then the checks it misses |
| `instruction validate [--strict] PATH` | Checks a `.claude/rules` file, or audits the instruction files of a project directory |
| `mcp scaffold [--template DIR] [--force] SPEC TARGET` | Renders an MCP server project and its `.mcp.json` shapes from an interview spec |
| `mcp validate --kind {plugin,project,user} [--check-command] [--strict] FILE` | Runs `claude plugin validate` on the servers, then the checks it misses |
| `plugin validate [--strict] PLAN` | Checks a plugin plan record |
| `plugin render [--force] PLAN TARGET` | Writes a plugin shell from a plan record |
| `plugin inventory [--out OUT] PLUGIN_DIR` | Records an existing plugin as a plan of built components |
| `tune [--state FILE] lint --skills PATH...` | Lists pairs of skill descriptions that share their distinctive vocabulary |
| `tune [--state FILE] init --skills PATH... --triggers FILE [--judge {claude-code,subagent}]` | Starts a description-tuning run from skills and a labeled trigger set |
| `tune [--state FILE] next`, `submit --packet ID --answer FILE`, `status` | Hands out the next work, takes an answer back, prints the stage and scores |
| `tune [--state FILE] route [--claude PATH]` | Judges the pending requests with one headless `claude -p` session each |
| `tune [--state FILE] report`, `apply [--dry-run]` | Prints the Markdown report; writes the tuned descriptions into the SKILL.md files |

Exit codes: the validators return 0 for a pass and 1 when a finding is an error, or a warning under `--strict`. They return 2 when they could not check: a file that cannot be read, `claude` missing from `PATH`, or a `claude plugin validate` that printed no JSON report. `hook test` returns 0 for a pass, 1 for a contract failure and 2 when the hook could not be run. `mcp scaffold` returns 0 once the project is written and 2 for a spec, template or target it rejects. `plugin render` returns 1 for a record or target it refuses and 2 when the record is unreadable or a write fails. `plugin inventory` returns 0 or 2. The `tune` commands return 0 on success, 1 when the tuner refuses an input or a step (the reason is on stderr) and 2 when a file cannot be read or written. Running `vibe-code` with no command prints the help and returns 2.

Four commands call `claude plugin validate --json` and fail with exit 2 on a Claude Code that lacks the flag: `skill validate`, `hook validate`, `subagent validate` and `mcp validate`. The other commands do not call it.

## Launcher

`bin/vibe-code` is a Python script whose first line is a shebang that runs `uv tool run` with the pins on that line:

```text
#!/usr/bin/env -S uv tool run --python >=3.12 --with msgspec==0.22.0 --with pyyaml==6.0.3 python
```

It does not use `uv run`. `uv run` adopts the `.venv`, `pyproject.toml` and `uv.toml` of the caller's working directory, so a project you open could substitute its own interpreter, packages or index for the pinned ones. `uv tool run` builds an isolated environment from the shebang line alone. The launcher sets `VIBE_CODE_PLUGIN_ROOT` and imports the CLI from `src/`. With `uv` missing from `PATH`, `env` exits with status 127.

The pins live in two places, line 1 of `bin/vibe-code` and `bin/vibe-code.cmd`, and `tests/test_shim.py` checks both against the versions in the repository's `uv.lock`. To change one, run `uv lock`, then edit the same version in both files. The lock's hashes are not enforced: the pins select versions and do not verify the downloaded artifacts.

`.gitattributes` keeps `bin/vibe-code` and `bin/vibe-code.cmd` on LF line endings, the form the repository's line-ending hook requires.

### Windows

`bin/vibe-code.cmd` runs the same `uv tool run` command for `cmd.exe`. This is what was observed on one machine, Windows 10.0.26200 with uv 0.10.4, driven through WSL interop on 2026-10-04. No automated test or CI job covers Windows.

- `vibe-code.cmd` under `cmd.exe` and Windows PowerShell 5.1, and the shebang under Git Bash, gave exit 0 for `--help` and exit 2 for an unknown argument. `mcp scaffold` wrote its 25 files and `plugin inventory` exited 0.
- The four commands that need `claude plugin validate --json` exited 2 with `claude plugin validate printed no JSON report`, because the Claude Code on that machine was 2.1.205, which has no `--json`.
- When PowerShell starts a `.cmd`, `cmd.exe` reads the command line again. An unquoted argument that holds `&` runs what follows it as a command: `vibe-code skill validate 'x&ver'` printed the Windows version. An argument with a space is quoted by PowerShell and arrives intact. Git Bash uses the shebang, which has no second read. Prefer Git Bash on Windows, or do not pass paths that hold `&`, `|`, `<`, `>`, `^` or `%`.

## What the CLI runs and overwrites

Most commands read files and print findings. Six do more:

- `hook test` runs the hook script you name, with the payload on stdin.
- `mcp validate --check-command` runs the configured command of each stdio server with `--help`, without a shell, to prove it resolves.
- `mcp scaffold --force` writes into a non-empty `TARGET` and removes `TARGET/src` before writing.
- `tune route` starts one headless `claude -p` session per trigger request, on your account and billed like any Claude Code use, in a temporary directory that holds stub skills (name and routing frontmatter only). The sessions load project settings only, have the `Skill` tool and nothing else, stop after one turn and keep no history.
- `tune apply` replaces the `description` value in the frontmatter of each changed SKILL.md, keeps everything else and the line endings, and refuses a file whose description changed since `tune init`. `tune init`, `next`, `submit` and `route` write the run state under `.skill-tuning/` in the working directory.
- `plugin render --force` rewrites the plan files of an existing plugin: `.claude-plugin/plugin.json` (keys the plan record does not model are kept), `README.md`, `PLAN.md` and `plugin-plan.json`. It deletes nothing.

Without `--force`, `mcp scaffold` refuses a non-empty `TARGET` and `plugin render` refuses a plugin that already has a manifest.

## Evals

`evals/` holds six cases for `claude plugin eval`: three for `create-mcp` and three for `plan-plugin`. Running them costs money and they are not part of the quality gate. This README states no results. The command, with a cost cap you choose:

```text
claude plugin eval plugins/vibe-code --ablation none --max-cost-usd <cap> --scaffold --allow-tools Bash Write Edit "WebFetch(domain:pypi.org)" "WebFetch(domain:files.pythonhosted.org)"
```

`--scaffold` runs the cases' scaffold scripts, which four of the cases have. `--allow-tools` grants the tools the cases list, since a run removes `Bash`, `Write` and `Edit` unless they are granted. The two `WebFetch` grants are there because `uv` needs PyPI inside the sandbox; drop them for an offline run. The first run asks whether to trust the plugin directory.

## Development

Tests are in `tests/` and run with the repository suite (`uv run pytest` from the repository root). `.python-version` here says 3.14, but the CLI source and tests must stay compatible with Python 3.12, and the second `ty` pass in `scripts/quality.sh` checks them at 3.12.

From the repository root, `make check` is the gate: it syncs the locked environment, runs pre-commit, then runs `scripts/quality.sh`. `claude plugin validate --strict plugins/vibe-code` is part of it. [CONTRIBUTING.md](../../CONTRIBUTING.md) has the rest.

## Layout

```text
.claude-plugin/plugin.json  the plugin manifest
bin/vibe-code               the launcher
bin/vibe-code.cmd           the launcher for cmd.exe
skills/                     the eleven skills
src/vibe_code_cli/          the CLI: one package per group, plus shared modules
tests/                      the CLI, launcher and eval-case tests
evals/                      six claude plugin eval cases
pyproject.toml              the vibe-code-plugin package, a uv workspace member
.python-version             3.14
```
