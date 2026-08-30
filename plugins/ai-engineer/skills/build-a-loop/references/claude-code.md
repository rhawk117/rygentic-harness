# Claude Code wiring

How to enforce a loop contract in Claude Code. Confirm event names and payload fields against the current docs before shipping; the shapes below reflect what was documented as of 2026-08-30.

## Contents

- Goal-based loops
- Budgets and caps
- The stop gate
- Keeping the contract alive through compaction
- The verifier subagent
- Parallel workers

## Goal-based loops

`/goal <condition>` runs the loop until an evaluator judges the condition met. The evaluator is a separate small fast model that **does not call tools**, so it can only judge what the main agent has already said out loud in the conversation.

That single fact decides how to write the condition. It must be demonstrable from the agent's own output:

- Good: `all tests in tests/api pass, with the pytest summary line shown, and ruff reports no errors`
- Bad: `the API is production ready`
- Bad: `the code is clean` (nothing the evaluator can see)

Three verdicts: met, not yet, and **impossible**, where the evaluator judges the condition can never be satisfied. The impossible verdict clears the goal and records the reason, which is the give-up path every loop needs.

Bound the run inside the condition itself: append `or stop after 20 turns`.

Stall detection is built in. Several turns with no tool use stops the loop, warns, and hands back control with the goal still set.

Escalation is already sorted for you. Auth failure, exhausted credit balance, a context overflow auto-compaction could not clear, and an unavailable model all clear the goal and return to the human. Transient failures, including rate limits and overloaded servers, leave the goal active.

## Budgets and caps

Both SDK budgets default to **no limit**. Set them for anything unattended:

- `max_turns` counts tool-use turns only
- `max_budget_usd` caps spend

Termination is an enum, not a boolean. Handle `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`. The `result` field is present only on `success`, so code that reads it unconditionally will break exactly when the loop failed.

Subagent trees have three separate caps, and prompting is not a substitute for setting them:

- `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3
- `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, default 20
- a spend cap, which refuses further spawns and ends the query when hit

A subagent that hits its own `maxTurns` returns partial output and can be resumed rather than failing outright.

## The stop gate

A `Stop` hook runs when the turn is about to end and can block it, forcing another turn. This is where a test suite belongs when "done" must mean "the tests pass".

Claude Code overrides the hook after **8 consecutive blocks**, so the loop cannot be trapped. You still want your own escape: read `stop_hook_active` from the payload and downgrade from blocking to advisory once it is set, so a check that can never pass degrades into a warning instead of eight wasted turns.

Hooks run in the application process, not in the context window. They cost no context and they bypass compaction, which makes them the right place for anything that must hold for the whole run.

`PreToolUse` hooks can reject a call before it executes; the agent receives the rejection as the tool result and tries another approach. Use this to enforce read-before-write on the contract file: no criterion flips to true unless the evidence artifact was read first.

## Keeping the contract alive through compaction

Compaction clears older tool outputs first, then summarizes. Requests and key snippets survive; detailed instructions from early in the conversation may not.

Three defenses, in order of strength:

1. Put standing rules in `CLAUDE.md`, which is re-injected on every request rather than living in conversation history.
2. Add a summarization-instructions section to `CLAUDE.md` naming the contract and the criteria as must-keep. The compactor matches on intent, so the header wording is free-form.
3. Use a `PreCompact` hook to snapshot the contract state and re-inject it after.

Keep noisy output out of the window in the first place: quiet flags on chatty commands, or run them inside a subagent, since command output stays in the conversation for the rest of the session.

## The verifier subagent

Spawn the grader as a subagent with no `Write` or `Edit` tools. A withheld tool is simply absent from its session, with no prompt or error, so this is a hard guarantee rather than an instruction.

Give it the diff and the criteria and nothing else. The value comes from what it cannot see: it never saw the reasoning that produced the change, so it judges the result on its own terms.

The only channel from parent to subagent is the Agent tool's prompt string. File paths, error messages, and decisions the verifier needs must be in that string; nothing is inherited.

Guard against the reviewer that finds problems because it was asked to. Have it grade against the named criteria and report "criterion met" as readily as it reports gaps, and distinguish a refuted claim from one it could not check.

## Parallel workers

Workflow scripts hold the loop outside the conversation, so intermediate results stay in script variables instead of filling the context window. Reach for them when the number of iterations is large or the branching is mechanical.

Runtime caps: 16 concurrent agents, 4,096 items per parallel call, 1,000 agents per run. The size warning above 25 agents is advisory and does not pause anything.

Prefer progress-phrased stop conditions in fan-out loops: "keep fixing reported errors until the type check passes or two rounds in a row make no progress".
