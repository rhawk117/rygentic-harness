# rygentic-harness

This is all of the agentic tooling I use with Claude Code every day, kept in one repository and
installable as a plugin marketplace. There are four plugins. mightymodels carries a ticket from
the first investigation through review and cleanup. vibe-code builds and checks the skills, hooks
and agents that everything else is made of. python-harness reviews Python the way I would.
terraform-harness gives Claude Code the tools to read, check and change Terraform.

The repository runs on an "everything is a plugin" mindset, an idea I took from the DeepSeek
harness. The root owns the marketplace manifest and the shared quality gate. Every capability
ships as a plugin under `plugins/`, one directory each, with its own manifest, skills and agents.
terraform-harness is the exception: it lives in its own repository,
[cc-terraform-harness](https://github.com/rhawk117/cc-terraform-harness), and its marketplace
entry points at a release tag there.

## What's in the marketplace

| Plugin | Version | What you get | Details |
| --- | --- | --- | --- |
| mightymodels | 1.0.0 | Takes a piece of work from the first question to a merged PR, with nineteen skills, twelve worker agents, seven hooks and a state server | [README](plugins/mightymodels/README.md) |
| vibe-code | 0.4.0 | Eleven skills for building and tuning Claude Code skills, subagents, hooks, rule files, MCP servers, loops and plugins, plus a CLI that validates what they write | [README](plugins/vibe-code/README.md) |
| python-harness | 0.2.0 | Eight Python skills, four agents, a ty language server, two hooks, a CLI and an MCP server | [README](plugins/python-harness/README.md) |
| terraform-harness | 0.1.0 | Four Terraform agents, five skills, three hooks, the terraform-ls language server and an MCP server that checks modules, digests plans and looks up provider schemas | [README](https://github.com/rhawk117/cc-terraform-harness#readme) |

No plugin depends on another. Install the ones you want.

## Prerequisites

Check this table before you install anything. Without `uv`, a plugin installs fine and then its
CLI, hooks or server will not start.

| You need | Needed by | Why |
| --- | --- | --- |
| Claude Code | all four | They are Claude Code plugins. The vibe-code validators also need a `claude plugin validate` that accepts `--json`: 2.1.289 has the flag and 2.1.205 does not. |
| [uv](https://docs.astral.sh/uv/) on your `PATH` | all four | The CLIs, hooks and MCP servers start through `uv tool run`, or `uv run` in terraform-harness. |
| Python | all four | Nothing to install by hand, because uv fetches it. mightymodels, python-harness and terraform-harness ask for 3.14 or newer, vibe-code for 3.12 or newer. |
| Linux, macOS or WSL | mightymodels, python-harness, terraform-harness | mightymodels starts through `sh` and `bash` scripts, the python-harness launcher does not run on native Windows, and the terraform-harness hooks start through a `sh` script. |
| `git` | mightymodels, python-harness, terraform-harness | mightymodels keeps a ticket's files in `.mightymodels/` at the git toplevel, and its hooks look up the ticket for the checked-out branch. python-harness runs `git` to list the files a diff changed, and terraform-harness does the same when it traces a change's impact. |
| `terraform`, `tflint` and `terraform-ls` on your `PATH` | terraform-harness | The hooks and the MCP server run `terraform` and `tflint`, and terraform-ls is the language server. The session-start hook names any that are missing, and the checks that need a missing one are skipped. |
| [GitHub CLI](https://cli.github.com/) (`gh`), logged in | mightymodels | Issues, pull requests and CI watching. Without it, `open-ticket` keeps the issue body as a file and `stick-the-landing` stops after showing you the `gh pr create` command. |
| `jira` CLI | mightymodels, optional | Only when you pick Jira as a ticket's tracker. Without it you get a draft file. |
| Network access | all four | A package index, the first time uv builds each environment. The two python-harness documentation tools also read `docs.python.org`. |

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
/plugin install terraform-harness@rygentic-harness
```

The first line reads this repository's `.claude-plugin/marketplace.json`. Each line after it
installs one of the plugins that file lists. [docs/claude-code.md](docs/claude-code.md) covers
model ids, agent discovery and validation.

## The plugins

### mightymodels

This is the plugin I cannot live without. It is built from the failures of spec-driven
development, and it is oriented around human-in-the-loop decision making: scouts fetch the facts,
the decisions come to me, and a task closes only when a command proves it. It has cut my token
consumption, the model gets more of the work right, and it has changed the way I work with AI. I have no
numbers for that yet. Evaluating this release is what I am doing next.

It is also the biggest of the four and the marketplace's first plugin. One unit of work gets one
`.mightymodels/<slug>/` directory and one `ticket.yml` carrying its scope and model routing. The
work then moves through fixed stages: investigate, write down what is known, open a ticket, plan,
sprint, land the PR, review. Each stage has one job, writes one artifact, and reads `ticket.yml`
before it does anything else.

When the work merges, `/prune-ticket` compresses the directory into a 30-line archive and deletes
it. The unit of deletion is the unit of work, so working state never outlives the ticket that
produced it. None of it is ever tracked by git, by design: spec-driven development leaves slop
artifacts all over a repository, and they confuse the agents that read them later.

People ask me about the names, which are odd on purpose: `ask-an-adult`, `merge-vader`,
`stick-the-landing`, `crashout`. They are supposed to be memorable. `/crashout` is for when the
agent has earned a rant. It writes the rant down verbatim and checks whether the same failure has
happened before.

One of my favorite features is `baton-pass`. With AI it is hard to walk away from a session
without a penalty. `baton-pass` writes down the facts that live nowhere else and prints the
opening prompt for the next session, so the next one picks up where I stopped.

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

Eight skills, four agents, a language server, two hooks, a CLI and an MCP server for Python
projects. The skills are `build-web-service`, `enterprise-design`, `design-persistence` and
`design-tests` (a service track that hands work along in that order), `data-engineering` and
`data-analysis` (a data track whose two skills hand work to each other), `automate-task` (a
script track) and `tactical-slop-review`, which every track hands to once code exists. Claude
offers a skill when the request matches its description, and you can run any of them as
`/python-harness:<name>`. `tactical-slop-review` reviews a PR, a branch or a codebase, writes
`PYTHON-REVIEW.md` or `REFACTOR-PLAN.md`, and never edits code. The four agents are `pylens` and
`pep-talk`, which are read-only and run on Haiku, `reviewer`, which cannot edit files, and
`test-engineer`, which writes the tests it is assigned. The `ty` language server gives Claude Code
type diagnostics for Python files and downloads ty through `uv` on its first start.

Two hooks come with it. One briefs each session on the project's Python toolchain. The other adds
a note when a Bash command runs plain `python` where `uv run python` was meant. Neither blocks a
command. The MCP server has eight tools: two read standard-library documentation from
`docs.python.org`, and six read the project Claude Code was started in.

> [!WARNING]
> As of 0.2.0 the skills, the agents, the language server, the hooks and the server have not yet
> been run inside a live Claude Code session. The
> [python-harness README](plugins/python-harness/README.md#limitations) lists what is unconfirmed.

### terraform-harness

Four agents, five skills, three hooks, a language server and an MCP server for Terraform and IaC
repositories. The agents are `terraform-advisor`, which gives a second opinion on a Terraform
call, `terraform-author`, which writes Terraform inside a scope it is handed,
`terraform-edit-reviewer`, which checks a just-edited module for drift, and
`terraform-researcher`, which answers one question about a repository. The skills are
`check-module`, `explain-plan`, `look-up-schema`, `review-module` and `trace-change-impact`.

The hooks format a `.tf` or `.tfvars` file after Claude writes it, report `terraform validate`
and `tflint` findings after Claude reads one, and report the terraform, tflint and terraform-ls
versions when a session starts. The MCP server describes modules, runs fmt, validate and tflint,
digests plans, traces a change's impact and looks up provider schemas.

The plugin is developed in [cc-terraform-harness](https://github.com/rhawk117/cc-terraform-harness),
not under `plugins/`, and the marketplace installs its `v0.1.0` tag. Its
[README](https://github.com/rhawk117/cc-terraform-harness#readme) lists every agent, skill and
hook.

## Layout

```text
plugins/          one directory per plugin; each carries its own manifest and skills
  mightymodels/   the dev loop: nineteen skills, twelve worker agents
  vibe-code/      authoring skills and the `vibe-code` CLI: eleven skills, no agents,
                  with its own tests and eval cases
  python-harness/ Python engineering: eight skills, four agents, a ty language server, hooks,
                  the `python-harness` CLI and an MCP server, with its own tests
docs/             human documentation for the harness and the mightymodels plugin
scripts/          the quality gate (`quality.sh`), checkout setup, and a log helper
.claude-plugin/   the rygentic-harness marketplace manifest
```

## Documentation

| Page | What it covers |
| --- | --- |
| [plugins/mightymodels/README.md](plugins/mightymodels/README.md) | The mightymodels plugin: requirements, the loop, skills, workers, hooks, state |
| [plugins/vibe-code/README.md](plugins/vibe-code/README.md) | The vibe-code plugin: install, skills, CLI, launcher |
| [plugins/python-harness/README.md](plugins/python-harness/README.md) | The python-harness plugin: install, skills, agents, language server, hooks, server, launcher, limitations |
| [cc-terraform-harness README](https://github.com/rhawk117/cc-terraform-harness#readme) | The terraform-harness plugin: agents, skills, hooks, MCP server |
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

A plugin developed in another repository gets a `url` source instead, the way terraform-harness
does: the repository's `https://` clone URL, pinned to a release tag and that tag's commit. Use
`url` rather than a `github` source, because a `github` source is cloned over SSH and fails with
`Permission denied (publickey)` for anyone without a GitHub SSH key. `claude plugin validate`
checks that entry's shape and does not fetch the plugin, so the gate here never runs against its
files.

## Contributing

`make check` is the gate a change has to pass. It syncs the locked environment, runs pre-commit,
and runs `scripts/quality.sh`. Read [CONTRIBUTING.md](CONTRIBUTING.md) before you open a PR.

Evals are separate from the gate. Some mightymodels skills keep dated eval results in
`plugins/mightymodels/skills/<skill>/evals/`. The vibe-code eval cases live in
`plugins/vibe-code/evals` and run with `claude plugin eval`, which costs money.

For anything sensitive, see [SECURITY.md](SECURITY.md).
