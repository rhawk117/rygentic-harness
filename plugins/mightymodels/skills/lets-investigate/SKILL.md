---
name: lets-investigate
description: >-
  Run a chat-first investigation as a gated loop: frame one target, dispatch scouts for
  repository facts and documentation facts, fold every report into a restated in-chat ledger
  (knowns, open questions, decisions, resources), then stop at an AskUserQuestion gate where the user
  chooses to dig further, redirect, or consolidate. Persists its ledger as rows
  in the state database and changes nothing else. Not for reviewing a branch or grading a codebase (review-circus), debugging
  with a known reproduction (whats-broken), or non-engineering research such as market or
  vendor comparisons.
when_to_use: >-
  Use at the START of work, before any ticket
  exists, whenever the user wants to understand something before acting: "let's investigate X",
  "look into this claim", "triage this bug report", "why would Y be happening", "dig into this
  error", "how does library Z actually handle this, check the docs and our usage". Also for
  research questions about a dependency, API, protocol, or tool the repository relies on.
argument-hint: "[question, claim or error]"
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_state__investigation
---

# lets-investigate

The opening move: understand before anything gets named, ticketed, or built. The session's
product is a ledger, restated in chat at the end of every round, that the user has agreed is
sufficient. The ledger is persisted before every gate by the `investigation` tool, so a compaction
or a new conversation resumes from the database instead of from memory; the chat restatement is
the tool's own rendering, so the two cannot disagree.

State goes through the plugin's MCP tool, called by full name:
`mcp__plugin_mightymodels_state__investigation`. Read `references/ledger-schema.md` when an
entry is rejected.

<important>Invoke `prompting-subagents` before the first dispatch.</important>

The skill runs as a loop with a gate, and the gate is the point. An investigation that runs
until the primary feels done ends up wherever the primary's curiosity went. One that stops after
every round and asks the user whether the picture is sufficient ends up where the user needs
it, and the user hears about a dead end after one round instead of five.

## Round zero: frame the target

**Argument:** what to investigate, given when the skill was started: "$ARGUMENTS". Empty quotes
mean nothing was given, and the target comes from the conversation.

Write the target as one line the user can disagree with, then work out which of these it is (the
user confirms the classification when the ledger opens):

- **Explain a behavior**: something happens and nobody knows why yet.
- **Check a claim**: someone asserted a fact about the system; find out whether it holds.
- **Research an approach or dependency**: how a library, API, protocol, or tool behaves, and
  how the repository actually uses it.

The classification decides where the first questions go. A behavior needs the code path and
the runtime configuration; a claim needs the exact lines that would make it true or false; a
research question needs the documentation for the version in the lockfile and the call sites
that depend on it.

Put the framing to the user through one `AskUserQuestion` dialog before dispatching anything: the
target line, and one question asking what they already know or have ruled out (the user can
always type an answer of their own). Scouts pointed at a vague target return precise answers to the wrong question, and facts
the user already holds cost nothing to record and a round to rediscover.

Once the user confirms the target, open the ledger and record their answers as round 0:

Call `mcp__plugin_mightymodels_state__investigation` with action `start` and the target, and
leave `kind` out: the tool asks the user for the classification and records the answer. The kinds
are `behavior`, `claim`, `research` and `change` (a proposed change to weigh, which what-we-know
opens):

```json
{"request": {"action": "start", "payload": {"request": {"target": "<target line>"}}}}
```

An answer starting `needs input` means no one could be asked through the tool: put the question
it names to the user in one `AskUserQuestion` dialog, then call again with `kind` in the request.

`start` returns the investigation id; every later call names it. Then the same tool with action
`add` records the user's answers:

```json
{"request": {"action": "add", "investigation_id": "ID", "payload": {"request": {"round": 0},
 "entries": [{"kind": "known", "text": "<fact the user holds>", "cite": "user", "source": "user"}]}}}
```

When the user is resuming an earlier investigation, action `list` shows the ids and action
`render` restores the ledger.

## Each round

**1. Choose two or three questions the ledger cannot answer.** Take them from the ledger's
Next section (round one takes them from the framing). Route each by where the answer lives:

