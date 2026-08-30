---
name: build-a-loop
license: MIT
description: >-
    Design a reliable agent loop from a plain description of the work. Picks the loop shape, defines what one iteration may touch, sets the evidence each success criterion needs, writes a stop condition that measures progress instead of counting turns, and emits a LOOP.md contract plus the Claude Code or GitHub Copilot CLI configuration and verification hook that enforce it. Use this whenever someone wants an agent to keep working on its own - a loop, a harness, an autonomous or long-running or overnight run, a self-verifying build, a fan-out of subagents, a scheduled or recurring agent task - and also when an existing loop misbehaves: runs away, stalls, burns turns repairing the wrong thing, claims success it cannot prove, or loses its rules after compaction. Trigger even when the user never says the word "loop".
---

# Design an agent loop

A loop is an agent repeating cycles of work until a stop condition is met. Most loops that fail do not fail because they ran too long. They fail because they were wrong early, could not tell, and kept going. The measured picture: the decisive error in a failed run lands around step 7, the window to recover is about one step, and the first visible symptom shows up around step 16. Repairs aimed at the wrong cause account for 39% of all wasted execution, and 26% of failed runs end by claiming success they did not achieve.

That is why this skill produces artifacts instead of advice. Advice lives in the context window, and the context window is exactly what gets summarized away on a long run. A contract file, a stop hook, and a budget flag survive.

## Before anything else: does this need a loop?

Not all work does, and a loop costs real money. A single agent run with a good prompt beats a badly specified loop nearly every time.

Say so plainly and stop here when:

- The task finishes in one pass and the user just wants it done well.
- There is no check the agent can run. Without a signal, "looks done" is the only stop condition available, and the user becomes the verification loop.
- The work is exploratory and the user cannot yet say what finished looks like. Help them scope it first.

When a loop is right, keep it the smallest one that works. Reach for parallel workers only after a single-worker loop has proved the check is trustworthy.

## Step 1: mine what they already told you

The user has usually described most of the loop already. Extract it before asking anything:

- What repeats, and what changes between repetitions
- What "done" means in their words
- What tooling exists (test command, linter, build, CI, a script that prints a number)
- Whether a human is present while it runs
- Which platform they are on

Re-asking something they already said is the fastest way to lose them. Ask only about the gaps that change the output.

## Step 2: the five decisions

Every good loop is these five answers. Fill each one from what the user said; where they did not say, propose a default and name it as a default rather than silently assuming.

### 1. Trigger - what starts the next iteration

| Shape | Starts on | Fits |
|---|---|---|
| Turn-based | the user's next message | short work, a human watching |
| Goal-based | the previous turn finishing, while a condition is unmet | anything with a verifiable exit criterion |
| Time-based | a schedule or a wait | queues, CI watching, PR shepherding |
| Event-driven | an external event, nobody present | recurring streams: issue triage, dependency bumps, migrations |

Default to goal-based. It is the only shape that carries its own stop condition.

### 2. Unit of work - what one iteration may touch

An iteration should be small enough that a bad one is cheap to throw away, and bounded enough that two workers cannot collide. State it as concrete boundaries: these files, this module, this test suite, this one ticket.

This matters most with parallel workers, which typically share a filesystem with no locking. Two agents writing the same file means the last writer wins, silently. Partition by file or module, and say which paths belong to whom. Where the work is genuinely sequential, say so and keep it sequential rather than paying for parallelism that has to be serialized anyway.

### 3. Evidence - what proves a criterion, and who reads it

Write success criteria as a list that starts entirely false. Nothing flips to true on the agent's say-so; it flips when a named artifact says so - test output, an exit code, a diff, a log line, a screenshot, a count.

The reason is blunt: agents asked to grade their own work tend to praise it, and a quarter of failed runs narrate a success that did not happen. So for each criterion capture:

- The exact command or check that produces the signal
- The artifact it writes, and where
- What the passing value looks like

If a criterion has no artifact, it is a wish. Either find a check for it or move it into a "human confirms" section that the loop cannot mark done on its own.

### 4. Stop - progress first, cost second

Give every loop three stop conditions, because they catch different things:

