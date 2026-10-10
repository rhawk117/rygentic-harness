# Evaluation methodology

Read this in phase F, before writing eval cases, and again in phase K, before running them. `claude plugin eval` does the running, grading and reporting; this file explains the decisions you make around it.

## Requirements

Claude Code v2.1.269 or later (`claude --version`), and git 2.31 or later if git is installed. Every run and every judge grader is a real model call on the user's account, so say so before running anything. The first run against a plugin directory asks `Trust this plugin directory?`; the user answers it, because it is a trust decision about their machine.

## The three rigor levels, as the user chooses them

| level                              | what runs                                                                  | what is judged                                                                | when it stops                                                                         |
| ---------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| 1. None, fully give into the vibes | nothing                                                                    | the user reads the skill and says yes                                         | when the user says so                                                                 |
| 2. Smoke test                      | one run per arm per case: `--runs 1`                                       | you read the with and without transcripts side by side in the report          | the with run has no immediate issue and beats the baseline on every case, or the cost ceiling is hit |
| 3. Boil the ocean                  | the default three runs per arm, more with `--runs <n>`, baseline arm on    | every grader in every case, aggregated into a score per arm with spread across runs | every case's with-arm score meets the rate the user agreed, with a positive `Δ`, or the cost ceiling is hit |

## The no-plugin baseline

A high score alone does not show the skill helped, because Claude might do as well without it. By default each case runs twice over: the with-arm has the plugin loaded and the without-arm has no plugin at all. The summary shows `WITH`, `W/OUT` and `Δ`, their difference, which is what the plugin contributed. A case that scores 1.0 in both arms is not evidence for the skill.

- The baseline removes the whole plugin, not one skill. If the plugin has several skills, the comparison measures all of them together.
- `--ablation none` runs one arm and halves the cost; use it while iterating on graders. `--ablation with-without` adds the baseline when a case would otherwise run one arm (a case that resumes a transcript through `context.history_file`).
- A `tool_used` grader on `Skill`, and any grader marked `arm: with-only`, can never pass without the plugin, so Claude Code reports them as indicators and leaves them out of the score in both arms. Set `arm: both` on a grader to score it in both arms anyway.
- For a personal or project skill with no plugin around it, `claude plugin eval` has no plugin target. Either wrap the skill folder in a plugin (a `.claude-plugin/plugin.json` in the skill folder makes it a skills-directory plugin) or compare by hand: set the skill to `"off"` in `skillOverrides` in `.claude/settings.local.json` for the baseline session and run the same prompts. `skillOverrides` does not affect plugin skills.

## Scenarios become cases

The use-case scenarios the user accepted in phase D are the cases; nothing else is. Each case is a directory under `evals/` at the plugin root, not inside the skill:

```text
evals/
  <case>/
    prompt.md          frontmatter: run limits; body: the prompt, sent exactly as written
    graders/
      <name>.md        one check per file; frontmatter: type and options; body: rubric
    case.yaml          optional: fixtures and history, or the whole case in one file
  results/             written by each run; add it to .gitignore
```

- A directory is a case when it holds `prompt.md`, `case.yaml` or both. A case with no grader fails to load, so write at least one before the first run.
- `claude plugin eval init --bare <case>` writes a blank case with a placeholder prompt and one placeholder grader and runs nothing. Without `--bare`, `claude plugin eval init` opens an interview that proposes cases and graders; the user runs that one in their own terminal.
- `assets/eval-case/` holds a prompt, a grader and a `case.yaml` template to copy from.
- Phrase the prompt the way a user would type it, without naming the skill; naming it tests nothing about triggering. Everything you would otherwise ask the user goes in the body after the task, under `Everything you'd otherwise ask me:`, because the run is non-interactive and the body is all Claude receives. `@path` mentions are not expanded.
- Write the cases and their graders before the skill exists, so the skill is not graded against whatever it happened to produce.
- A run starts in an empty workspace with only the plugin under test loaded: no user settings, `CLAUDE.md`, project `.mcp.json` or other plugins. Ship anything a case depends on inside the plugin.
- A human-only skill (`disable-model-invocation: true`) cannot be loaded by Claude, so a trigger grader on it fails by design; what `/plugin-name:skill-name` does inside a `prompt.md` is unverified, so tell the user the case measures the body only if it passes.

## prompt.md frontmatter

An unknown key is an error.

