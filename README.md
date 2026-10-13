# rygentic-harness

This is all of the agentic tooling I use with Claude Code every day, kept in one repository and
installable as a plugin marketplace. There are three plugins. mightymodels carries a ticket from
the first investigation through review and cleanup. vibe-code builds and checks the skills, hooks
and agents that everything else is made of. python-harness reviews Python the way I would.

The repository runs on an "everything is a plugin" mindset, an idea I took from the DeepSeek
harness. The root owns the marketplace manifest and the shared quality gate. Every capability
ships as a plugin under `plugins/`, one directory each, with its own manifest, skills and agents.

## What's in the marketplace

| Plugin | Version | What you get | Details |
| --- | --- | --- | --- |
| mightymodels | 1.0.0 | A ticket-scoped development loop: nineteen skills, twelve worker agents, seven hooks and a state server | [README](plugins/mightymodels/README.md) |
| vibe-code | 0.4.0 | Eleven skills for building and tuning Claude Code skills, subagents, hooks, rule files, MCP servers, loops and plugins, plus a CLI that validates what they write | [README](plugins/vibe-code/README.md) |
| python-harness | 0.1.0 | A Python review skill, a read-only fact agent, two hooks, a CLI and an MCP server | [README](plugins/python-harness/README.md) |

No plugin depends on another. Install the ones you want.

## Prerequisites

Check this table before you install anything. Without `uv`, a plugin installs fine and then its
CLI, hooks or server will not start.