- **Progress**: the real one. "Until the type check passes, or two consecutive rounds make no progress." "Until two rounds in a row find nothing new." A count cannot detect a loop that is confidently repairing the wrong thing; a progress measure can.
- **Cost backstop**: a turn cap and a spend cap, set explicitly. Both platforms default to unlimited. Treat the cap as a fuse, not as the design.
- **Impossible**: an explicit verdict for "this condition can never be satisfied", which ends the loop and says why. Without it a loop with a bad criterion runs forever.

Add stall detection where the platform offers it: several turns of talking without tool use means the loop is spinning.

### 5. Escalation - what ends the run and what does not

Sort failures by whether waiting could fix them. A workable default:

| Failure | Action |
|---|---|
| Auth failure, exhausted credit, unrecoverable context overflow, model unavailable | end the loop, return to the human |
| Rate limit, overloaded server, transient network | keep the loop alive, back off |
| Check fails | remediate and iterate, this is the loop working |
| Same check fails the same way twice | stop and escalate, the loop is stuck |
| Criterion judged impossible | end with the reason |

## Step 3: write the contract

Write `LOOP.md` (or `<task-dir>/LOOP.md` where the user keeps per-task state) from `assets/LOOP.template.md`. This file is the loop's memory of its own rules, and it exists because rules kept only in the prompt decay: after a single compaction, policy violation in measured conditions goes from zero to roughly 30% pooled, and worse for project-specific rules than for general ones. A file the agent re-reads each iteration does not decay.

Keep it short enough that re-reading it every iteration is cheap. If it is growing past a page, the unit of work is too big.

## Step 4: emit the enforcement

Ask which platform, then read exactly one reference file and follow it:

- Claude Code: `references/claude-code.md`
- GitHub Copilot CLI: `references/copilot-cli.md`

Do not emit both dialects unless the user asks. Each reference covers the goal or autopilot wiring, the stop-gate hook, the budget flags, the verifier subagent, and how to keep the contract pinned against compaction.

Both platforms move fast. Before writing a hook file, confirm the event names and payload shape against the platform's own documentation or config schema rather than trusting the template verbatim, and tell the user which parts you verified.

## Step 5: red-team the design before handing it over

Walk the emitted loop against these. Each one is a failure that shows up in the field, and naming a residual risk is more useful than pretending there is none.

- **Self-graded stop.** Does anything flip to true without an artifact? Does the same agent both do the work and grade it? The grader should be a separate run with no write tools and a fresh context that sees the diff and the criteria, not the reasoning that produced them.
- **Count-only stop.** Is the only stop a turn cap? Add the progress condition.
- **Unverifiable condition.** If a small evaluator model that cannot call tools had to judge this condition from what the agent said out loud, could it? If not, rewrite it around something the agent's own output demonstrates.
- **Rules that live only in the prompt.** Anything that must hold for the whole run belongs in the contract file, a re-injected instruction file, or a hook, not in the opening message.
- **A watcher agent.** Supervisors that monitor a run in flight currently detect failure about 29% of the time, and typically not until after the point of no return. Put the gate at the boundary instead.
- **Parallelism for throughput alone.** Splitting agents to divide labour mostly multiplies collisions and cost. The reported wins come from splitting to get an independent second opinion from a deliberately narrow context.
- **No give-up path.** Is there any way for this loop to conclude the goal is impossible?
- **Unbounded blast radius.** Can one bad iteration damage something the user cannot cheaply undo? Restrict the tool surface rather than asking the agent to be careful. A tool that is not granted cannot be misused.
- **Over-orchestration.** Five reviewers on a two-file change is a 20x cost for no benefit. Cut it.

## What to hand back

Show the user, in this order:

1. **The loop in three sentences** - what repeats, what proves it worked, when it stops. Plain language, no jargon. If this is hard to write, the design is not finished.
2. **The files** - path and one line each on what it does.
3. **How to start it** - the literal command.
4. **What will go wrong first** - the residual risks from step 5, and the signal that would tell them. This is the most valuable paragraph in the handoff; do not skip it because the design looks clean.

## Reference material

- `references/claude-code.md` - Claude Code wiring: goal conditions, Stop hooks, budgets, verifier subagents
- `references/copilot-cli.md` - Copilot CLI wiring: autopilot, agentStop hooks, credit caps, custom agents
- `references/failure-modes.md` - the evidence behind the checks in step 5, with sources. Read when the user pushes back on a recommendation or asks why
- `assets/LOOP.template.md` - the contract template
- `assets/verify_gate.py` - starting point for the stop-gate hook, adapted per platform
