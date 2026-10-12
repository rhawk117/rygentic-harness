---
name: prompting-subagents
description: >-
  Build, review, or repair the dispatch packet for a mightymodels worker: choose the right
  worker (code-scout, web-scout, qualitylens, engineer, architect, merge-vader,
  uncle-bob, gitty-up, wingman), fill its role template, resolve its model from
  ticket.yml, and read the report it returns; also the opening prompt for the next mightymodels
  session. Not for writing a prompt a human will paste into
  Claude Code or Copilot; that is ai-engineer's promptlint.
when_to_use: >-
  Use whenever you are about to dispatch, re-dispatch, or escalate to a mightymodels
  worker ("dispatch the engineer for task 3", "have a scout find every caller of X", "escalate
  T5 to architect"), when asked which worker should handle something, or when a drafted
  dispatch needs checking before it goes out.
user-invocable: false
---

# prompting-subagents

Mightymodels workers are cheap because each does one narrow job from a packet it cannot question: a subagent has not seen this conversation, the ticket, or the diff, and it will act on exactly what the packet says. The failures this skill prevents are all packet failures: the wrong worker for the job, a worker asked for judgment it is built to refuse, a packet missing the one field its worker checks first, a model other than the ticket's, and a report read as more certain than it is. Every worker's standing contract lives in its agent file; the packet carries only what varies per dispatch.

## When it applies

- Before any dispatch to a mightymodels worker, from any mightymodels skill or ad hoc.
- When asked which worker should handle a job.
- When checking or repairing a dispatch someone drafted.
- When writing the opening prompt for the next session (baton-pass).
- Not for a prompt a human will paste into a coding agent; that is ai-engineer's `promptlint`.

## Procedure

1. **Choose the worker.** Route by what you need, not by what feels senior:

   - A fact, location, call-site list, config value, resolved version, git history, or one command's output: **code-scout**. Documented behavior, a default, a deprecation, or a changelog entry for a dependency: **web-scout**, with the version the lockfile pins. One narrow question per dispatch; a "why" or "should" comes back `NEEDS-ANALYSIS`, because that judgment is yours.
   - Code written against acceptance criteria: **engineer**, with an ASKED stanza. One known fix with explicit Fix and Verify lines (a lint failure, a missed verification item, a review finding): **engineer**, residual variant. If the fix is not nameable in a sentence, it is a task, not a residual.
   - A task the plan sizes `tiny`, one that owns exactly one file and whose every acceptance criterion is a command with an expected result: **intern**, with the same ASKED stanza, for one attempt. The dispatch hook refuses the intern unless the task started for it owns exactly one file, so every other size goes to the **engineer**, which may also take a tiny task. An intern that comes back `blocked` is not dispatched again and the user is not asked: the task goes to the **engineer**.
   - An engineer came back `failed` or `blocked`, or a designated reviewer rejected its work for poor code quality with structured evidence: **architect**, once, `recovery-implementation` by default. When architect also fails, the task goes to whats-broken. Never architect for new work.
   - Churn, coupling, or hotspot measurements: **qualitylens**, dispatched by a persona reviewer or review-circus with the target and the history window.
   - A release-readiness or maintainability review: **merge-vader** and **uncle-bob**, dispatched only by review-circus; each preloads its doctrine as a skill of its own, `becoming-merge-vader` or `becoming-uncle-bob`.
   - Whether CI passed: **gitty-up**, after the PR exists. Its `error` verdict is a stop, never a pass.
   - Verification of an engineer's DONE claims: **code-scout**, DONE against ASKED criterion by criterion. Never let the engineer grade its own work, and never grade it yourself from the diff alone.
   - A stuck judgment call (two defensible options, an expensive-to-reverse choice, conflicting scout reports, two failed attempts): **wingman**, through the ask-an-adult skill, then the user decides.

   Review findings route by risk first: a Critical finding, or a security finding at High or above, goes to a full engineer task whichever reviewer found it. Below that line, uncle-bob findings go to engineer tasks and merge-vader findings to engineer residuals; a `failed` or `blocked` engineer escalates to architect. CI failures route by the log-tail test: a cause obvious from the last screen of the log is an engineer residual; anything needing investigation is whats-broken, not a fixer.

2. **Resolve the model.** Read the active ticket's `subagent-models` block in `.mightymodels/<slug>/ticket.yml` at every dispatch. Every worker but the two reviewers has one fixed model, the same in the ticket and in the agent file's `model:` pin, and `validate` refuses a ticket value that differs; each agent file also pins its `effort`. A reviewer's model comes from the run (review-circus), not the ticket. Pass the alias (haiku, sonnet, opus or fable) as the `Agent` tool's `model` parameter, which takes precedence over the agent file's pin. The engineer is sonnet at every scope; a genuinely gnarly engineer task may be bumped one tier up, with the reason logged in its ASKED stanza.

3. **Fill the template.** Read the chosen worker's template in `references/templates/` (one file per worker, named after it) and fill its slots; run its ten-second checklist before sending. Templates exist for `code-scout`, `web-scout`, `engineer` (task and residual), `intern`, `architect`, `qualitylens`, `reviewer`, `wingman`, and `next-session`. A worker without a template (gitty-up) gets the house format below, not the rough task: gitty-up needs the PR reference and the base branch.

4. **Check the packet** against the house format and the anti-patterns below. This step is also the whole of review-and-repair mode.

5. **Dispatch** with the `Agent` tool: `subagent_type` the plugin-qualified `mightymodels:FOLDER:WORKER`, where the folder is the one the worker's agent file is in: `review` for merge-vader, uncle-bob and qualitylens, `workers` for engineer, architect, intern and gitty-up, `triage` for code-scout, web-scout and wingman (neither the bare name nor `mightymodels:WORKER` is accepted), and `model` the worker's fixed alias. Send independent questions in parallel; send a narrower follow-up to the same worker through `SendMessage` instead of a fresh dispatch, its `to` the agent ID or name the first dispatch returned. The worker resumes with its full conversation history (https://code.claude.com/docs/en/sub-agents.md, "Resume subagents").

6. **Read the report.** Workers report in XML with a shared vocabulary: `verdict`, `confidence`, `findings`, `follow_up`. Treat `INFERRED` as a hypothesis naming what it rests on, never as a fact; open the cited line yourself before an `INFERRED` finding drives a decision. The full verdict vocabularies and the severity table live in `agents-assemble/references/contracts.md`, which wins whenever a report and this page disagree.

## House format

Trim, well-formed XML sections containing Markdown: the tags give the worker unambiguous boundaries, and the Markdown inside keeps each section readable. Include only the sections that earn their place.

| section          | carries                                                         | include when                           |
| ---------------- | --------------------------------------------------------------- | -------------------------------------- |
| `<objective>`    | what the worker must do and why                                 | always                                 |
| `<context>`      | facts the worker cannot discover: branch, trigger, history      | there are such facts                   |
| `<discovery>`    | what to inspect before acting: paths, symbols, search terms     | the worker searches or reads           |
| `<constraints>`  | owned scope, commit and push instructions, what must not change | the worker edits or runs commands      |
| `<verification>` | exact commands and expected results, with evidence required     | the worker's result must be checked    |
| `<output>`       | only what differs from the worker's standing output contract    | rarely; the contract usually covers it |

State instructions positively, attach a reason to every non-obvious constraint, and never restate the worker's own contract: duplication drifts, and a packet that repeats the agent file buries the lines that vary.

## Anti-patterns

- Dispatching an engineer to answer a lookup: implementation budget spent on retrieval.
- Asking a scout to recommend an approach: `NEEDS-ANALYSIS` at best, laundered guesswork at worst.
- A context-free packet: the worker has not seen the diff, ticket, or ledger, so "check whether the docs are stale" fails where "grep `docs/` and `README.md` for `get_all_tasks`" succeeds.
- A vague residual ("clean this up"): the engineer's owned-file set will refuse it anyway.
- Paraphrasing Fix and Verify lines, reviewer findings, or scout citations: paraphrase is where scope creep and false certainty start. Paste them verbatim.
- Reading gitty-up's `error` as "probably fine".
- Doing a worker's job yourself: committing for an engineer or verifying your own dispatch removes the second pair of eyes the loop is built around.

## Output

The dispatch goes out through the `Agent` tool; in review-and-repair mode, return the repaired packet in a fenced block with one line per substantive change and why it matters. The next-session prompt is printed in chat by baton-pass.