| Field                  | Default                   | Purpose                                                                       |
| ---------------------- | ------------------------- | ----------------------------------------------------------------------------- |
| `name`                 | the directory name        | case name; `--case` globs match it                                            |
| `description`          |                           | for humans                                                                    |
| `tags`                 | `[]`                      | labels for `--tag` filtering                                                  |
| `runs`                 | `3`                       | runs per arm, 1 to 50; `--runs` overrides it                                  |
| `model`                | the child session default | model for the agent under test; `--model` overrides it                        |
| `max_turns`            | `10`                      | turn cap, up to 200; hitting it lowers the score, so set it generously        |
| `timeout_seconds`      | `300`                     | wall-clock cap per run, up to 3600                                            |
| `allowed_tools`        | `[]`                      | tools the case wants; read-only ones such as `Read`, `Glob`, `Grep`, `Skill` are granted when listed |
| `append_system_prompt` |                           | text appended to the child session's system prompt                            |
| `env`                  | `{}`                      | extra environment variables; keys must match `EVAL_[A-Z0-9_]*`               |

## case.yaml: fixtures and history

`case.yaml` needs `schema_version: "1.1"` and `name`. The prompt.md fields `description`, `tags`, `plugins`, `runs` go at the top level; `model`, `max_turns`, `timeout_seconds`, `allowed_tools`, `append_system_prompt` and `env` go under `execution:`. When both files exist, `prompt.md` frontmatter wins and its body is the prompt. These keys exist only in `case.yaml`:

| Field                    | Purpose                                                                                                          |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `context.scaffold_script` | a Bash script in the case directory that creates fixture files or a git repository in the empty workspace before Claude starts; 120-second limit, non-zero exit fails the run |
| `context.history_file`   | a `.jsonl` transcript in the case directory to resume; the case prompt becomes the next user turn                |
| `context.add_dirs`       | directories inside the case directory Claude may read during the run, read-only                                  |
| `graders`                | a list of graders, each with a `name` plus the keys a grader file takes                                          |

The scaffold script runs as the user, outside the agent's sandbox, and only when `--scaffold` is passed, so tell the user to pass that flag only for suites they or their organization wrote. Use it for files and git state only: project configuration it writes is not loaded.

## Graders

A grader's name is its filename without `.md`. Every grader takes `type` (required), `weight` (default 1, any positive number) and `arm` (`with-only` or `both`).

| type          | options                                | passes when                                                                                                         |
| ------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `regex`       | `pattern`, `flags`, `match`, `target`  | the JavaScript regex is found in the target; `match: not_contains` requires absence, `match: "count:N"` exactly N; case-insensitivity is `flags: i`, not `(?i)` |
| `tool_used`   | `tool`, `input_match`, `min`, `max`    | calls to `tool` whose JSON input matches `input_match` number between `min` (default 1) and `max` (default unlimited) |
| `tool_order`  | `before`, `after`                      | both tools were called and the first `before` call precedes the first `after` call; each is a tool name or `{ tool, input_match }` |
| `file_exists` | `path`, `exists`                       | a file Claude created during the run matches the `path` glob, or none does with `exists: false`                    |
| `llm`         | `criteria`, `focus`                    | a judge model votes PASS on the rubric in at least two of three votes; in a `.md` file the body is the criteria     |

`regex` takes a `target` and `llm` takes a `focus`; both accept the same values:

| value                            | what the grader sees                                                                                     |
| -------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `last_message`                   | Claude's final response text (the default)                                                               |
| `trace`                          | the session as JSON, one message per line; quotes are escaped, so a regex matches `\"` rather than `"`    |
| `files`                          | the paths Claude created, one per line; not their contents                                               |
| `{ source: file, path: <path> }` | the contents of one workspace file after the run; use this to grade what the skill produced              |
| `mock_calls`                     | each call Claude made to a mocked MCP tool, with its input and the mock's answer                         |

Only `file_exists` and `target: files` miss files that were edited rather than created; to check an edit, grade the file's contents or use `tool_used` on `Edit`. There are no custom-code graders: for a build or test outcome, have the prompt run it and write the result to a file, grade that file with `regex`, and assert the command ran with a `tool_used` grader whose `input_match` names it.

The grader to trigger a skill check is `tool_used` with `tool: Skill` and `input_match: '"skill"\s*:\s*"(?:[\w-]+:)?NAME"'`. It stays inside cases that also grade an output; do not write a case that exists only to test triggering.

### Choose graders that give a stable signal

- Give each case one grader on the result (the final message or a produced file) and one on the steps taken (`tool_used` or `tool_order`). Together they say whether the answer was right and whether the skill produced it.
- Grade long output, such as a generated file, with `regex` over the file's contents, which checks the whole file the same way every time. Keep `llm` graders for short output, with rubrics written as concrete PASS and FAIL conditions.
- If the `Skill` grader passes but `Δ` is negative, suspect the judge before the skill: re-run with `--judge-model sonnet` and tighten the rubric so formatting does not decide the verdict.

## MCP mocks

