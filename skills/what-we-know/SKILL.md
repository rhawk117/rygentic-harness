---
name: what-we-know
description: >-
  Consolidate the current understanding of a problem: a table of knowns with file:line citations, enumerated uncertainties, and — in interactive mode — each uncertainty resolved through the ask-user dialog, closing with a SWOT-level analysis in chat. In sprint mode (inside an active mightymodels loop) it gathers citations for the current task only and never asks the user anything. Use at the end of a triage or investigation session — "what do we know", "summarize what we've learned", "where are the unknowns", "consolidate the findings" — before prepare-handoff, and automatically per-task inside agents-assemble. Not for summarizing a repo or writing documentation.
---

# what-we-know

One skill, two modes, one hard rule separating them: **interactive mode may ask the user; sprint mode never does.** The mode split exists because this skill runs twice per loop iteration — an uncertainty that pauses a triage chat for the user's judgment is exactly right, and the same pause inside a running sprint stalls the loop on questions nobody wanted.

**Mode detection:** sprint mode when invoked from agents-assemble, when a `briefs/` directory exists in the active ticket, or when the dispatch says so. Interactive otherwise.

## Interactive mode (triage end)

1. **Knowns table.** Each row: claim + citation (`file:line`, command output, or document). A claim without a source goes in uncertainties, not knowns — the table's value is that every row survives being checked.
2. **Uncertainties.** Enumerate what is not established and would change the approach. When they exceed about six, group them and ask the user which matter — twenty questions is a failed triage wearing thoroughness as a costume.
3. **Resolve via ask-user.** One dialog, batched questions where the tool allows. Record each answer as a known (source: "user, this session"). No dialog available → list the questions you would ask, state your working assumption per question, proceed.
4. **SWOT, in chat.** Strengths and weaknesses of the current implementation; opportunities and threats of the proposed change. Engineering-flavored, a paragraph per letter at most — this is a decision aid, not a consulting deliverable.
5. Close with one paragraph: is this ready for prepare-handoff, and what would make it readier.

Output is **chat only**. No files — prepare-handoff persists what matters into ticket.yml and the issue; a triage file here would be a second source of truth waiting to drift.

## Sprint mode (per task, inside agents-assemble)

Gather citations for the current task and its scope: where the change lands, what touches it, what the ASKED stanza's `files-in-scope` should contain. Fresh citations every time — the plan is deliberately citation-free because citations rot during iteration; this step is where they get compiled at dispatch time, against the current HEAD.

An unresolved uncertainty in sprint mode is a one-line report to the primary: what is unknown, and the blast radius of guessing wrong. The primary decides ask-versus-proceed. You do not ask, and you do not silently guess on anything whose blast radius crosses a file boundary.

## Both modes

Citations follow the scout discipline: cite the line you (or your scout) actually opened. Delegate retrieval to scouts when they are available; the consolidation and the uncertainty judgment are yours, not theirs.
