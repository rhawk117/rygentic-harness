---
name: what-we-know
description: >-
  Consolidate what is established about a problem, claim, behavior, or dependency into a knowns
  table with file:line or URL citations, an uncertainties list, and an analysis shaped by the
  question (causal chain for a behavior, verdict for a claim, fit for a dependency, SWOT for a
  proposed change), closing with a readiness read for the next stage. Consumes a
  lets-investigate ledger when one exists, assembles from cited facts otherwise, and bootstraps
  with one scout wave when starting cold. Interactive mode resolves
  uncertainties via the ask-user dialog; sprint mode (inside agents-assemble) compiles per-task
  citations and files-in-scope and never asks. Use for "what do we know", "summarize what
  we've learned", "where are the unknowns", "consolidate the findings", "before we ticket
  / plan / decide, what is verified", "do the swot pass", and as the facts packet before ask-an-adult. Not for summarizing a repository, writing docs or postmortems, or general
  knowledge questions with nothing to consolidate.
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

## Where the evidence comes from

Consolidation starts from whatever evidence exists, and re-deriving evidence that already
carries a citation is waste.

- **A lets-investigate ledger is in the conversation.** Consume it. Its Knowns lift straight
  into the knowns table, its Open items into uncertainties, its Decisions into the table with
  source `user, round N`, and its Resources carry forward untouched. A Decision is settled;
  asking the user about it again tells them the gate meant nothing.
- **Cited facts are scattered through the conversation** with no ledger. Assemble them. A
  claim with a citation is a known; a claim someone made without one is an uncertainty, even
  when it came from the user, until the user confirms it at the dialog.
- **Nothing is established yet** and the user is asking cold. Bootstrap with one scout wave of
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

**4. Resolve through the ask-user dialog.** One dialog, questions batched where the tool
allows, only for uncertainties the user can actually answer (intent, production observations,
history, priorities). Uncertainties a scout could answer get one more narrow dispatch instead
of a question; uncertainties nobody can answer yet are recorded as such. Record each answer as
a known with source `user, this session`. When no dialog is available, list the questions you
would ask, state a working assumption for each, and proceed on the assumptions labelled as
assumptions.

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
the picture readier for it: prepare-handoff when there is work to ticket; game-plan or
yolo when a ticket already exists; ask-an-adult when the remaining uncertainty is a
judgment call between defensible options; whats-broken when a reproduction is in hand; or no
work at all, when the claim did not hold or the behavior is intended. Offer the stage; do not
invoke it.

Output is **chat only**. No files. prepare-handoff persists what matters into ticket.yml and
the issue; a triage file here would be a second source of truth waiting to drift. End the
output with the Resources list so prepare-handoff can name the sources in the issue.

## Sprint mode (per task, inside agents-assemble)

Compile fresh citations for the current task against the current HEAD: where the change lands,
what touches it, and what the ASKED stanza's `files-in-scope` should contain. Fresh every time,
because the plan is deliberately citation-free; citations rot during iteration and this step
is where they get compiled at dispatch time.

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

Citations follow the scout discipline: cite the line you or your scout actually opened, and
carry `INFERRED` findings as uncertainties, never as knowns. Delegate retrieval to scouts when
they are available; the consolidation and the uncertainty judgment are yours, not theirs.

The vocabulary is shared with lets-investigate so the two compose without translation:

| lets-investigate ledger | what-we-know |
| ----------------------- | --------------------------------------- |
| Known                   | knowns table row                        |
| Open                    | uncertainty                             |
| Decision                | knowns table row, source `user, round N` |
| Resource                | Resources list, carried forward         |
| Next                    | dropped; the investigation has ended    |
