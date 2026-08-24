# The .mightymodels/ directory

Per-ticket, sparse, organized by unit of work. The unit of deletion is the unit of work: `/prune-ticket` removes a whole ticket directory, so rot cannot outlive its ticket.

```
.mightymodels/
├── <task-slug>/
│   ├── ticket.yml                     source of truth (see ticket-schema.md)
│   ├── plan.md                        formulate-plan ramp only; high-level, citation-free
│   ├── issue-body.md                  when no forge issue was created, or as the local draft
│   ├── handoffs/SPRINT.md             thin session bootstrap
│   ├── handoffs/REVIEW.md             thin review-session bootstrap
│   ├── briefs/task-NN.md              two halves, ≤80 lines (contracts.md)
│   ├── review/MERGE-VADER-REPORT.md
│   ├── review/UNCLE-BOB-REPORT.md
│   ├── whats-broken.md                only while a debug is live; regenerated per attempt
│   └── REPORT.md                      ≤50 lines, sprint summary
└── archives/<task-slug>.md            ≤30 lines, written by /prune-ticket
```

## Writer/reader matrix — one writer per file class

| Path | Writer | Readers |
|---|---|---|
| ticket.yml | prepare-handoff (then the user's hand) | every session |
| plan.md | formulate-plan primary, after user approval | primary, dispatch compilation |
| briefs/ ASKED half | primary at dispatch | engineer, verifying scout |
| briefs/ DONE half | engineer | primary, verifying scout |
| review/ | review skills | review-circus primary, the user |
| handoffs/ | prepare-handoff / finish-assembly | the next session's primary |
| REPORT.md | agents-assemble primary | finish-assembly, review-circus, prune-ticket |
| archives/ | prune-ticket | future humans |

## Thinness rule for handoffs

`SPRINT.md` and `REVIEW.md` contain zero facts that live in ticket.yml or the issue. They are a bootstrap pointer — read ticket.yml, read issue #N, your role, what to invoke — plus nothing. Duplicated facts drift, and the next session reads ticket.yml first anyway.

## Ignore ritual (idempotent, run at ticket creation)

```bash
git check-ignore -q .mightymodels 2>/dev/null || echo '.mightymodels/' >> .git/info/exclude
```

`info/exclude` is local and needs no commit — and it is the safer default: `briefs/` and `review/` carry raw command output that can hold secrets, and local-only exclusion means a careless `git add -A` cannot ship them. A team adopting mightymodels officially can promote to a committed `.gitignore`; when tracking is wanted, track `archives/` and `*/ticket.yml` only.
