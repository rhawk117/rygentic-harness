---
name: lets-investigate
description: >-
  Run a chat-first investigation as a gated loop: frame one target, dispatch scouts for
  repository facts and documentation facts, fold every report into a restated in-chat ledger
  (knowns, open questions, decisions, resources), then stop at an ask-user gate where the user
  chooses to dig further, redirect, or consolidate. Use at the START of work, before any ticket
  exists, whenever the user wants to understand something before acting: "let's investigate X",
  "look into this claim", "triage this bug report", "why would Y be happening", "dig into this
  error", "how does library Z actually handle this, check the docs and our usage", "gather
  context on how this subsystem works before we plan". Also use for research questions about a
  dependency, API, protocol, or tool the repository relies on. Writes no files and changes
  nothing. Not for reviewing a branch (merge-vader), grading a codebase (uncle-bob), debugging
  with a known reproduction (whats-broken), or non-engineering research such as market or
  vendor comparisons.
---

# lets-investigate

The opening move: understand before anything gets named, ticketed, or built. The session's
product is a ledger, restated in chat at the end of every round, that the user has agreed is
sufficient. Nothing is written to disk; prepare-handoff persists what matters once there is
something worth persisting.

<important>Invoke `using-mightymodels` before the first dispatch.</important>

The skill runs as a loop with a gate, and the gate is the point. An investigation that runs
until the primary feels done ends up wherever the primary's curiosity went. One that stops after
every round and asks the user whether the picture is sufficient ends up where the user needs
it, and the user hears about a dead end after one round instead of five.

## Round zero: frame the target

Write the target as one line the user can disagree with, then classify it:

- **Explain a behavior**: something happens and nobody knows why yet.
- **Check a claim**: someone asserted a fact about the system; find out whether it holds.
- **Research an approach or dependency**: how a library, API, protocol, or tool behaves, and
  how the repository actually uses it.

The classification decides where the first questions go. A behavior needs the code path and
the runtime configuration; a claim needs the exact lines that would make it true or false; a
research question needs the documentation for the version in the lockfile and the call sites
that depend on it.

Put the framing to the user through the ask-user dialog before dispatching anything: the
target line, the classification, and one question asking what they already know or have ruled
out. Scouts pointed at a vague target return precise answers to the wrong question, and facts
the user already holds cost nothing to record and a round to rediscover. Each answer becomes a
ledger entry with source `user, round 0`.

## Each round

**1. Choose two or three questions the ledger cannot answer.** Take them from the ledger's
Next section (round one takes them from the framing). Route each by where the answer lives:

