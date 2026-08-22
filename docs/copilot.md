# Running under GitHub Copilot CLI

mightymodels targets Copilot CLI as its first harness. The skills are standard `SKILL.md`
directories, the agents are Copilot-format `.agent.md` files, and the plugin manifests are
readable by the CLI. This page records what the CLI actually does with each piece, so you can
tell a packaging problem from a harness problem.

## Install as a plugin

```text
copilot plugin install <owner>/mightymodels
```

The CLI accepts a repo slug, a full URL, or a `repo:subdirectory` path, and it understands
repositories carrying a `.claude-plugin/` directory with a Claude plugin manifest, which is what
this repo ships. A marketplace flow also works:
`copilot plugin marketplace browse <owner>/mightymodels` reads the `marketplace.json` here.

Skills distributed through a plugin are managed through the plugin: uninstalling the plugin
removes them, and you cannot delete an individual plugin skill in place.

## Install by hand

If you prefer a personal install, or your plugin surface is restricted:

```sh
./scripts/install-copilot.sh          # copy skills and agents into ~/.copilot
./scripts/install-copilot.sh --link   # symlink instead; a git pull updates in place
./scripts/install-copilot.sh --uninstall
```

Copilot CLI loads personal skills from `~/.copilot/skills` and `~/.agents/skills`, and project
skills from `.github/skills`, `.claude/skills`, or `.agents/skills` inside a repo. The script
uses `~/.copilot` for both skills and agents and touches only names that exist in this repo, so
it will not clobber unrelated skills you keep there.

## How skills fire

Copilot selects a skill from your prompt and the skill's frontmatter description, and every
description in this repo is written as that retrieval surface: trigger phrases, boundaries, and
the negative space ("not for X"). You can always bypass selection by naming the skill with a
slash, `/agents-assemble`, `/prune-ticket`, `/whats-broken`.

The trigger datasets under `evals/datasets/<skill>/trigger.yaml` exist for this harness
specifically. They pair should-trigger prompts with near-misses, including the sprint/Jira
collision pair, and they ship without an executor because triggering is retrieval-specific; wire
them to your own oracle and assert the should-trigger queries rank the skill in the top k.

## Agents

The four workers are `.agent.md` files with Copilot frontmatter: `name`, `description`, `model`,
`tools` (Copilot tool names such as `view`, `edit`, `execute`), and `disable-model-invocation`
where relevant. A plugin can carry agent directories, but harness versions differ in whether
plugin agents surface automatically, and a `customAgents.defaultLocalOnly: true` setting will
filter non-local agents on purpose. If the workers do not appear after a plugin install, the
install script's copy into `~/.copilot/agents` is the reliable path; check with `/agents` in a
session.

## Model ids

The pins in this repo are Copilot model ids: `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`,
`claude-opus-5`, `sonnet-5`. Three places carry them, in priority order: a ticket's
`subagent-models` block (read at dispatch, wins), the `.agent.md` pins (headless fallback), and
the defaults recorded in `skills/prepare-handoff/references/ticket-schema.md` (what
prepare-handoff writes into new tickets). If your organization exposes different ids, adjust the
schema defaults once and new tickets inherit them; the agent pins matter only when no ticket
answers.

## Tool permissions

None of the skills pre-approve tools. The SKILL.md format supports an `allowed-tools` key that
bypasses confirmation prompts, and this repo deliberately does not use it: a skill that silently
green-lights `bash` is an injection amplifier, and the loop's own review stack would flag that
pattern in anyone else's code. Approve tools per session like you would for any agent work.

## Hooks

Not shipped yet. The designed hook layer (session covenant injection, verification gates at
agentStop, preCompact ticket snapshots) is Copilot-hook shaped and will land as JSON configs
plus scripts; until then, the loop runs on skills and agents alone, and `hooksmith` can build
repo-specific hooks independently.

## Known limits

VS Code does not read Claude-format plugin manifests, so treat this repo as CLI-first; in VS
Code, the hand-install path still gets you the skills and agents it supports. Slash invocation
and description-based selection both depend on your CLI version behaving as GitHub's current
docs describe; if a skill will not fire, `/skill-name` is the diagnostic that separates
retrieval trouble from a loading problem.

## Claude Code parity

The same tree installs as a Claude Code plugin (`/plugin marketplace add`, then
`/plugin install mightymodels@mightymodels-marketplace`). Skill frontmatter carries nothing Claude
rejects, and the Copilot-specific agent keys are ignored there. The model pins are the one thing
you may want to edit, as above.
