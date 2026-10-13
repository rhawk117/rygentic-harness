---
name: create-skill
description: >-
  Interactive Claude Code skill creator, scenario-first. Use it to create, write, scaffold, improve, test or evaluate a skill (SKILL.md plus optional scripts, references and assets). It asks where the skill ships (personal, project, plugin), sets invocation and tool pre-approvals by checkbox, takes a plain description of what the skill does and what problem it solves, proposes a name and use-case scenarios the user accepts or rejects, records them as claude plugin eval cases with graders before the skill exists, builds the skill conversationally without inferring answers, validates it, then runs the cases with and without the plugin and iterates on the report.
when_to_use: >-
  Use when the user says "turn this workflow into a skill", "make Claude know how to do X", "package this procedure", "write a SKILL.md", or asks how skill frontmatter, triggering, tool pre-approval or skill evals work, even without the word "skill".
---

# Create a Claude Code skill

A skill is a procedure or body of knowledge Claude loads on demand: by matching the description against what the user typed, or by `/name`. It costs only its description until it loads, which makes it the right home for anything not needed on every turn and the wrong home for anything that must be enforced. Skills fail in two silent ways: a description that never matches a real prompt, so the skill exists and is never used; and a body that restates what Claude already does, so runs with and without it look the same. This skill is built around catching both, which is why the use-case scenarios are written and accepted before the skill is, and why every evaluation has a no-plugin baseline.

Ask every question in the interview with the `AskUserQuestion` tool: single select, multi select, or free text through its other option. The rule for the whole workflow: anything the user has not said is a question, not an assumption. When the user has answered everything upfront, use those answers and skip the question, but say which default you took for anything they did not cover.

| phase                 | what happens                                                                  | user involvement                                            |
| --------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------- |
| A. Scope              | where the skill ships                                                         | one question                                                |
| B. Constraints        | invocation flags, tool pre-approvals, MCP tools, optional frontmatter         | up to four checkbox questions                               |
| C. Describe and route | what it does, what problem it solves; is a skill the right mechanism          | free text, one confirmation, one routing decision if needed |
| D. Name and scenarios | suggested name; use-case scenarios accepted, rejected, refined                | checkbox loop until accepted                                |
| E. Resources          | research first? scripts? assets?                                              | three questions                                             |
| F. Rigor and record   | none / smoke test / boil the ocean; eval cases written before the skill       | one question, then sign-off on the record                   |
| G. Research           | only if agreed in E                                                           | results shown                                               |
| H. Layout             | proposed tree                                                                 | one confirmation                                            |
| I. Build              | description, then body section by section, asking every open question         | conversational                                              |
| J. Validate           | `vibe-code skill validate`, `claude plugin validate`                 | results shown                                               |
| K. Evaluate           | cost ceiling, models, permissions; `claude plugin eval`; improve loop         | a question per setting, review per run                      |
| L. Hand off           | paths, how to invoke, what is unverified                                      | summary                                                     |

Read `references/skill-facts.md` once at the start: install locations, frontmatter fields, flags, substitutions and what the host actually does are there, and a field or behavior outside it is unverified. Read `references/eval-methodology.md` in phases F and K.

## Phase A: scope

Single select, because it fixes paths and what else has to change:

- personal: `~/.claude/skills/NAME/SKILL.md`. Visible in every project this user opens, only to this user. Keep it project-agnostic.
- project: `.claude/skills/NAME/SKILL.md`. Versioned, shared with everyone who works in the repository. Claude Code also finds skills in `.claude/skills/` of every parent directory up to the repository root, so in a monorepo say which level it belongs at. `--add-dir DIR` loads `DIR/.claude/skills/` for one session.
- plugin: `skills/NAME/SKILL.md` in the plugin root. Ships wherever the plugin is enabled, as `/plugin-name:NAME`; the manifest needs no change for skills. Plugins are cached at install, so develop with `claude --plugin-dir ./DIR` and run `/reload-plugins` in the session after adding a component (`/reload-skills` for a skills directory created mid-session).

Check that the target does not already hold a skill of the intended name where it would shadow or be shadowed: enterprise beats personal, personal beats project, and a plugin skill is namespaced so it never collides. Verify by asking Claude "What skills are available?"; for a plugin, `claude plugin details <plugin>` also lists the component inventory.

Cloud and browser sessions may not run bundled scripts (unverified), so for a script-dependent skill say so in `compatibility` and keep a prose fallback.

## Phase B: constraints, by checkbox

**B1. Invocation.** Multi-select, defaults both checked:

