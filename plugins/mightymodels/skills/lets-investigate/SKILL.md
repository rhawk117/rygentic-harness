---
name: lets-investigate
description: >-
  Open a chat-first triage session on a problem, claim, error, or unexplained behavior: the primary delegates retrieval to scout subagents (one narrow question each), accumulates cited facts in chat, and ends by offering what-we-know once the fact base feels sufficient. Use at the START of work, before any ticket exists — "let's investigate X", "look into this claim", "triage this bug report", "why would Y be happening", "dig into this error". Writes no files and changes nothing. Not for reviewing a branch (merge-vader), not for grading a codebase (uncle-bob), and not for debugging with a known reproduction (whats-broken).
---

# lets-investigate

The opening move: understand before anything gets named, ticketed, or built. This session's output is understanding — cited facts accumulated in chat plus the scout reports in context. No files, no `.mightymodels/`, no edits; artifacts come later, from prepare-handoff, once there is something worth persisting.

<important>YOU MUST invoke `using-mightymodels`</important>

## How it runs

**State the target in one line** — the claim to check, the behavior to explain, the question to answer. If the user's framing is vague, sharpen it with them before dispatching anything; scouts pointed at a vague target return precise answers to the wrong question.

**Delegate retrieval, keep judgment.** Scouts take one narrow retrieval question each, with exact paths, symbols, and search terms — they have not seen this conversation. Shape questions as locate/list/extract/run, never should/why/sound (those bounce back NEEDS-ANALYSIS and waste the dispatch). No ticket exists yet, so no `subagent-models` routing applies: scouts run on their agent-file default. Two or three scouts per wave; let wave one's answers write wave two's questions.

**Accumulate with citations.** Every fact carries its `file:line` or command output. Contradictions between scout findings are findings themselves — surface them, don't reconcile them silently.

**Know when to stop.** The fact base is sufficient when new scout questions stop changing the picture. That is the moment to **offer** what-we-know — never auto-invoke it. The user decides when investigation is done; ending someone's triage for them is how half-understood problems get ticketed.

## Boundaries

Read-only throughout — this session changes nothing and writes nothing. If the investigation surfaces something that needs immediate action (a live secret in the repo, a data-loss bug in production), say so plainly and let the user act; the pipeline is for work, not for emergencies.
