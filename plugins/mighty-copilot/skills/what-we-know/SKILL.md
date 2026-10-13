---
name: what-we-know
description: >-
  Consolidate what is established about a problem, claim, behavior, or dependency into a knowns
  table with file:line or URL citations, an uncertainties list, and an analysis shaped by the
  question (causal chain for a behavior, verdict for a claim, fit for a dependency, SWOT for a
  proposed change), closing with a readiness read for the next stage. Reads the persisted
  lets-investigate ledger, treats entries from an older HEAD as leads to re-verify, and writes
  current verdicts back; assembles from cited facts or one scout wave otherwise. Interactive mode resolves
  uncertainties via AskUserQuestion; sprint mode (inside agents-assemble) compiles per-task
  citations and files-in-scope and never asks.
  Not for summarizing a repository, writing docs, or general knowledge questions.
when_to_use: >-
  Use for "what do we know", "summarize what
  we've learned", "where are the unknowns", "consolidate the findings", "before we ticket
  / plan / decide, what is verified", "do the swot pass", and as the facts packet before
  ask-an-adult.
argument-hint: "[question or claim]"
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_state__investigation
  - mcp__plugin_mightymodels_state__similarity
---

# what-we-know

Evidence accumulates in a conversation faster than anyone's sense of what it adds up to. This
skill turns the accumulated evidence into one picture the next stage can act on: what is
established and by which line, what is not, and what the facts say about the question that
started the work.

One skill, one vocabulary, several entry points, and one hard rule: **interactive mode may ask
the user; sprint mode never does.** The rule exists because the skill runs at two very
different moments. An uncertainty that pauses a triage chat for the user's judgment is exactly
right; the same pause inside a running sprint stalls the loop on questions nobody wanted.

**Mode detection:** sprint mode when invoked from agents-assemble, when a `briefs/` directory
exists in the active ticket, or when the dispatch says so. Interactive otherwise.

**Argument:** the question or claim to consolidate, given when the skill was started:
"$ARGUMENTS". Empty quotes mean nothing was given, and the target comes from the conversation or
from the skill that called this one.

The ledger belongs to lets-investigate, and this skill reads and writes it only through the
`investigation` tool, so the rows have one writer: call
`mcp__plugin_mightymodels_state__investigation`. The ledger-schema reference of lets-investigate,
`${CLAUDE_PLUGIN_ROOT}/skills/lets-investigate/references/ledger-schema.md`, describes the
fields.

## Where the evidence comes from

Consolidation starts from whatever evidence exists, and re-deriving evidence that already
carries a citation is waste.

- **An investigation exists.** Action `list` shows the ids; lets-investigate usually hands
  you one. Action `knowns` with the id prints every live entry marked `current` (written at
  this HEAD) or `lead` (written at an older one). Current Knowns lift straight into the knowns
  table, Open items into uncertainties, Decisions into the table with source `user`, and
  Resources carry forward. A lead is history, not evidence: the code may have moved since it
  was cited, so send it to the scout that produced it for one re-verification at HEAD, or carry
  it as an uncertainty. Decisions are settled whatever their HEAD; asking the user about one
  again tells them the gate meant nothing.
- **Cited facts are scattered through the conversation** with no ledger. Assemble them. A
  claim with a citation is a known; a claim someone made without one is an uncertainty, even
  when it came from the user, until the user confirms it at the dialog.
- **Nothing is established yet** and the user is asking cold. Open an investigation first
  (action `start`, `kind` one of `behavior`, `claim`, `research` or `change`, the proposed
  change being the SWOT target) so the verdicts have somewhere to persist:

  ```json
  {"request": {"action": "start", "payload": {"request": {"target": "<target line>", "kind": "change"}}}}
  ```

  Then bootstrap with one scout wave of
  two or three narrow retrieval questions aimed at the target, then consolidate what came
  back. If one wave is plainly not enough, that is an investigation, not a consolidation: say
  so and offer lets-investigate rather than running rounds under this skill's name.

## Interactive mode

**1. State the target and its shape.** One line, classified as lets-investigate classifies it:
a behavior to explain, a claim to check, a dependency or approach to research, or a proposed
change to weigh. The shape decides which analysis step four produces, so an unclassifiable
target is the first uncertainty.

**2. Knowns table.** One row per established fact: claim, citation (`file:line`, command
output, `URL#heading`, or `user, round N`), and what it bears on. Every row must survive being
checked; that is the table's whole value, so a claim without a citation goes to uncertainties
no matter how obvious it feels.

**3. Uncertainties.** Enumerate what is not established and would change what happens next:
the ticket's scope, the plan's sequence, the decision under consideration, or the debug's next
attempt. Each carries either what an inference rests on or where the answer lives. When they
exceed about six, group them and ask the user which matter; twenty questions is a failed
triage wearing thoroughness as a costume.