- Claude may load it on its own when the description matches (`disable-model-invocation: false`)
- a human may run it with `/NAME` (`user-invocable: true`)

Unchecking the first gives a human-only skill (release procedures, anything destructive); unchecking the second gives a model-only skill hidden from the `/` menu. Both unchecked is a skill nobody can invoke; refuse it. The flags are native Claude Code keys and accept `true`, `false`, `yes`, `no`, `on`, `off`, `1` and `0`. For a human-only skill ask for the `argument-hint` text shown after `/NAME` and write it as a quoted string, `argument-hint: "[file]"`. Only claude.ai upload and packaging reject that key, so mention the restriction only if the user plans to upload.

**B2. Tool pre-approvals.** Scan the repository for what the workflow will run (the runner in `pyproject.toml`, `package.json` scripts, a `Makefile`, CI steps) and present candidates as `allowed-tools` rules: `Bash(uv *)`, `Bash(git status *)`, `Edit`, `WebFetch(domain:docs.example.com)`, `mcp__SERVER__TOOL`. Multi-select, nothing pre-checked, plus "none, prompt as usual". Explain that these are pre-approvals for the turn that invokes the skill, not restrictions, that a skill can grant itself broad access so the list should be as narrow as the procedure allows, and that a bundled script needs its interpreter listed too (`Bash(python3 *)`). The plugin this skill ships in sets none; the user's skill sets only what they picked. `vibe-code skill validate` checks the rule grammar.

**B3. MCP tools.** Read `.mcp.json` at the plugin root or project root and list the servers found. Multi-select the servers the skill will use and, for each, the tools. Claude names them `mcp__SERVER__TOOL`, and `mcp__plugin_PLUGIN_SERVER__TOOL` for a server a plugin declares. A skill cannot declare an MCP server; it can only reference one configured elsewhere, so the body names the server and says what to do when it is absent. If the workflow needs a server nobody has configured, route to `create-mcp`, or ask whether to add it to `.mcp.json` first. The eval phase mocks the server (see below).

**B4. Optional frontmatter.** Multi-select, nothing pre-checked; each choice goes into the draft and the question is skipped for fields the user never needs:

- `arguments`: named positional arguments the body can refer to by name
- `paths`: glob patterns that limit automatic activation to matching files
- `context: fork` with `agent`: run the skill as the prompt of a fresh subagent (see C2)
- `hooks`: hooks registered while the skill is active (see C2)

## Phase C: describe and route

**C1. Describe.** Ask for two things in the user's own words: what the skill should do, and what problem it solves (what goes wrong today without it). Restate each as one sentence and confirm. The problem statement is what the graders are written against later, so push on vagueness: "helps with tests" is not a problem; "Claude writes tests that mock the database instead of using the fixtures in `tests/conftest.py`" is.

**C2. Route.** Decide whether a skill is the right mechanism, using the table in `references/skill-facts.md`:

- a persona, delegation target, own tool set, own model or own MCP server: a subagent at `agents/<name>.md`, `create-subagent`
- something that must happen at a lifecycle point whether or not Claude follows the skill: a hook in `hooks/hooks.json`, `create-hooks`; a hook that should apply only while this skill is active goes in the `hooks` frontmatter field, and the hook itself is written with `create-hooks`
- always-on steering for certain files with no procedure to run: `CLAUDE.md` or a rules file, `create-instructions`; a plugin cannot ship rules
- a task that needs its own context window and has explicit steps: keep the skill and add `context: fork` with an `agent` type; the subagent does not see the conversation, so the body must stand alone

When another mechanism fits better, say so with the concrete reason (for example: "you want this to run after every edit whether or not Claude remembers; a skill only runs when it loads"), name the sibling skill, and offer a single select: switch to it, or "Don't care, build it as a skill even though I'll get worse results". Honor the override without further argument and record it in the hand-off.

## Phase D: name and scenarios

**D1. Name.** Propose one kebab-case name (1 to 64 characters, lowercase letters, digits, single hyphens; it becomes the directory name and must equal `name`), plus two alternatives, and ask. Prefer a verb or the artifact (`review-migration`, `release-notes`) over a topic (`database`).

**D2. Use-case scenarios.** Generate four to six scenarios. Each is one realistic prompt a user would actually type, the state it starts from (files, branch, failing test), and what a good outcome looks like in one line. Present them as a multi-select: accept the ones that ring true, reject the rest, and give the user a free-text way to add or rewrite. Regenerate the rejected slots from the feedback and repeat until every slot is accepted or the user says enough. The accepted scenarios are the eval cases; nothing else is. Each case must grade an output; do not write a case whose only job is to test triggering.