- Repository facts (definitions, call sites, config values, versions, one command's output) go
  to code-scout with exact paths, symbols, and search terms.
- External facts (documented behavior, changelog entries, defaults, deprecations) go to a
  web-scout with the URL or the search phrase, the version pinned in the lockfile, and the
  specific question. web-scout fetches and cites the page; it does not summarize a library.
- Facts only the user holds (intent, production observations, history) are held for the gate,
  where they are asked alongside the round's decision.

Shape every scout question as locate, list, extract, fetch, or run. A "why" or "should" bounces
back as `NEEDS-ANALYSIS` and costs a dispatch; that judgment is yours, made in the open and
recorded as a decision only once the user agrees with it.

**2. Dispatch through prompting-subagents.** Scouts have not seen this conversation, so each dispatch
carries the question, the scope, and the citation form wanted back. No ticket exists, so no
`subagent-models` routing applies: scouts run on their agent-file default.

**3. Fold reports into the ledger.** Each verdict has one destination, and each destination
is an entry `kind`:

- `VERIFIED` becomes a `known`, with its `file:line` or `URL#heading` citation.
- `INFERRED` becomes an `open` question stating what the inference rests on. It never becomes a
  Known by being repeated.
- `NEEDS-ANALYSIS` is a judgment call for you. Make it in chat with the evidence in view; it
  becomes a Decision only if the user accepts it at the gate.
- `UNKNOWN-BLOCKED` becomes an Open question carrying the location the scout named. If that
  location is outside the repository and the docs, it is a question for the user.
- Two scouts disagreeing is a finding. Record the contradiction as its own Open question with
  both citations; never reconcile it silently.

**4. Persist, then restate the whole ledger.** Write the round's entries in one `add` call:

```json
{"request": {"action": "add", "investigation_id": "ID", "payload": {"request": {"round": 1}, "entries": [
  {"kind": "known", "text": "...", "cite": "src/queue.py:41", "source": "code-scout"},
  {"kind": "open", "text": "... rests on ...", "cite": "CHANGELOG 3.x", "source": "web-scout"},
  {"kind": "known", "text": "...", "cite": "https://...#backoff", "source": "web-scout", "supersedes": [4]},
  {"kind": "next", "text": "<exact question>", "source": "code-scout"}
]}}}
```

Then call `mcp__plugin_mightymodels_state__investigation` with action `render`:

```json
{"request": {"action": "render", "investigation_id": "ID"}}
```

An answered Open question is retired by the entry that answers it (`supersedes`, naming an
entry from an earlier call), never edited. Paste the `render` output into chat as the
restatement: not a delta, the whole ledger.
If `add` is rejected, fix the entry the error names and retry; if it cannot be written at all,
stop at the gate and say so. A gate on an unpersisted round is the loss this skill exists to
prevent.

**5. Stop at the gate.** Open an `AskUserQuestion` dialog with the round's decision and any questions
held for the user, batched into one call (up to four questions). The decision offers exactly
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

`render` prints it in this shape. The sections are ordered so what-we-know can lift
Knowns and Open straight into its knowns table and uncertainties list.

```markdown
## Ledger, round N
Target: <one line> (<behavior | claim | research | change>)

### Knowns
- e<seq>: <claim> [<file:line> | <URL#heading> | user] (<source>, round N)

### Open
- e<seq>: <question>: rests on <what> [<where the answer lives>] (<source>, round N)

### Decisions
- e<seq>: <what was settled> (user, round N)

### Resources
- e<seq>: <what it answered, and the version or date if it matters> [<path or URL>] (...)

### Next
- e<seq>: <exact question> (<code-scout | web-scout | user>, round N)
```

Rules that keep the ledger honest:

- A Known has a citation or it is not a Known. "The retry wrapper is applied everywhere" with
  no line goes in Open.
- A Decision carries the user's word from a gate or a framing dialog. Your own conclusion,
  however well cited, is a Known or an Open item until the user takes it.
- Resources record where facts came from so open-ticket can name them in the issue and the
  next session does not re-find them. A fetched docs page goes here with the version it
  describes; a docs page for the wrong version is a Resource with a warning, not a Known.
- The ledger stays readable in one screen. When it grows past roughly forty lines, merge
  Knowns that say the same thing (one new entry superseding both), retire Open questions the
  user has waved off (a Decision superseding them), and supersede Next items the user has
  redirected away from. Growth
  past that point means the investigation is sprawling, which is itself something to say at
  the gate.

## Research targets

A research question is answered by two facts joined together: what the documentation says for
the version the repository resolves, and where the repository depends on that behavior. One
without the other is trivia. So a research round usually pairs one web-scout with one
code-scout: web-scout fetches the page for the pinned version and cites the section;
code-scout cites the lockfile line and the call sites. Prefer primary sources, in this
order: the project's official documentation, its changelog or release notes, the dependency's
own source at the resolved version. A blog post or forum answer is a lead that names where the
primary source is, not a citation.

## Ending

The loop ends only at a gate. On Sufficient, offer what-we-know and hand it the investigation
id; never invoke it unasked. On Stop here, leave the final rendered ledger as the last message;
the database keeps it for a later session.

## Boundaries

Read-only apart from the ledger rows: no other writes, no edits, no commands beyond
the `investigation` tool and the single read-only command a scout runs. If the investigation surfaces something needing immediate
action (a live secret, a data-loss path in production), say so plainly and let the user act;
the pipeline is for work, not for emergencies.

## Example round

Target: `Explain a behavior`: the retry queue drains at roughly a tenth of its configured rate
after 2am.

Round 1 dispatches a code-scout for the drain loop's definition and its concurrency
setting, a code-scout for every reader of `RETRY_CONCURRENCY`, and a web-scout for the
queue client's documented default backoff at the version in `uv.lock`. The reports come back
`VERIFIED`, `VERIFIED`, and `INFERRED` (the docs page found is for a newer major version). The
ledger restates with two Knowns, one Open ("documented backoff for 3.2.x: rests on a 4.x page;
answer lives in the 3.x changelog"), one Resource carrying the version warning, and a Next
section proposing the 3.x changelog fetch and a code-scout to run the drain loop's unit test once.
The gate asks the user to choose, and adds the held question: "does the slowdown correlate
with the nightly compaction job you mentioned?" The user picks Dig further and answers yes;
both land in the ledger as `user, round 1` entries before round 2 dispatches.
