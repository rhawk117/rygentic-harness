# Running under Claude Code

mightymodels is a Claude Code plugin living under `plugins/mightymodels/`. The skills are
standard `SKILL.md` directories, the seven workers are Claude Code subagent files under
`plugins/mightymodels/agents/`, and the plugin manifest plus the repo-root marketplace manifest
are what the plugin loader reads. This page records what Claude Code actually does with each piece,
so you can tell a packaging problem from a harness problem.

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
removes everything it installed. Nothing in this repo writes outside its own tree, so there is
no per-machine state to clean up beyond the plugin itself; ticket state lives in each target
repository's `.mightymodels/` directory and belongs to that repository, not to the plugin.

## How skills fire

Claude Code selects a skill from your prompt and the skill's frontmatter description, and every
description in this repo is written as that retrieval surface: trigger phrases, boundaries, and
the negative space ("not for X"). You can always bypass selection by naming the skill with a
slash. Plugin skills surface as `/mightymodels:agents-assemble`, and the short form
`/agents-assemble` works whenever the name is unambiguous in your session.

The trigger datasets under `evals/datasets/<plugin>/<skill>/trigger.yaml` exist for this selection layer.
They pair should-trigger prompts with near-misses, and they ship without an executor because
triggering is retrieval-specific; wire them to your own oracle and assert the should-trigger
queries rank the skill in the top k.

## Agents

The seven workers are markdown files under `plugins/mightymodels/agents/` with Claude Code
subagent frontmatter:
`name`, `description`, `model`, and `tools`. Claude Code discovers plugin agents by convention,
so no manifest key names them; check with `/agents` in a session after installing.

Two frontmatter details are easy to misread:

- `tools` lists canonical Claude Code tool names (`Read`, `Write`, `Edit`, `Bash`, `Grep`,
  `Glob`). An explicit list is a cap, not a suggestion.
- `tools: []` means a tool-less agent. Omitting the key entirely means the agent inherits every
  tool in the session, which is the opposite of what an advisory worker like wingman wants, so
  wingman pins the empty list on purpose.

## Model ids

The pins in this repo are Claude model ids: `claude-haiku-4-5`, `claude-sonnet-5`,
`claude-opus-5`. Three places carry them, in priority order:

1. A ticket's `subagent-models` block in `.mightymodels/<slug>/ticket.yml`, read at dispatch
   time. This wins whenever a ticket is active.
2. The `model` pins in the agent files, which are only the fallback for headless runs where no
   ticket answers.
3. The defaults recorded in
   `plugins/mightymodels/skills/prepare-handoff/references/ticket-schema.md`, which are what
   `prepare-handoff` writes into new tickets.

If your organization exposes different ids, adjust the schema defaults once and new tickets
inherit them; the agent pins matter only when no ticket answers.

## Tool permissions

None of the skills pre-approve tools. The SKILL.md format supports an `allowed-tools` key that
bypasses confirmation prompts, and this repo deliberately does not use it: a skill that silently
green-lights `Bash` is an injection amplifier, and the loop's own review stack would flag that
pattern in anyone else's code. Approve tools per session like you would for any agent work.

## Hooks

Not shipped yet. The designed hook layer (session covenant injection, verification gates at
Stop, PreCompact ticket snapshots) will land as a `hooks/hooks.json` at the plugin root plus
scripts; Claude Code merges plugin hooks with the ones in your settings files. Until then, the
loop runs on skills and agents alone, and `create-hooks` can build repo-specific Claude Code hooks
independently.

## Known limits

Whether plugin agents surface, and under which names, depends on your Claude Code version
behaving as the current docs describe. If a skill will not fire, the slash form is the
diagnostic that separates retrieval trouble from a loading problem: a skill that runs when named
but never self-selects has a description problem, and a skill the slash menu cannot find has a
loading problem. The ticket routing assumes dispatches can name the workers by their agent
names; if `/agents` does not list them, fix the install before debugging the loop.