A skill that calls MCP tools can be evaluated without the real service. Put one file per tool at `evals/mocks/<server>/<tool>.md` (suite-wide) or in a case's own `mocks/` directory, where `<server>` is the server's name in the plugin's `.mcp.json`. The body is what the tool returns, with `{{input.<field>}}` substitutions; an `expect:` block in the frontmatter aborts the run with score 0 when Claude sends input that violates it, so a case can assert what the skill asked the server to do. A tool with no mock file is not available to Claude. Grade the calls with `target: mock_calls`. The plugin's real servers start only with `--allow-real-servers` or `--mocks off`.

## Running

Run from the plugin root; put the target before list-valued flags.

```bash
claude plugin eval . --runs 1 --case <case> --allow-tools Write Edit "Bash(python3 *)" --max-cost-usd 5
```

| Option                   | Effect                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `--runs <n>`             | runs per case per arm; default each case's `runs`, else 3                                                           |
| `--ablation none`        | one arm only; `with-without` adds the no-plugin baseline                                                            |
| `--case <glob>`          | only the matching cases                                                                                             |
| `--model <model>`        | model for the agent under test; pin it so a model rollout is not mistaken for a regression                          |
| `--judge-model <model>`  | model for `llm` graders; the default is the model Claude Code uses for background tasks                             |
| `--allow-tools <tools>`  | grants beyond the read-only set, for every case in the run; a run never stops to ask, so an ungranted `Bash`, `Write`, `Edit` or `WebFetch` is removed from the session |
| `--max-cost-usd <usd>`   | a ceiling on the list-price cost estimate, checked before each run starts; runs already started finish; if any run is left unstarted the command exits 2 with partial results |
| `--scaffold`             | run each case's `scaffold_script`                                                                                   |
| `--output-dir <dir>`     | where `aggregate-result.json` and `report.html` go                                                                  |
| `--keep-temp`            | keep each run's sandbox directory and print its path                                                                |

- Cost: roughly cases times runs agent runs with the plugin and the same again without, plus three short judge calls per `llm` grader per run. Show this arithmetic before asking for the ceiling.
- Granting `Bash` in any form runs every command under the OS-level sandbox: writes are confined to the run's workspace and network access only reaches domains granted with `WebFetch(domain:example.com)`. With no sandbox backend (native Windows, or Linux without `bubblewrap` and `socat`) each run is refused. If the skill bundles a script, grant its interpreter, or every case that runs it fails for a reason unrelated to the skill.
- A case's `allowed_tools` and the skill's own `allowed-tools` cannot widen what `--allow-tools` granted.
- With `--max-cost-usd`, an unstarted run means exit code 2 and partial results; say so rather than reporting the partial scores as a result.

## Reading the results

Each run with at least one case writes `evals/results/<timestamp>/report.html` and `aggregate-result.json` (the report is one self-contained file). The summary table prints first, with a `Report:` line. The report shows every grader's verdict and explanation for every run; for `llm` graders it also shows the judge's votes and the excerpt it judged. `cases[].arms.with[].error` in the JSON says why a run ended abnormally, such as a timeout or a usage limit, and a usage-limit error partway through can look like a regression, so read the `NOTES` column before trusting a drop.

## The improve loop

After each run read the report and the transcripts, not just the scoreboard. A failing grader usually has one of four causes, each with a different fix:

1. The skill never loaded (`Δ` near zero and the `Skill` grader failing): rewrite the description to name the situations in the case prompts; do not touch the body. When the skill competes with neighbors, or the first rewrite does not fix it, hand off to the `tune-skill-descriptions` skill: it measures the description against real Claude Code routing on a labeled trigger set and keeps a rewrite only when held-out requests improve.
2. The skill loaded and Claude ignored an instruction: explain why the instruction matters, put a rule that must always hold in a hook, or move the step into a script the body tells Claude to run.
3. Every run did the same repeated work: look for logic each run rebuilt from scratch (the same tool sequence across runs, three runs each writing their own helper script) and bundle it as a script. A script encoding a judgment call makes the skill worse; bundle only deterministic work.
4. The grader was wrong: change it, say why in the hand-off, and note it, because silently editing graders to match outputs is the failure the record exists to prevent.

Generalize fixes: a complaint about one prompt is rarely about that prompt, and a fix that names the example makes the skill work on exactly the cases that were tested. Cut as readily as you add; a skill that only grows spends its budget on instructions that no longer earn it. When something resists three attempts, change the frame (a worked example, a different decomposition) rather than escalating the wording. To check a section earns its place, delete it, re-run, and see whether the score moves; save that for a skill the user considers finished.

Re-run within the cost ceiling until the stop condition for the chosen rigor holds or the ceiling is hit, and say which happened.
