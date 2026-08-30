# Failure modes - organised by symptom

Evidence grades: `[DOC]` vendor documentation · `[MEASURED]` a stated experiment with numbers
· `[OPINION]` practitioner assertion, unproven · `[GAP]` no credible source, stated rather
than guessed.

## Symptom: the agent never appears

| Cause                                                                        | Platform    | Grade   |
| ---------------------------------------------------------------------------- | ----------- | ------- |
| `name` missing, or `description` missing - skipped with no visible error     | Claude Code | `[DOC]` |
| Opening `---` not on line 1, or YAML that does not parse                     | both        | `[DOC]` |
| `name` contains `:` or starts with `-`                                       | Claude Code | `[DOC]` |
| Extension is `.md` where `.agent.md` is required                             | Copilot CLI | `[DOC]` |
| Filename outside `. - _ a-z A-Z 0-9`, or a name producing a hidden file      | Copilot CLI | `[DOC]` |
| A new `agents/` directory was created mid-session and needs a restart        | Claude Code | `[DOC]` |
| A stale `~/.copilot/agents/<n>.agent.md` shadows the repo's copy - home wins | Copilot CLI | `[DOC]` |
| Duplicate `name` in one directory - one loads by read order, no error        | Claude Code | `[DOC]` |

Copilot CLI reports load failures; Claude Code writes them to the debug log. When a file must
work on both, author and debug it on the CLI first.

## Symptom: it loads but is never chosen

| Cause                                                                                                                                                                                                                                         | Grade                                  |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `description` describes capability instead of trigger conditions. Anthropic: "Be specific about trigger conditions, not just capability."                                                                                                     | `[DOC]`                                |
| No recognised trigger clause - `Use when`, `Use after`, `Use PROACTIVELY when`, `Trigger when`. wshobson's linter fails this as `MISSING_TRIGGER`.                                                                                            | `[OPINION]`, enforced by a real linter |
| Combined non-builtin descriptions exceed 15,000 tokens, producing a startup warning. Detail belongs in the body.                                                                                                                              | `[DOC]`                                |
| `Agent` missing from the caller's allowed tools, so delegation is impossible                                                                                                                                                                  | `[DOC]`                                |
| `disable-model-invocation: true` set without realising it blocks automatic selection                                                                                                                                                          | `[DOC]`                                |
| Descriptions overlapping across a large agent library. Anthropic lists "too many custom specialist agents flooding options" as an anti-pattern, and 3-6 focused agents per repo is a common recommendation - but **nobody has measured this** | `[DOC]` + `[GAP]`                      |

## Symptom: it runs but the answer is confidently wrong

This is the most dangerous class, because nothing looks broken.

| Cause                                                                                                                                                                                                                                                       | Grade                     |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| The agent was assumed to inherit conversation context. It receives the dispatch prompt and `CLAUDE.md`, nothing else.                                                                                                                                       | `[DOC]`                   |
| A reviewer was given an underspecified input package. Reviewers handed only the diff produced confident spec verdicts that silently redefined "spec", with **0 of 5 flagging the missing brief**.                                                           | `[MEASURED]`              |
| The handoff did not state the request, the known context, the ownership scope and the required result format. GitHub's fix for exactly this measured 23% fewer tool failures per session, 18% fewer edit failures, P95 wait down 5%, no quality regression. | `[MEASURED]`              |
| No `<inputs_expected>` section, so the agent inferred its inputs instead of refusing.                                                                                                                                                                       | derived from the above    |
| Prose inside a loaded file was executed as a directive - a subagent read "MODEL REQUIREMENT: MUST only be run with Opus" from a `SKILL.md` and silently spawned a nested Opus child, invisible until its closing report.                                    | primary bug report #72684 |

## Symptom: it does more than it was asked to

| Cause                                                                                                                           | Grade        |
| ------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| No explicit OUT list in scope. Vincent's evals caught review subagents reviewing a whole branch when asked about a single task. | `[MEASURED]` |
| Multi-responsibility agent. One persona per file; extract procedures into skills.                                               | `[OPINION]`  |
| The body contradicts `CLAUDE.md` / `copilot-instructions.md`. Both load; conflicts produce unstable behaviour.                  | `[OPINION]`  |

## Symptom: it silently lacks a capability

