# Template: next-session opening prompt

For the prompt that opens the next primary session, which baton-pass prints in chat. It is a pointer prompt. Every fact it would need already lives in a file, so the prompt names the files and the one skill to run, and copies nothing; a copied fact is a fact that drifts.

**Ten-second checklist:** every file it names exists before the prompt is written, and the snapshot was written successfully · the ramp or next skill is named once, per the routing table · the focus line (baton-pass) is verbatim · no fact from ticket.yml, the issue, or the baton is restated.

```text
<objective>Continue ticket <slug>: <focus line, verbatim, or the ramp's one-line purpose>.</objective>
<discovery>
Read, in order: .mightymodels/<slug>/ticket.yml; <the issue or plan>; <.mightymodels/<slug>/handoffs/snapshot.md and handoffs/BATON.md when baton-pass wrote them>.
Invoke prompting-subagents before the first dispatch.
</discovery>
<constraints>Invoke <the one skill: agents-assemble | game-plan | one-shot | review-circus> and follow it. <To land, in place of that sentence: Hand the user `/mightymodels:stick-the-landing <slug>`; only the user can start that skill.> Treat the files above as the only source of state.</constraints>
```

Slots: slug · focus or purpose · issue or plan · snapshot and baton paths when present · next skill.