| You need | Needed by | Why |
| --- | --- | --- |
| Claude Code | all three | They are Claude Code plugins. The vibe-code validators also need a `claude plugin validate` that accepts `--json`: 2.1.289 has the flag and 2.1.205 does not. |
| [uv](https://docs.astral.sh/uv/) on your `PATH` | all three | The CLIs, hooks and MCP servers start through `uv tool run`. |
| Python | all three | Nothing to install by hand, because uv fetches it. mightymodels and python-harness ask for 3.14 or newer, vibe-code for 3.12 or newer. |
| Linux, macOS or WSL | mightymodels, python-harness | mightymodels starts through `sh` and `bash` scripts, and the python-harness launcher does not run on native Windows. |
| `git` | mightymodels, python-harness | mightymodels keeps a ticket's files in `.mightymodels/` at the git toplevel, and its hooks look up the ticket for the checked-out branch. python-harness runs `git` to list the files a diff changed. |
| [GitHub CLI](https://cli.github.com/) (`gh`), logged in | mightymodels | Issues, pull requests and CI watching. Without it, `open-ticket` keeps the issue body as a file and `stick-the-landing` stops after showing you the `gh pr create` command. |
| `jira` CLI | mightymodels, optional | Only when you pick Jira as a ticket's tracker. Without it you get a draft file. |
| Network access | all three | A package index, the first time uv builds each environment. The two python-harness documentation tools also read `docs.python.org`. |

> [!NOTE]
> vibe-code is the only plugin with a Windows launcher, `bin/vibe-code.cmd`. It was tried by hand
> on one Windows machine and no CI job covers it. The
> [vibe-code README](plugins/vibe-code/README.md#windows) has what was observed.

To work on the repository itself you also need Node 22 or newer, `make`, and the Claude Code CLI
at the version the gate was built against:

```sh
npm install -g @anthropic-ai/claude-code@2.1.285
```

## Install

```text
/plugin marketplace add rhawk117/rygentic-harness
/plugin install mightymodels@rygentic-harness
/plugin install vibe-code@rygentic-harness
/plugin install python-harness@rygentic-harness
```

The first line reads this repository's `.claude-plugin/marketplace.json`. Each line after it
installs one of the plugins that file lists. [docs/claude-code.md](docs/claude-code.md) covers
model ids, agent discovery and validation.

## The plugins

### mightymodels

This is the plugin I cannot live without. It is built from the failures of spec-driven
development, and it is oriented around human-in-the-loop decision making: scouts fetch the facts,
the decisions come to me, and a task closes only when a command proves it. It has cut my token
consumption, the model gets more of the work right, and it has changed the way I work with AI.

It is also the biggest of the three and the marketplace's first plugin. One unit of work gets one
`.mightymodels/<slug>/` directory and one `ticket.yml` carrying its scope and model routing. The
work then moves through fixed stages: investigate, write down what is known, open a ticket, plan,
sprint, land the PR, review. Each stage has one job, writes one artifact, and reads `ticket.yml`
before it does anything else.

When the work merges, `/prune-ticket` compresses the directory into a 30-line archive and deletes
it. The unit of deletion is the unit of work, so working state never outlives the ticket that
produced it.

It also has `/crashout`, for when the agent has earned a rant. It writes the rant down verbatim
and checks whether the same failure has happened before.

The [mightymodels README](plugins/mightymodels/README.md) has the loop diagram, every skill and
worker, the hooks and where the state lives.

### vibe-code

Skills for building the parts other plugins are made of: skills, subagents, hooks, rule files,
MCP servers, loops and whole plugins. There are eleven of them, and a `vibe-code` CLI that the
skills call to validate what they just wrote. It ships no agents.

It was called `ai-engineer` before 0.3.0. An install under the old name is not upgraded in place,
so remove it and install `vibe-code`.

The [vibe-code README](plugins/vibe-code/README.md) covers the skills, the CLI, the launcher and
Windows.

### python-harness

`/python-harness:what-would-ryan-say` reviews a PR, a branch or a codebase and writes
`PYTHON-REVIEW.md` or `REFACTOR-PLAN.md`. It never edits code, and it runs only when you type it.
It dispatches a read-only agent, `pylens`, which returns cited facts.

Two hooks come with it. One briefs each session on the project's Python toolchain. The other adds
a note when a Bash command runs plain `python` where `uv run python` was meant. Neither blocks a
command. The MCP server has six tools: two read standard-library documentation from
`docs.python.org`, and four read the project Claude Code was started in.

> [!WARNING]
> As of 0.1.0 the hooks and the server have not been run inside a live Claude Code session. The
> [python-harness README](plugins/python-harness/README.md#limitations) lists what is unconfirmed.

## Layout

```text
plugins/          one directory per plugin; each carries its own manifest and skills
  mightymodels/   the dev loop: nineteen skills, twelve worker agents
  vibe-code/      authoring skills and the `vibe-code` CLI: eleven skills, no agents,
                  with its own tests and eval cases
  python-harness/ Python review: one skill, one agent, hooks, the `python-harness` CLI
                  and an MCP server, with its own tests
docs/             human documentation for the harness and the mightymodels plugin
scripts/          the quality gate (`quality.sh`), checkout setup, and a log helper
.claude-plugin/   the rygentic-harness marketplace manifest
```

## Documentation

| Page | What it covers |
| --- | --- |
| [plugins/mightymodels/README.md](plugins/mightymodels/README.md) | The mightymodels plugin: requirements, the loop, skills, workers, hooks, state |
| [plugins/vibe-code/README.md](plugins/vibe-code/README.md) | The vibe-code plugin: install, skills, CLI, launcher |
| [plugins/python-harness/README.md](plugins/python-harness/README.md) | The python-harness plugin: install, hooks, server, launcher, limitations |
| [docs/workflow.md](docs/workflow.md) | The full mightymodels loop, stage by stage, with diagrams |
| [docs/skills.md](docs/skills.md) | Every mightymodels skill: what it does and when it fires |
| [docs/agents.md](docs/agents.md) | The twelve workers and how models get routed |
| [docs/state.md](docs/state.md) | The `.mightymodels/` directory and `ticket.yml` |
| [docs/claude-code.md](docs/claude-code.md) | Running under Claude Code |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each plugin, version by version |

## Adding a plugin

A new plugin is a directory under `plugins/` with a `.claude-plugin/plugin.json` naming it, plus
its `skills/` and `agents/`. Add a matching entry to the marketplace manifest and the rest is
automatic: `scripts/quality.sh` runs `claude plugin validate --strict` for every directory under
`plugins/` and for the marketplace root, which checks the manifests and the skill and agent
frontmatter.

## Contributing

`make check` is the gate a change has to pass. It syncs the locked environment, runs pre-commit,
and runs `scripts/quality.sh`. Read [CONTRIBUTING.md](CONTRIBUTING.md) before you open a PR.

Evals are separate from the gate. Some mightymodels skills keep dated eval results in
`plugins/mightymodels/skills/<skill>/evals/`. The vibe-code eval cases live in
`plugins/vibe-code/evals` and run with `claude plugin eval`, which costs money.

For anything sensitive, see [SECURITY.md](SECURITY.md).
