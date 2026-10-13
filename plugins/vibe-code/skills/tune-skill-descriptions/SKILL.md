---
name: tune-skill-descriptions
description: >-
  Tunes Claude Code skill descriptions so the right skill loads for the right request. It runs the vibe-code tune loop over a labeled trigger set: real headless Claude Code routing (or fresh subagents) judges which skills each request loads, Claude proposes one rewrite at a time, the loop keeps a rewrite only when held-out validation requests improve, and the winners are written back into the SKILL.md files.
when_to_use: >-
  Use when skills misfire, never load, load for the wrong request or steal each other's requests, or when the user wants to evaluate, test, optimize or rewrite SKILL.md descriptions or skill routing, even if they only say Claude keeps ignoring their skill.
---

# Tune skill descriptions

The `vibe-code tune` CLI owns the loop and you supply the judgment. It keeps the state, splits the trigger set into train and validation, decides what to work on next, scores every round, and accepts a rewrite only if the held-out validation score improves, or holds steady while the training score improves. You write the candidate descriptions. Claude Code itself judges which skills each request loads; fresh subagents can stand in when real routing is unavailable.

The `vibe-code` launcher is on the PATH while this plugin is enabled. Every command below starts with `vibe-code tune`. A refusal exits 1 with the reason on stderr; exit 2 means a file could not be read or written.

## 1. Gather the inputs

- **Skills in scope.** Directories that hold `<skill>/SKILL.md` folders, or individual `SKILL.md` paths. Tune the skills that compete with each other together; a description only means something relative to its neighbors.
- **A trigger set.** A YAML or JSON list of realistic requests, each with the skills that should load (an empty list means none should). If the user has none, build one with them following `references/trigger-sets.md` and get their sign-off before starting, because the loop optimizes toward whatever the set says.

Run the model-free collision check first. It flags descriptions that share their distinctive vocabulary, the most common reason one skill steals another's requests, and it costs nothing:

```bash
vibe-code tune lint --skills <paths...>
```

## 2. Choose the judge, agree the cost, then start

| Judge | What it measures | Cost |
|---|---|---|
| `claude-code` (default) | Real routing: one headless `claude -p` session per request, recording the skills Claude Code loads | One short session per request, every evaluation, billed like any Claude Code use |
| `subagent` | A proxy: fresh subagents read the descriptions and say which skills they would load | One subagent per 12 requests, every evaluation |

A run is one baseline evaluation plus up to 8 rounds, each re-evaluating the whole trigger set, so 40 requests means up to 360 sessions. A routed session measured between $0.002 and $0.02 on Claude Code 2.1.296, depending on prompt caching. Tell the user that estimate before starting and adjust with `--max-rounds` and `--patience`. `--model` pins the model the sessions route with; without it they use the user's default.

```bash
vibe-code tune init --skills <paths...> --triggers <trigger-set.yaml> --judge <claude-code|subagent>
```

State lives in `.skill-tuning/` in the working directory: `state.json` resumes the run, and `status` shows where it stands. Leave the folder alone while a run is open.

## 3. Run the loop

Repeat `next` and act on the `kind` it prints until it says `done`.

```bash
vibe-code tune next
```

### kind: route

The CLI judges by real routing. It writes each skill as a stub (name, description, `when_to_use`, `disable-model-invocation` and `argument-hint`, never the body or tool grants) under `.claude/skills/` in a temporary project, then runs one headless session per request with the request on stdin. Each session:

- loads project settings only, so the user's personal skills, plugins, hooks and MCP servers stay out;
- has the `Skill` tool and nothing else, and stops after one turn;
- keeps no session history.

Claude Code's built-in skills still compete with the stubs, which is what a real session looks like; the report lists them under "Competing skills".

Run it with a generous timeout, up to 10 minutes:

```bash
vibe-code tune route
```

Progress is saved after every packet of 12 requests. If the command is interrupted or a session fails, run `route` again and it continues where it stopped, then run `next`.

A failure names its cause:

- **"Invalid API key" or another login message:** the headless sessions cannot authenticate. Have the user run `claude` once in a terminal and log in.
- **"staged skills were not listed":** Claude Code did not pick up the stubs, so its routing could not be measured. Report the message and the Claude Code version (`claude --version`) to the user.
- **"timed out":** a session ran past `--timeout` seconds (240 by default). Rerun `route`, or start over with a longer `--timeout` and `--force`.
- **`claude` not on PATH:** pass `--claude <path>` to `route`.

When real routing stays unavailable, start again with `--judge subagent --force` and tell the user the scores are now a proxy.

### kind: judge

The output lists packet ids and packet file paths. For every packet, start a fresh subagent with the `Agent` tool and `subagent_type: general-purpose`, all in one message so they run in parallel. Tell each one to read its instructions in this skill's `references/judging.md`, at `${CLAUDE_SKILL_DIR}/references/judging.md`, then its packet file at the given path, and to reply with JSON only.

Hand the packet paths over without opening the files. They contain the held-out validation requests, and you know which description is being tuned, so verdicts you wrote would score your intent instead of the text. For the same reason the subagents judge, not you.

Save each subagent's JSON answer to a file and submit it; submissions are safe in any order:

```bash
vibe-code tune submit --packet <packet_id> --answer <answer.json>
```

If the CLI rejects an answer, the message says why (a missing request key, an unknown skill name, a packet from a replaced run). Ask that subagent to correct its packet and resubmit.

### kind: propose

Write one new description for the named skill yourself, following `references/proposing.md`. The packet shows the current text, the skill's `when_to_use` (kept as it is; only `description` changes), the training requests it missed or wrongly claimed, earlier rewrites that were rejected, and any collisions. Save it as `{"description": "..."}` and submit:

```bash
vibe-code tune submit --packet <packet_id> --answer <proposal.json>
```

The CLI then has the candidate judged on train and validation together. Nothing it prints to you contains a validation request, which is what keeps the rewrites honest.

### kind: done

```bash
vibe-code tune report
vibe-code tune apply --dry-run
```

Show the user the report and the proposed changes. Write them into the `SKILL.md` files only after they agree:

```bash
vibe-code tune apply
```

`apply` replaces only the `description` value in each changed file's frontmatter, keeps line endings, and refuses a file whose description changed since `init`. Afterwards run `vibe-code skill validate` on each changed skill.

## What the scores mean

Each request scores the overlap between the skills that should load and the skills that did, so a correct "no skill" counts as a full hit. Scores from `claude-code` are what Claude Code did with the staged descriptions on the model the sessions ran on. Scores from `subagent` are a proxy, and an optimistic one: on one test library it scored vague descriptions about 0.83 where real routing scored 0.50. Say which judge produced the numbers.

A skill's name is part of what Claude Code routes on. If the baseline is already near 1.0 with vague descriptions, the names are doing the work and the run has little to tune; say so instead of spending rounds. Treat small gains as noise, prefer descriptions that say concretely what the skill does, and give `lint` collisions as much weight as the score. If the final report still lists collisions, point them out: that is where triggering is most likely to stay fragile.
