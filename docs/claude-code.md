# Running under Claude Code

mightymodels is a Claude Code plugin living under `plugins/mightymodels/`. The skills are
standard `SKILL.md` directories, the twelve workers are Claude Code subagent files in three
folders under `plugins/mightymodels/agents/`, and the plugin manifest plus the repo-root
marketplace manifest are what the plugin loader reads. This page records what Claude Code
actually does with each piece, so you can tell a packaging problem from a harness problem.

## Install as a plugin

```text
/plugin marketplace add <owner>/rygentic-harness
/plugin install mightymodels@rygentic-harness
```

The marketplace add step reads `.claude-plugin/marketplace.json` from this repository; the
marketplace is named rygentic-harness and mightymodels is one of its plugins. The install step
loads the plugin's skills, agents, and manifests into your session. Skills distributed through a
plugin are managed through the plugin: uninstalling the plugin removes them, and you cannot
delete an individual plugin skill in place.

To check a working copy before publishing changes, run validation from the repository root:

```text
claude plugin validate ./ --strict
```

Strict mode checks skill and agent frontmatter and flags unrecognized keys, which is the fastest
way to catch a typo before a session ever loads the file.

## Updating and uninstalling

Updates flow through the marketplace: refresh the marketplace and reinstall the plugin, and the
new skill and agent versions replace the old ones in your next session. Uninstalling the plugin
removes everything it installed.

The plugin's state lives in two places. A ticket's files (`ticket.yml`, the plan, briefs,
snapshots, review runs and archives) are in the target repository's `.mightymodels/` directory,
at the git toplevel. The rows (tickets, tasks, the verification contract and its receipts,
review runs, ledgers, crashouts and closings) are in `mightymodels.db` in the plugin data
directory, the one Claude Code names in `CLAUDE_PLUGIN_DATA`. That file is outside every repository and serves all
of them, and the `scout-spool` directory beside it holds scout reports waiting to be stored.
[docs/state.md](state.md) has the detail.

## How skills fire

Claude Code selects a skill from your prompt and the skill's frontmatter description, and every
description in this repo is written as that retrieval surface: trigger phrases, boundaries, and
the negative space ("not for X"). You can always bypass selection by naming the skill with a
slash. Plugin skills surface as `/mightymodels:agents-assemble`, and the short form
`/agents-assemble` works whenever the name is unambiguous in your session.

No trigger datasets ship in this repository, so nothing here measures selection. A skill that
runs when named but never self-selects has a description problem; see Known limits.

## Agents

The twelve workers are markdown files under `plugins/mightymodels/agents/`, in the folders
`triage`, `workers` and `review`, with Claude Code subagent frontmatter:
`name`, `description`, `model`, `effort`, and `tools`, plus `skills` and `maxTurns` where a
worker needs them. Claude Code discovers plugin agents by convention, so no manifest key names
them, and it makes the folder part of the agent type: a worker is dispatched as
`mightymodels:<folder>:<name>`, for example `mightymodels:triage:code-scout`. Check with
`/agents` in a session after installing.

Three frontmatter details are easy to misread:

- `tools` lists canonical Claude Code tool names (`Read`, `Write`, `Edit`, `Bash`, `Grep`,
  `Glob`). An explicit list is a cap, not a suggestion.
- `tools: []` means a tool-less agent. Omitting the key entirely means the agent inherits every
  tool in the session, which is the opposite of what an advisory worker like wingman wants, so
  wingman pins the empty list on purpose.
- An `Agent(...)` entry in `tools` names the workers a worker may dispatch, but Claude Code
  lets a subagent dispatch any agent type. The plugin's dispatch hook is what holds a worker to
  that list.

## Models

The pins in this repo are Claude Code model aliases: `haiku`, `sonnet`, `opus` and `fable`.
Every worker but the two reviewers runs on one fixed model, and three places carry it:

1. The `model` pin in the worker's agent file.
2. A ticket's `subagent-models` block in `.mightymodels/<slug>/ticket.yml`, which the primary
   reads at dispatch time and passes as the `Agent` tool's `model` parameter. The `ticket`
   tool's `validate` refuses a ticket whose value differs from the fixed one.
3. The routing table in `plugins/mightymodels/src/mightymodels_plugin/core/routing.py`, which
   is what the `ticket` tool writes into new tickets and validates against.

A reviewer's model comes from the review run: `sonnet` for a quick review, `opus` for standard
and deep, and `fable` for the one reviewer a run's override moves. Which model an alias resolves
to is Claude Code's decision in your session, not the plugin's.

## Tool permissions

A skill's `allowed-tools` key pre-approves the tools it lists while the skill runs. The skills
here use it for two kinds of tool only: `AskUserQuestion`, and the plugin's own state tools
(`mcp__plugin_mightymodels_state__...`). None pre-approves `Bash`, `Edit` or `Write`: a skill
that silently green-lights `Bash` is an injection amplifier, and the loop's own review stack
would flag that pattern in anyone else's code. Approve those per session like you would for any
agent work.