## Phase E: resources

Three questions, each with a short reason attached to the recommendation:

- **Research first?** Should docs, standards, an API reference or example repositories be consulted before writing, and captured as `references/` files the skill reads on demand? Recommend yes when the workflow depends on facts that change (CLI flags, API shapes, framework conventions) and no when the user's own description is the whole source. Ask for URLs or paths if yes.
- **Scripts?** Does any step deserve deterministic code Claude runs instead of re-deriving (validation, transformation, a check with a clear pass or fail)? List the candidates you see in the scenarios and let the user pick. A bundled script is one fewer thing every future run can get wrong.
- **Assets?** Templates, boilerplate, fixtures that end up in outputs. List candidates, let the user pick.

## Phase F: rigor and the record

Single select, in the user's terms:

1. None, fully give into the vibes: no evaluation; the user reads the skill and says yes.
2. Smoke test: one run per arm per case (`--runs 1`), the with and without transcripts read side by side; iterate until the with run has no immediate issue and beats the baseline.
3. Boil the ocean: the default three runs per arm or more, every grader scored, aggregated per arm with spread.

For 2 and 3, read `references/eval-methodology.md`, then write one case per accepted scenario under `evals/` at the plugin root, before any part of the skill exists. A case is `evals/<case>/prompt.md` or `case.yaml` plus `graders/*.md`; the files live at the plugin root, not inside the skill. Copy from `assets/eval-case/`, or run `claude plugin eval init --bare <case>` for a blank case. Ask the user to run `claude plugin eval init` themselves if they want Claude to propose graders in an interview.

- The prompt body is sent to Claude exactly as written, and the run cannot ask questions, so put everything you would otherwise ask the user in the body after the task, under `Everything you'd otherwise ask me:`. Phrase the task as the user would type it, without naming the skill.
- Write at least one grader per case, or the case fails to load: one on the result (the final message or a produced file) and one on the steps taken. A grader that checks the skill loaded is `tool_used` with `tool: Skill` and an `input_match` naming the skill; keep it inside a case that also grades an output.
- A case needing fixture files or a git repository gets a `case.yaml` with `context.scaffold_script` (a Bash script in the case directory) and `context.add_dirs` for read-only directories. The script runs only when the user passes `--scaffold`, so tell them to pass that only for a suite they wrote.
- A skill that calls MCP tools is evaluated with mocks at `evals/mocks/<server>/<tool>.md`, one file per tool, where the body is what the tool returns.
- A skill that is not in a plugin has no `claude plugin eval` target. Offer to wrap it in a plugin, or compare by hand with the skill set to `"off"` in `skillOverrides` for the baseline; `skillOverrides` does not affect plugin skills.

Grader types, for the cases you write (full options in `references/eval-methodology.md`):

| type          | options                               | passes when                                                                      |
| ------------- | ------------------------------------- | -------------------------------------------------------------------------------- |
| `regex`       | `pattern`, `flags`, `match`, `target` | the JavaScript regex is found in the target                                      |
| `tool_used`   | `tool`, `input_match`, `min`, `max`   | calls to `tool` whose JSON input matches `input_match` number between min and max |
| `tool_order`  | `before`, `after`                     | both tools were called and the first `before` call precedes the first `after`    |
| `file_exists` | `path`, `exists`                      | a file Claude created matches the glob, or none does with `exists: false`        |
| `llm`         | `criteria`, `focus`                   | a judge model votes PASS in at least two of three votes                          |

`target` (regex) and `focus` (llm) take `last_message` (the default), `trace`, `files` (paths created, not contents), `{ source: file, path: <path> }` for one produced file's contents, or `mock_calls`. Every grader also takes `weight` and `arm` (`with-only` or `both`). Prefer `regex` over a produced file for long output and keep `llm` for short answers with a rubric of concrete PASS and FAIL conditions. The graders are not custom code: when a result needs a command's outcome, have the prompt write it to a file and grade that file.

Show the cases and ask for sign-off; a grader changed after generation is changed with a note saying why. At rigor 1 write no case, because a case with no grader fails to load; put the accepted scenarios in the hand-off so a later session can pick evaluation up.

## Phase G: research

Only if agreed in E. Use `WebFetch` and the repository; write findings as `references/<topic>.md`, each starting with a line saying what it covers and when the skill should read it, and mark each claim doc-verified or inferred. Show the user what was found before building, because the research decides what the body can assert.

## Phase H: layout

Propose the tree and ask:

