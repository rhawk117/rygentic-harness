---
name: build-an-agent
description: >-
  Create, review, port, or debug a subagent definition file - a Claude Code agent (.claude/agents/*.md) or a GitHub Copilot CLI custom agent (*.agent.md). Use this whenever the user wants a new subagent, agent, worker, reviewer, scout, or specialist agent; wants an existing definition improved, hardened, or moved between Claude Code and Copilot CLI; or asks why an agent is not triggering, not loading, or behaving wrong. Use it even when they only describe the agent they want ("I need something that audits my migrations before I open a PR") without ever saying "subagent" or "frontmatter". Not for writing a one-off task prompt to hand to an agent that already exists.
---

# Build an agent

A subagent definition is three separate contracts wearing one file:

1. **Frontmatter** - whether the platform loads it at all, and what it may touch.
2. **Body** - what it does once running.
3. **Dispatch contract** - what the caller must hand it, and what comes back.

Most bad agents are bad at #3 and get debugged at #1. The measured evidence points the same
way: GitHub cut Copilot CLI tool failures 23% by improving handoff specifications rather than
configuration, and Jesse Vincent's eval suite found reviewer agents given an underspecified
input package produced confident wrong verdicts with 0 out of 5 flagging the missing brief.
So this skill spends most of its effort on the body and the dispatch, and treats frontmatter
as a lookup.

**Both platforms fail quietly.** A Claude Code definition with a malformed `name` is skipped
with nothing but a debug-log line. A tool name neither platform recognises is dropped in
silence, and the agent then runs without the capability and never says so. That is why this
skill ends in a lint step rather than a "looks good to me".

---

## Step 0 - Ask the target platform. Always, first.

Before anything else, ask which platform this agent is for:

- **Claude Code** - `.claude/agents/<name>.md`
- **GitHub Copilot CLI** - `.github/agents/<name>.agent.md` or `~/.copilot/agents/<name>.agent.md`
- **Both** - one shared body, two generated wrappers

This is not politeness. The answer forks the frontmatter keys, the tool vocabulary, the model
identifiers, and the return contract itself (Claude Code subagents return one final message;
Copilot CLI subagents have been multi-turn since CLI 1.0.71). Guessing wrong means rewriting.

If the user picks **Both**, say plainly that the two files will not be identical: only
`name`, `description`, `tools` and `model` exist on both platforms, and the values inside
`tools` and `model` still differ. Emitting the divergence report in Step 5 is what keeps this
honest.

Then read the reference for the chosen platform (both, if they said both):

- `references/claude-code.md`
- `references/copilot-cli.md`

Read them at this point rather than earlier - they are lookups, and loading the wrong one
wastes context.

---

## Step 1 - Check that a subagent is the right answer

Cheap to ask, expensive to skip. A subagent is worth it when the task explores many files,
splits into genuinely independent pieces, produces verbose output you want kept out of the
main context, or needs tool restrictions the main session should not have.

It is the wrong tool when the work is "find a file, read it, make a targeted change, verify
it". GitHub deliberately made Copilot CLI _less_ eager to delegate and reliability improved.
Anthropic's threshold is roughly ten or more files to explore, or three or more independent
pieces of work.

Two things people reach for subagents to do that a subagent does not do:

- **A checklist.** If the content is "always run these four commands", that is a skill or a
  hook, not an agent.
- **Repeated always-on context.** That is `CLAUDE.md` / `copilot-instructions.md` / `AGENTS.md`.

If the request is really one of these, say so and offer the right artifact instead. Building
the agent anyway is the more expensive mistake.

---

## Step 2 - Interview

Ask only what you cannot infer. If the user has already answered something in conversation,
use it and move on - re-asking reads as not listening. Batch the open questions into one
round rather than dripping them out.

1. **Trigger.** What must be true for this agent to be the right choice? A capability answer
   ("it reviews code") is not enough; you need a condition ("after an engineer subagent
   reports a task complete, before a PR is opened"). The `description` is router input, and
   Anthropic's own guidance is to be specific about trigger conditions, not just capability.
   Push back once if you only get a capability.

2. **Read or write.** Does it modify anything? This decides the tool allowlist and whether an
   over-grant is a security question rather than a tidiness one.

3. **Unit of work.** One task, one file, one diff, one branch? Vincent's evals caught review
   subagents drifting to review a whole branch when asked about a single task. If the boundary
   is not in the body, the agent will pick its own.

4. **Inputs the dispatch must supply.** What will it be unable to see? This is the
   highest-value question in the interview. A Claude Code subagent receives the dispatch
   prompt and `CLAUDE.md` and nothing else - no parent conversation, no parent tool results.
   Anything the agent needs and cannot fetch must arrive in the dispatch or be refused.

5. **Return shape.** What exactly comes back? On Claude Code only the final message returns,
   and the parent may summarise it further, so anything not in the output contract is lost.

6. **Model tier intent.** Cheap retrieval, standard work, or frontier review? Ask for the
   intent, not a model name - the reference resolves it per platform. Official guidance is
   `model: haiku` for simple delegated tasks, and one measurement put pinning a cheap model
   against inheriting a frontier one at 37% fewer tokens and under half the wall time.

7. **Failure posture.** What should it do when it cannot finish or its inputs are missing?
   The good answer is almost always "stop and say what is missing", because the alternative
   is a confident wrong answer that looks like a real one.

8. **Conversational or one-shot** - only if Copilot CLI is a target. If the design assumes the
   caller can ask follow-up questions, it will not port to Claude Code, where the subagent
   returns exactly once. Better to learn that now than at Step 5.

---

## Step 3 - Write the body

Use `templates/agent-body.md`. It is XML sections containing Markdown, which is portable
because neither platform parses the body, and which gives the agent unambiguous slots to fill.

The two sections that carry the most weight:

- **`<inputs_expected>`** turns failure mode "confident answer built on guessed context" into
  "loud refusal". This is the countermeasure to the 0-out-of-5 finding. Name the inputs, and
  say explicitly what the agent must _not_ infer them from.
- **`<output_contract>`** is the only thing that survives back to the caller. Everything else
  stays in the agent's context and is discarded.

Style notes worth following, with the reasoning:

- Write in second person to the agent. It is a system prompt, not documentation.
- Name behaviour, not tools. "Open the file" ports; "use the `Read` tool" breaks the moment
  the file moves platforms, and adds nothing on the platform it was written for.
- Give the scope an explicit OUT list. Naming the adjacent work the agent must not drift into
  is more effective than describing the IN list harder.
- Include two or three worked `<example>` blocks. Concrete beats abstract, and examples are
  how the agent learns your output vocabulary rather than inventing one.
- Prefer stating goals over step-by-step scaffolding when the agent runs on a frontier model.
  Heavy scaffolding wastes the reasoning you are paying for.

Body length: Copilot CLI caps it at 30,000 characters. Below that, there is no evidence that a
longer body hurts - so do not pad, but do not agonise about trimming a body that is genuinely
carrying its weight.

---

## Step 4 - Write the frontmatter

Look the keys up in the platform reference rather than recalling them - both platforms moved
fields inside the last quarter, and the references carry dated version gates.

A few decisions worth making deliberately rather than by default:

- **Tools are an allowlist, and omission is silent.** An agent missing `Edit` will not ask for
  it; it will work around the gap and report success. Grant exactly the verbs the answer to
  interview question 2 implies.
- **Cheap model for cheap work.** Do not let a retrieval agent inherit a frontier model.
- **A turn budget on anything that can run commands.** On Claude Code that is `maxTurns`, and
  it exists because agents have hung for hours with no abort.
- **Do not hardcode runtime limits into the body.** Nesting depth, spawn caps and model
  precedence all changed inside a single quarter. Cite the reference; do not restate it.

---

## Step 5 - Lint, then hand over

Run the linter on every file you emit:

```bash
python scripts/lint_agent.py --platform claude-code path/to/agent.md
python scripts/lint_agent.py --platform copilot-cli path/to/agent.agent.md
```

It checks the things that fail silently at runtime: structural rules that make a file load or
not, naming and filename rules, the `tools: []` total-lockout trap, description trigger
phrasing, and whether the body actually has the two load-bearing sections. Fix errors before
handing over; warnings are judgement calls to raise with the user rather than to auto-fix.

Then deliver three things, not one:

1. **The agent file(s)**, at the correct path for the platform.
2. **A dispatch snippet** - the paragraph the caller should use when spawning it, naming the
   inputs from interview question 4 and the return shape from question 5. An agent file
   without its dispatch snippet is half a deliverable, because the dispatch is where the
   measured quality difference lives.
3. **A divergence report**, if the user chose Both - which fields were dropped on each side
   and what that costs them. Making the loss visible is the entire value of emitting two files
   instead of pretending one file works everywhere.

Close by stating what the output was verified against, for example "frontmatter verified
2026-08-30 against Claude Code v2.1.251 / Copilot CLI 1.0.79", so a stale recommendation
identifies itself later instead of being trusted forever.

---

## Reviewing or debugging an existing agent

Same skill, different entry point. Ask the platform (Step 0), read the reference, then:

- Run the linter first. It catches the silent-load failures, and "my agent never runs" is
  usually one of those rather than a prompt problem.
- If it loads but never triggers, the `description` is the suspect - it is almost always
  written as a capability blurb for a human instead of a trigger condition for a router.
- If it triggers but returns something useless, the fault is usually `<inputs_expected>` or
  `<output_contract>` - it was not told what it would be missing, or not told what to return.
- If it does too much, the `<scope>` OUT list is empty.

`references/failure-modes.md` is the full catalogue, organised by symptom, with evidence
grades. Read it when a diagnosis is not obvious from the four checks above.

---

## Files in this skill

| Path                          | Read it when                                                                     |
| ----------------------------- | -------------------------------------------------------------------------------- |
| `references/claude-code.md`   | Target includes Claude Code. Frontmatter, load rules, caps.                      |
| `references/copilot-cli.md`   | Target includes Copilot CLI. Frontmatter, paths, limits.                         |
| `references/failure-modes.md` | Diagnosing an existing agent, or unsure whether a design choice is a known trap. |
| `templates/agent-body.md`     | Every time you write a body.                                                     |
| `scripts/lint_agent.py`       | Every file you emit, before handing over.                                        |