## Hooks

`plugins/mightymodels/hooks/hooks.json` registers seven hooks on five events, each a command that
runs the plugin's CLI against the state database; Claude Code merges them with the ones in your
settings files. Every entry has a timeout of 10 seconds.

- `SessionStart` exports the plugin data directory to the session's commands.
- `PreToolUse` on `Agent`, the dispatch hook, denies a dispatch by one of the plugin's workers
  outside the workers its agent file allows, and a dispatch of the intern unless the task started
  for it owns exactly one file. Every other caller is judged as the main thread. While the
  checked-out branch has one unclosed ticket, its dispatch of the engineer or the architect is
  denied until a task is in progress, and its dispatch of the architect or the wingman is
  answered `ask` while a task is blocked or failed and the ticket's `auto-escalate` is off.
- `PreToolUse` on `Edit`, `Write` and `Bash`, the main-thread hook, acts only on a caller that
  is none of the plugin's workers, and only while the checked-out branch has one unclosed
  ticket. An `Edit` or `Write` outside the ticket directories is answered `ask`, so you approve
  it in the permission prompt. Under `claude -p` there is no prompt and the call is refused, even
  with the tool in `--allowedTools`: `scripts/live-plugin-check.sh --require-state` shows it. No
  other permission mode was tested. A `git push` is denied, with what is still open, until no plan
  task is open and every live contract command has a passing landing-phase receipt at HEAD.
- `SubagentStop` on the two scouts and `PostToolUse` on `SubagentHandback` leave a scout's
  report in the spool for search.
- `SubagentStop` on the engineer, the architect and the intern is the completion gate. It holds
  a stop once while a plan task the worker started has no DONE half naming a commit, or a
  residual it started lacks its commit, its receipts or a diff inside its owned files.
- `PreCompact` writes the snapshot of the ticket on the checked-out branch before a compaction.

With no unclosed ticket on the branch, the main thread's rules give no decision, as if the
plugin were not installed; with several they give none either and show one line naming them.
When the state cannot be read, a dispatch of the engineer, the architect or the intern and a
`git push` are refused, an `Edit` or `Write` goes ahead with one line saying it was not checked,
and every other hook does nothing but say why on standard error. The push rule reads the
command's shell words, so `git -C <dir> push` and a push after `&&` are held and
`echo "git push"` is not. A command that pushes without the words `git` and `push`, such as a
git alias or a script, is not seen.
`plugins/mightymodels/references/state/runtime-layout.md` has what each reads and writes.
`create-hooks` can still build repo-specific Claude Code hooks independently.

## The vibe-code plugin

`plugins/vibe-code/` ships ten skills and no agents: `build-a-loop`, `create-agents-md`,
`create-hooks`, `create-instructions`, `create-mcp`, `create-skill`, `create-subagent`,
`humanizer`, `plan-plugin`, and `promptlint`. Install it with
`/plugin install vibe-code@rygentic-harness`.

The skills call a `vibe-code` CLI to validate what they write: `skill validate`,
`hook validate` and `hook test`, `subagent validate`, `instruction validate`,
`mcp scaffold` and `mcp validate`, and `plugin validate`, `plugin render`, and `plugin inventory`.
Claude Code puts a plugin's `bin/` directory on the Bash tool's `PATH` while the plugin is
enabled, so the skills run `vibe-code` by name.

The CLI needs [uv](https://docs.astral.sh/uv/) on your `PATH`. Without it the launcher exits with
status 127. `bin/vibe-code` is a Python script whose shebang runs `uv tool run`, not `uv run`,
because `uv run` adopts the `.venv`, `pyproject.toml` and `uv.toml` of the caller's working
directory. The dependency versions are pinned on line 1 of `bin/vibe-code` and in
`bin/vibe-code.cmd`, which `tests/test_shim.py` checks against `uv.lock`. The pins select versions
and do not verify hashes. Four commands (`skill validate`, `hook validate`, `subagent validate`
and `mcp validate`) call `claude plugin validate --json`, so they need a Claude Code that has
that flag. Windows was exercised by hand on one machine and no automated test covers it; one
thing to know is that PowerShell starting `vibe-code.cmd` lets `cmd.exe` re-read the command line,
so an unquoted argument holding `&` runs what follows it. The details are in
[the plugin README](../plugins/vibe-code/README.md).

The plugin's eval cases are in `plugins/vibe-code/evals`. Running them with
`claude plugin eval` costs money and is not part of the quality gate.

## Known limits

Whether plugin agents surface, and under which names, depends on your Claude Code version
behaving as the current docs describe. If a skill will not fire, the slash form is the
diagnostic that separates retrieval trouble from a loading problem: a skill that runs when named
but never self-selects has a description problem, and a skill the slash menu cannot find has a
loading problem. The ticket routing assumes dispatches can name the workers by their agent
types, `mightymodels:<folder>:<name>`; if `/agents` does not list them, fix the install before
debugging the loop.