| Cause                                                                                                                                            | Grade   |
| ------------------------------------------------------------------------------------------------------------------------------------------------ | ------- |
| Under-granted tools. "A tool you leave out isn't in the subagent's session at all: Claude works without it, with no permission prompt or error." | `[DOC]` |
| `tools: []` written meaning "use defaults". It means all tools disabled.                                                                         | `[DOC]` |
| Tool names copied between platforms. The vocabularies are disjoint and both platforms drop unknown names in silence.                             | `[DOC]` |
| `disallowedTools` assumed to filter the `tools` list. It resolves first.                                                                         | `[DOC]` |

## Symptom: it has more power than intended

| Cause                                                                                                                                 | Grade                  |
| ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| Over-granted tools - a security auditor with edit and shell access rewrites the code you wanted reviewed.                             | `[OPINION]`            |
| `bypassPermissions`, which permits writes to `.git`, `.claude`, `.vscode`, `.config/git`.                                             | `[DOC]`                |
| `skills:` treated as an access control. It is startup injection only; any agent with filesystem access can glob the skills directory. | `[DOC]` + issue #32910 |

## Symptom: it costs too much or takes too long

| Cause                                                                                                                                                                                                                                                                      | Grade                               |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| A simple agent inheriting a frontier model. Official guidance is `model: haiku` for simple delegated tasks; one measurement put pinning a cheap model at 37% fewer tokens and under half the wall time.                                                                    | `[DOC]` + `[MEASURED]`              |
| Fan-out assumed to be faster. Matched pairs measured 2.6x metered tokens on Opus and 5.9x on a Fable-tier model, with no wall-clock improvement. **The tasks were small** - the large parallelizable case that both vendors recommend subagents for has not been measured. | `[MEASURED]` + `[GAP]`              |
| Blanket downgrades. Conditional cheap-model tiering beat unconditional, and the router correctly refuses a cheap model when the task is unsuitable.                                                                                                                        | `[MEASURED]`                        |
| Over-delegating. GitHub made Copilot CLI less eager to delegate and reliability improved. Do not delegate "find a file, read it, make a targeted change, verify it".                                                                                                       | `[MEASURED]`                        |
| No turn budget on an agent that can run commands. One reported hang ran 12+ hours from a delegation that should have taken 30 seconds. `maxTurns` (v2.1.246) is the mitigation.                                                                                            | primary bug report #61405 + `[DOC]` |

## Symptom: it behaves differently than it did last time

| Cause                                                                                                                                                                                                                                                                              | Grade               |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| The same definition resolves differently as a subagent, as an `--agent` main session, as an in-process teammate (body appended, `mcpServers` ignored) and as a split-pane teammate (body replaces the system prompt, `model` ignored). `skills` is ignored in both teammate modes. | `[DOC]`             |
| A field honoured on one invocation path and dropped on another - `effort` under `-p --agent` (#82259, open), `isolation: worktree` under `--agent` (#50357).                                                                                                                       | primary bug reports |
| Agent teams forming unintentionally. With teams enabled, a subagent Claude names launches as a teammate, and the idle notification does not carry its output, so a flow waiting on results can stall. Teams also run roughly 7x tokens in plan mode.                               | `[DOC]`             |
| Guidance written against a stale version. Nesting depth, per-session spawn caps, fork defaults and `model:` precedence all changed inside Q3 2026 on Claude Code; Copilot CLI moved nesting 6 to 4 in 1.0.79.                                                                      | `[DOC]`             |

## Things frequently asserted that are not supported

Worth knowing so you do not enforce them as rules:

- **"Keep the body short."** No evidence that a verbose agent body degrades anything. The
  documented advice is to keep the _description_ short and push detail _into_ the body. Only
  Copilot CLI's 30,000-character cap is real. `[GAP]`
- **"Overlapping descriptions cause misrouting."** Plausible, unmeasured. The 15,000-token
  warning is a mechanical limit, not a quality finding. `[GAP]`
- **"Trigger phrases in the description improve routing."** Universally recommended, never
  benchmarked. Worth following - it costs nothing - but do not present it as proven. `[GAP]`
- **"Fan-out is never faster."** Only measured on small tasks. Do not let the claim travel
  without that qualifier. `[GAP]`
