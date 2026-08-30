# Loop contract: <name>

Re-read this file at the start of every iteration. It is the loop's rules; the conversation is not.

## Goal

<One sentence. What is true when this loop is finished.>

## Unit of work

One iteration handles: <one ticket / one failing test / one module>

It may touch: <explicit paths or modules>
It must not touch: <paths owned by another worker, or off limits>

## Acceptance criteria

Every criterion starts `false`. A criterion flips to `true` only after the evidence artifact has been read in this session. The agent's own judgment is not evidence.

| # | Criterion | Check | Evidence artifact | Passing looks like | Status |
|---|---|---|---|---|---|
| 1 | <what must be true> | `<command>` | `<path or output>` | <exit 0 / count / string> | false |
| 2 | | | | | false |

## Stop conditions

- **Progress**: <e.g. all criteria true, or two consecutive iterations with no change to the criteria table>
- **Cost backstop**: <turn cap> turns, <spend cap>
- **Impossible**: if a criterion cannot be satisfied as written, stop, mark it impossible, and record why here rather than rewriting the criterion to something easier.

## Escalation

| Condition | Action |
|---|---|
| Auth failure, exhausted credit, unrecoverable context overflow, model unavailable | stop, return to human |
| Rate limit, overload, transient network | back off, keep the loop alive |
| A check fails | remediate, iterate |
| The same check fails the same way twice | stop, escalate with both failure outputs |

## Out of scope

<Things the loop must not decide on its own. Anything here needs a human.>

## Progress log

Append one line per iteration: what changed, which criteria moved, what the check said. Keep it terse; this file is re-read every iteration.

- <iteration 1>
