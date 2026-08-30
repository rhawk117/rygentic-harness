---
name: prune-ticket
description: >-
  Close out a finished mightymodels unit of work: compress the ticket directory into a ≤30-line archive at .mightymodels/archives/<slug>.md (what shipped, PR link, key decisions, gotchas worth remembering), propose any cascading documentation updates as diffs for the user's approval, then delete the ticket directory. Refuses when live work remains — open report items, an active whats-broken.md, unpushed commits. Use for "/prune-ticket", "archive the ticket", "close out the mightymodels ticket", "clean up the ticket dir for X". Not for deleting branches, closing issues, or general repo cleanup.
---

# prune-ticket

The lifecycle's last move, and the reason `.mightymodels/` never becomes a landfill: the unit of deletion is the unit of work. Everything in the ticket directory was working state; what deserves to outlive the ticket gets 30 lines in the archive and a place in the repo's real documentation — nothing else survives.

## Sequence

**1. Refuse live work.** Before anything: `REPORT.md` open threads, an active `whats-broken.md`, unpushed commits on the ticket's branch, unchecked tasks in the issue. Any of these → refuse, list exactly what's blocking, stop. Pruning a live ticket doesn't close work, it hides it.

**2. Write the archive first.** `.mightymodels/archives/<task-slug>.md`, 30 lines max, written and verified *before* any deletion:

```markdown
# <slug>
shipped: <one line> · PR: <link> · issue: <#n> · pruned: <date>
decisions: <the 2-4 choices someone will ask about in six months, one line each>
gotchas: <what bit us, what to know before touching this area again>
```

The compression test: a teammate touching this area next quarter reads 30 lines and knows what happened and what to watch for. History beyond that lives in git, the issue, and the PR — the archive is a pointer with judgment, not a copy.

**3. Extract cascading documentation.** Read `REPORT.md` and the review reports for "this changed how X works" signals — a new config key, a changed workflow, a retired endpoint. Propose the corresponding updates to the repo's real docs (AGENTS.md, README, runbooks) **as diffs, applied only on the user's approval**. Never auto-commit documentation; wrong docs outlive wrong code.

**4. Delete the ticket directory.** After the archive exists and doc diffs are settled: remove `.mightymodels/<task-slug>/` entirely. Confirm what was removed in one line.

When `.mightymodels/` is tracked by the repo (team mode), the deletion is a commit — say so and let the user commit it with their next batch rather than committing unilaterally.