**4. Resolve through `AskUserQuestion`.** One dialog, up to four questions a call with two to
four options each (the user can always type an answer of their own), only for uncertainties
the user can actually answer (intent, production observations, history, priorities). Uncertainties a scout could answer get one more narrow dispatch instead
of a question; uncertainties nobody can answer yet are recorded as such. Record each answer as
a known with source `user`. When no dialog is available, list the questions you
would ask, state a working assumption for each, and proceed on the assumptions labelled as
assumptions.

**Persist before analysing.** Write the session's verdicts in one batch with
`mcp__plugin_mightymodels_state__investigation`: its `request` holds action `add`, and the
`payload`'s own `request` is `{"round": N}` (the next round after the ledger's latest):

```json
{"request": {"action": "add", "investigation_id": "ID", "payload": {"request": {"round": 2},
 "entries": [{"kind": "known", "text": "...", "cite": "src/queue.py:41", "source": "code-scout", "supersedes": [4]}]}}}
```

The batch
carries re-verified leads as new `known` entries that supersede the lead, scout findings that
contradict a lead as `open` entries superseding it, user answers as `known` with source `user`,
and each unresolved uncertainty as `open` with where its answer lives. The analysis below is
judgment and stays in chat; only cited facts and open questions go in the ledger. When the write is
rejected, fix the entry the error names; when it cannot be written at all, say so before
continuing, because a consolidation that is not persisted is lost at the next compaction.

**5. Analysis, shaped by the target.** A paragraph per part at most; this is a decision aid,
not a consulting deliverable.

- *Behavior*: the causal chain from trigger to observed effect, marking each link as
  established (with its citation) or gap. The gaps are the uncertainties that matter.
- *Claim*: a verdict of holds, does not hold, or holds under stated conditions, with the
  deciding citations named. "Partly" without conditions is not a verdict.
- *Dependency or approach*: fit between what the documentation says for the resolved version
  and what the repository needs from it, with each mismatch cited on both sides.
- *Proposed change*: SWOT. Strengths and weaknesses of the current implementation;
  opportunities and threats of the change. Engineering-flavored.

**6. Readiness, one paragraph.** Name the next stage the facts point at and what would make
the picture readier for it: open-ticket when there is work to ticket; game-plan or
one-shot when a ticket already exists; ask-an-adult when the remaining uncertainty is a
judgment call between defensible options; whats-broken when a reproduction is in hand; or no
work at all, when the claim did not hold or the behavior is intended. Offer the stage; do not
invoke it.

Output is chat plus the investigation's rows; nothing else is written. open-ticket lifts
what matters into ticket.yml and the issue, and a separate triage file here would be a second
source of truth waiting to drift. End the output with the Resources list and the
investigation id so open-ticket can name the sources and link the ledger.

## Sprint mode (per task, inside agents-assemble)

Compile fresh citations for the current task against the current HEAD: where the change lands,
what touches it, and what the ASKED stanza's `files-in-scope` should contain. Fresh every time,
because the plan is deliberately citation-free; citations rot during iteration and this step
is where they get compiled at dispatch time. When the ticket links an investigation, its
`investigation` `knowns` rows are leads for where to look, never citations to copy: re-verify before
any of them reaches the report. Sprint mode writes nothing; the brief's ASKED stanza is the
durable record of the task's citations, and a second copy in the ledger would drift.

Report to the primary in this shape, so it can be lifted into the ASKED stanza without
reformatting:

```markdown
## what-we-know, task-NN
Knowns:
- <claim> [<file:line>]
files-in-scope candidates: [<paths>]
Uncertainties:
- <unknown> | rests on: <evidence> | blast radius: <one file | crosses a file boundary | crosses a service or data boundary>
```

An uncertainty here is a report, not a question. The primary decides ask-versus-proceed; you
do not ask the user, and you do not silently guess on anything whose blast radius crosses a
file boundary. Blast radius is the primary's routing signal, so state it for every
uncertainty, including the ones you think are harmless.

Sprint mode never produces the analysis or readiness sections. The task's judgment lives in the
plan and the ASKED stanza; adding a SWOT per task is context spent on a question nobody asked.

## Both modes

Before a scout wave, search what the plugin already holds for this repository (ledger entries,
scout reports, review findings and crashouts) through `mcp__plugin_mightymodels_state__similarity`:

```json
{"request": {"action": "search", "query": "<the target or the task's intent>"}}
```

A row it returns says where earlier work looked. It is a lead, never a citation: re-verify it at
HEAD before it reaches the table, or carry it as an uncertainty.

Citations follow the scout discipline: cite the line you or your scout actually opened, and
carry `INFERRED` findings as uncertainties, never as knowns. Delegate retrieval to scouts when
they are available; the consolidation and the uncertainty judgment are yours, not theirs.

The vocabulary is shared with lets-investigate so the two compose without translation:

| ledger entry     | what-we-know                                       |
| ---------------- | -------------------------------------------------- |
| `known`, current | knowns table row                                   |
| `known`, lead    | re-verified at HEAD, or carried as an uncertainty  |
| `open`           | uncertainty                                        |
| `decision`       | knowns table row, source `user`, whatever its HEAD |
| `resource`       | Resources list, carried forward                    |
| `next`           | dropped; the investigation has ended               |