```
NAME/
  SKILL.md
  references/   only if G produced something or E asked for it
  scripts/      only the scripts chosen in E
  assets/       only the assets chosen in E
```

Empty directories are not created. Eval cases are not part of the tree: they live in `evals/` at the plugin root. Keep SKILL.md under 500 lines and move detail into the files it points at, with a sentence saying when to read each; keep references one level deep.

## Phase I: build, conversationally

Draft from `assets/SKILL.template.md`; delete the optional lines the user did not choose. The order matters because each part constrains the next:

1. **Description.** It is the entire trigger surface, so write it to match the accepted scenarios' prompts: name the situations, the phrasings and the artifacts, key use case first, under 1024 characters. Put extra trigger phrases and example requests in `when_to_use`; the two are joined in the skill listing and truncated at 1,536 characters together. Every enabled skill's name and description sit in context on every turn, and when the listing overflows its budget (1% of the context window) descriptions are dropped, so keep them tight; `claude plugin details <plugin>` shows what a plugin costs. Show it and ask.
2. **Body, one section at a time.** For each step, write it and, when a question arises (which command, which path, what to do when a check fails, how strict to be), stop and ask it rather than choosing. Put the reason next to each instruction Claude might be tempted to skip. Write guidance that should hold throughout a task as a standing instruction, because the rendered body stays in context and is not re-read, and put the most important instructions first, because only the start of a skill survives compaction. Reach bundled files through the skill-directory variable and use the string substitutions and dynamic context injection described in `references/skill-facts.md`; those are replaced in SKILL.md itself, so show them literally only in a reference file.
3. **Scripts and assets** chosen in E, each tested before it is shown (run it with `--help` and a sample input); a script that has not been run is not done.
4. **Whole-file preview**, then one question to write. Do not write before it.

## Phase J: validate

Run `vibe-code skill validate <dir>` and show the output; add `--strict` to fail on warnings. It runs `claude plugin validate` first and then the checks that one misses: frontmatter keys, `name` against the directory and pattern, description length, flags and the dead flag pair, the `allowed-tools` rule grammar, every referenced resource existing, files nothing points at, and the line budget. It exits 0 on a pass, 1 on findings, 2 when it could not check. The `vibe-code` launcher is on the PATH while this plugin is enabled, because it lives in the plugin's `bin/`; the user installs nothing. For a plugin skill also run `claude plugin validate <plugin-dir> --strict`, then confirm the skill is visible as described in phase A.

## Phase K: evaluate

Skip at rigor 1. Otherwise ask, one question each:

- **Runs and baseline.** `--runs` per case per arm, and `--ablation none` while iterating on graders versus the default with and without comparison. Show the arithmetic: cases times runs, doubled by the baseline, plus three short judge calls per `llm` grader per run.
- **Cost ceiling.** `--max-cost-usd`, a ceiling on the list-price estimate, checked before each run starts. There is no run-count cap. If it is hit, the command exits 2 with partial results; say so rather than reporting them as a result.
- **Models.** `--model` for the agent under test and `--judge-model` for `llm` graders; the case's `model` key sets the first per case. Take any model id, pin it, and say the report records the models used.
- **Permissions.** `allowed_tools` in each `prompt.md` plus `--allow-tools`, for example `Write Edit "Bash(npm test *)"`; there is no allow-all flag and a run never stops to ask. Say what each grant allows, that `Bash` runs in an OS sandbox, and that a bundled script needs its interpreter granted or every case that runs it fails for a reason unrelated to the skill.

Show the exact command and its cost estimate, and run `claude plugin eval <plugin-root>` with the agreed flags only after the user confirms: every run and judge call is billed to their account. The run writes `evals/results/<timestamp>/report.html` and `aggregate-result.json`; `--output-dir` moves them. Read the report and the grader explanations, then apply the improve loop in `references/eval-methodology.md`: description if the skill did not load (with `tune-skill-descriptions` when a rewrite alone does not fix it), body if it loaded and was ignored, a script if every run repeated the same work, the grader if it was wrong. Re-run within the ceiling until the stop condition for the chosen rigor holds or the ceiling is hit, and say which happened.

## Phase L: hand off

The paths written; how to invoke (`/NAME`, `/plugin-name:NAME` for a plugin skill, or the phrasings the description targets); for plugin scope the reload step; how to re-run `claude plugin eval` and where the report goes; anything routed away in C or overridden; and everything unverified: whether scripts run in cloud sessions, what a human-only skill does inside an eval prompt, and any claim in a `references/` file marked inferred.
