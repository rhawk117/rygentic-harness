---
name: promptlint
description: >-
  Turn a rough task description into a production-quality prompt for a coding agent (Claude Code or GitHub Copilot), applying Anthropic's prompt-engineering best practices. Use this whenever the user wants a prompt written, improved, or reviewed for Claude Code, Copilot CLI, Copilot Chat, the Copilot coding agent, or any AI coding assistant — including requests like "write me a prompt for...", "draft a task for copilot", "turn this into an agent prompt", or when they describe a coding task they intend to hand off to an agent rather than have done here.
---

# Prompt Lint

Produce prompts that a coding agent can execute end-to-end without the user in the loop. The failure modes this skill exists to prevent: agents stop when the work _looks_ done (so every prompt needs a check the agent can run), agents act on assumptions instead of the codebase (so every prompt directs investigation first), and agents overreach (so every prompt draws a scope boundary). A prompt missing any of these three shifts the verification burden back onto the user.

## Workflow

### 1. Intake

Establish before writing anything:

- **Target**: Claude Code, or Copilot — and which Copilot surface (CLI, IDE chat, coding agent). If the user didn't name one, ask; the surfaces have different capabilities and the prompt shape changes.
- **Task type**: bugfix, feature, refactor, investigation/plan, migration, or review. This picks which sections the prompt needs.
- **What's already known**: repo/stack, symptom or goal, constraints, the project's verification commands.

### 2. Interview — only for load-bearing gaps

Ask at most 2–4 targeted questions, via the ask-user dialog when available. Only four gaps justify a question:

1. **Scope boundary** — what must NOT change.
2. **Verification gate** — which commands prove success (test runner, linter, type checker, build).
3. **Undiscoverable context** — symptoms, environment quirks, decisions already made, prior failed attempts. The agent can read the code; it cannot read history or intent.
4. **Done criteria** — what the user will check to accept the work.

Do not interrogate. If the user said to skip questions, is unavailable, or already covered these: proceed, and surface every guess in an **Assumptions** list alongside the deliverable. Never block on a question you can answer with a reasonable stated assumption.

### 3. Assemble the prompt

Build from the architecture below, then read exactly one target file and adapt:

- Claude Code → `references/claude-code.md`
- Any Copilot surface → `references/copilot.md`

For proven prompt language covering common failure modes (overengineering, hardcoding to tests, hallucinated claims, action defaults), pull from `references/snippets.md` rather than reinventing — adapt the snippets, don't paste them wholesale.

### 3b. Fast path — mightymodels role dispatches

When the prompt targets a known mightymodels worker inside an active loop — a scout retrieval question, an engineer task dispatch, a budgetron fix, or a reviewer kickoff — skip the interview and instantiate the matching template from `references/templates/`. The templates are pre-linted; the job shrinks to filling slots and running the ten-second checklist at the top of each. The engineer template's output doubles as the task brief's `## ASKED` half — write it once, use it in both places. Fall back to the full workflow for anything novel: a template forced onto a strange task is worse than the interview.

### 4. Deliver

Output, in order:

1. The prompt in a fenced block, using a four-backtick outer fence so any inner code fences render intact. Ready to paste — no placeholders unless the user chose placeholder mode, and then mark each one `TODO(<what>)`.
2. **Assumptions** — every guess made, one line each. Omit the section if none.
3. **Attach when running** — files, screenshots, or error output the user should provide alongside the prompt (e.g. `@`-references in Claude Code, open files in the IDE).

Keep commentary to a couple of sentences. If the prompt is long or the user wants a file, write it to `prompt-<slug>.md` instead of only printing it. When the caller sets a line budget, honor it — trim optional sections before load-bearing ones.

## Prompt architecture

House format: trim, well-formed XML sections containing Markdown. XML tags let the agent parse instruction boundaries unambiguously; Markdown inside keeps each section readable. Include only sections that earn their place — a small bugfix prompt might need four; never pad to fill the template.

| Section          | Carries                                                                                                                                                     | Include when                                      |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `<objective>`    | What, where, and _why it matters_. One short paragraph.                                                                                                     | Always                                            |
| `<context>`      | Facts the agent cannot discover: symptom, environment, history, decisions already made.                                                                     | There are such facts                              |
| `<discovery>`    | Investigation before changes: named files to read, flows to trace, assumptions to confirm against the code.                                                 | Always for non-trivial work                       |
| `<constraints>`  | Scope boundary (what must not change), minimal-change expectation, conventions — by pointing at an existing exemplar file, not describing style abstractly. | Always                                            |
| `<verification>` | The exact commands and expected results. Require evidence in the report — actual output, not "tests pass".                                                  | Always — non-negotiable                           |
| `<output>`       | What the final report contains: changed files, evidence, and anything discovered that contradicts this brief.                                               | Agent runs unattended or reports to the user      |
| `<examples>`     | 3–5 input→output pairs in `<example>` tags.                                                                                                                 | Output format matters and prose can't pin it down |

Content rules that make the difference:

- **State instructions positively.** "Write prose paragraphs" beats "don't use bullets" — the agent needs to know what to do, not only what to avoid.
- **Attach a why to every non-obvious constraint.** Agents generalize from reasons; a bare rule gets applied literally and nowhere else. "Don't touch token issuance — it's mid-migration and another branch owns it" steers judgment in cases the rule didn't anticipate.
- **Goal over recipe.** For complex work, state the goal and quality bar and let the agent plan; a guessed step-by-step recipe is usually worse than the plan the agent forms after investigating. Prescribe sequence only when order genuinely matters (migrations, deploy steps).
- **The new-colleague test.** Read the finished prompt as a competent engineer with zero context on this repo. Anything confusing to them is confusing to the agent. Ambiguity in, garbage out.
- **Trim ruthlessly.** Every line must change agent behavior. Padding buries the load-bearing lines, and a bloated prompt gets its rules ignored just like a bloated instructions file.
- **Don't restate what the agent's persistent config already covers.** If the repo has CLAUDE.md / copilot-instructions.md, reference it ("follow the conventions in CLAUDE.md") instead of duplicating it — duplication drifts.

## Anti-patterns to catch

| Smell                                                                     | Fix                                                                                           |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| "Fix the login bug"                                                       | Symptom + likely location + what fixed looks like + a reproducing test                        |
| Prescribing implementation the agent should discover                      | Move it to `<discovery>` as a question to answer                                              |
| "Do not X" with no alternative                                            | Say what to do instead                                                                        |
| Success by assertion                                                      | Verification commands + evidence requirement                                                  |
| Pasting whole files the agent can read                                    | Reference the path; paste only what the agent can't access (logs, screenshots, external docs) |
| Tests exist and the task is "make them pass"                              | Add general-solution language from `references/snippets.md`                                   |
| Conflicting instructions ("be thorough" + "change as little as possible") | Resolve the priority explicitly in the prompt                                                 |

## Review mode

When the user brings an existing prompt: audit it against the architecture table and anti-pattern list, then return a revised prompt plus a short list of substantive changes and why each matters. Don't nitpick wording that doesn't change agent behavior.