- Repository facts (definitions, call sites, config values, versions, one command's output) go
  to a scout with exact paths, symbols, and search terms.
- External facts (documented behavior, changelog entries, defaults, deprecations) go to a
  scout with the URL or the search phrase, the version pinned in the lockfile, and the specific
  question. A scout fetches and cites the page; it does not summarize a library.
- Facts only the user holds (intent, production observations, history) are held for the gate,
  where they are asked alongside the round's decision.

Shape every scout question as locate, list, extract, fetch, or run. A "why" or "should" bounces
back as `NEEDS-ANALYSIS` and costs a dispatch; that judgment is yours, made in the open and
recorded as a decision only once the user agrees with it.

**2. Dispatch through promptlint.** Scouts have not seen this conversation, so each dispatch
carries the question, the scope, and the citation form wanted back. No ticket exists, so no
`subagent-models` routing applies: scouts run on their agent-file default.

**3. Fold reports into the ledger.** Each verdict has one destination:

- `VERIFIED` becomes a Known, with its `file:line` or `URL#heading` citation.
- `INFERRED` becomes an Open question stating what the inference rests on. It never becomes a
  Known by being repeated.
- `NEEDS-ANALYSIS` is a judgment call for you. Make it in chat with the evidence in view; it
  becomes a Decision only if the user accepts it at the gate.
- `UNKNOWN-BLOCKED` becomes an Open question carrying the location the scout named. If that
  location is outside the repository and the docs, it is a question for the user.
- Two scouts disagreeing is a finding. Record the contradiction as its own Open question with
  both citations; never reconcile it silently.

**4. Restate the whole ledger.** Not a delta. The ledger is the only state this session has,
and the last restatement is what what-we-know and prepare-handoff will read.

**5. Stop at the gate.** Open the ask-user dialog with the round's decision and any questions
held for the user, batched into one dialog where the tool allows. The decision offers exactly
these choices:

- **Sufficient**: consolidate through what-we-know.
- **Dig further**: run the Next questions as proposed.
- **Redirect**: the target or the Next questions need changing; the user says how.
- **Stop here**: keep the ledger in chat and end without consolidating.

When you believe the picture is complete, say so in the dialog text and recommend Sufficient,
and still ask. When the Next questions would not change the picture, say that too; a user who
hears "one more round would only confirm what we have" can make a real choice. What you do
not do is skip the gate because the answer seems obvious. Ending someone's triage for them is
how half-understood problems get ticketed.

When no dialog tool is available, ask the same question in chat with the four options spelled
out, and wait for the answer.

## The ledger

Restate it in this shape every round. The sections are ordered so what-we-know can lift Knowns
and Open straight into its knowns table and uncertainties list.

```markdown
## Ledger, round N
Target: <one line> (<behavior | claim | research>)

### Knowns
- <claim> [<file:line> | <URL#heading> | user, round N]

### Open
- <question>: rests on <what the inference rests on> | answer lives in <location>

### Decisions
- R<n>: <what was settled> (user)

### Resources
- <path or URL>: <what it answered, and the version or date if it matters>

### Next
- <exact question>: <scout, repository | scout, docs | user>
```

Rules that keep the ledger honest:

- A Known has a citation or it is not a Known. "The retry wrapper is applied everywhere" with
  no line goes in Open.
- A Decision carries the user's word from a gate or a framing dialog. Your own conclusion,
  however well cited, is a Known or an Open item until the user takes it.
- Resources record where facts came from so prepare-handoff can name them in the issue and the
  next session does not re-find them. A fetched docs page goes here with the version it
  describes; a docs page for the wrong version is a Resource with a warning, not a Known.
- The ledger stays readable in one screen. When it grows past roughly forty lines, merge
  Knowns that say the same thing, retire Open questions the user has waved off (recording
  the wave-off as a Decision), and drop Next items the user has redirected away from. Growth
  past that point means the investigation is sprawling, which is itself something to say at
  the gate.

## Research targets

A research question is answered by two facts joined together: what the documentation says for
the version the repository resolves, and where the repository depends on that behavior. One
without the other is trivia. So a research round usually pairs one docs scout with one
repository scout: the docs scout fetches the page for the pinned version and cites the section;
the repository scout cites the lockfile line and the call sites. Prefer primary sources, in this
order: the project's official documentation, its changelog or release notes, the dependency's
own source at the resolved version. A blog post or forum answer is a lead that names where the
primary source is, not a citation.

## Ending

The loop ends only at a gate. On Sufficient, offer what-we-know and hand it the final ledger as
its input; never invoke it unasked. On Stop here, leave the final ledger as the last message so
it can be copied forward.

## Boundaries

Read-only throughout: no files, no `.mightymodels/`, no edits, no commands beyond the single
read-only command a scout runs. If the investigation surfaces something needing immediate
action (a live secret, a data-loss path in production), say so plainly and let the user act;
the pipeline is for work, not for emergencies.

## Example round

Target: `Explain a behavior`: the retry queue drains at roughly a tenth of its configured rate
after 2am.

Round 1 dispatches a repository scout for the drain loop's definition and its concurrency
setting, a repository scout for every reader of `RETRY_CONCURRENCY`, and a docs scout for the
queue client's documented default backoff at the version in `uv.lock`. The reports come back
`VERIFIED`, `VERIFIED`, and `INFERRED` (the docs page found is for a newer major version). The
ledger restates with two Knowns, one Open ("documented backoff for 3.2.x: rests on a 4.x page;
answer lives in the 3.x changelog"), one Resource carrying the version warning, and a Next
section proposing the 3.x changelog fetch and a scout to run the drain loop's unit test once.
The gate asks the user to choose, and adds the held question: "does the slowdown correlate
with the nightly compaction job you mentioned?" The user picks Dig further and answers yes;
both land in the ledger as `user, round 1` entries before round 2 dispatches.
