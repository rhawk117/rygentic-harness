# Workflow

The five phases of every merge-vader review, read before Phase 0. `dimensions.md` and `report-template.md` are next to this file; the division of labor is a section of the skill's SKILL.md, which is already in your context.

## Phase 0: ground truth

Establish what you are reviewing before forming any opinion:

```bash
git rev-parse --abbrev-ref HEAD          # confirm the branch under review
git merge-base <base> <branch>           # the true fork point
git diff --stat <merge-base>...<branch>
git log --oneline <merge-base>..<branch>
git diff <merge-base>...<branch>         # the review target
```

The base is whatever the user names, otherwise the repository default branch. Diff against the merge-base with three dots so you review only the branch's own work, not upstream drift. If the working tree is dirty, review committed state and say so in the report.

Also walk the branch history itself, `git log -p <merge-base>..<branch>`, at least skimmed. Files added and later deleted on the branch (credentials, dumps, debug scripts) are still in history after merge, and the endpoint diff hides them.

Size triage. Under roughly 300 changed lines: read everything. Up to roughly 2000: read everything, concentrate scouts on risk hotspots. Beyond that: fully read the files matching risk heuristics (auth, crypto, input handling, CI and build config, dependency manifests, public API), skim the rest, and list the skimmed files in the report's Not verified section. Never silently sample.

### Phase 1: read the diff, build the ledger

Read [dimensions.md](dimensions.md) first. It holds the four checklists (security, SDLC regressions, quality and maintainability, documentation drift) with severity anchors and a scout question bank per dimension.

Then read every hunk. As you read, keep a ledger with four columns: file, observation, dimension, and the fact question that would confirm or kill the observation. Most rows need no scout; the diff itself is the evidence. A question earns a dispatch only when its answer lies outside the diff.

Generate blast-radius questions mechanically from the change type:

| Change in the diff                                                | Scout question                                                                         |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Public symbol renamed, removed, or re-signed                      | List call sites of `<old name>` outside `<changed files>`, file:line                   |
| Function behavior or contract changed                             | Which test files reference `<symbol or module>`? file:line                             |
| Test deleted or skipped                                           | Does anything else exercise `<covered module>`? List test files referencing it         |
| Config key, flag, env var, or endpoint added or removed           | Grep `docs/`, `README*`, `.env.example`, deploy manifests for `<old>` and `<new>`      |
| New dependency                                                    | What version does the lockfile resolve `<pkg>` to, and is it pinned?                   |
| CI workflow edited                                                | Show the steps of `<workflow file>` on `<base>`, so you can diff intent, not just text |
| Sensitive sink touched (SQL, exec, deserialize, path build, HTML) | Show the 5 lines preceding each call to `<function>` at the call sites already located |

### Phase 2: dispatch scouts

Send independent questions as one parallel wave, 4 to 6 at a time so results stay digestible. Questions raised by wave one become wave two. One question per scout. When a narrower follow-up emerges from a scout's answer, reuse that scout's conversation instead of dispatching a fresh one; scouts stay resident for exactly this.

Handle their verdicts:

| Scout verdict     | Your action                                                                                                                    |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `VERIFIED`        | Usable as finding evidence. Open the cited line yourself before it drives a BLOCK.                                             |
| `INFERRED`        | A lead, not evidence. Confirm with your own read or a follow-up, or mark the finding Confidence: Low.                          |
| `NEEDS-ANALYSIS`  | The judgment is yours. Do it with the facts already in the scout's findings; its `<follow_up>` usually names the missing fact. |
| `UNKNOWN-BLOCKED` | Record in the report's Not verified section with what would resolve it. Unverified risk is a finding class, not a shrug: a security question left UNKNOWN-BLOCKED is also written as a High finding in the `security` dimension whose Fix is to answer it.       |

### Phase 3: judge

Convert the ledger plus scout facts into findings. Every finding carries:

- **ID**: MV-1, MV-2, and so on, stable within the report, so downstream agents can reference them.
- **Dimension**: security, sdlc, quality, docs, or plan. It decides how review-circus records the finding: `security` marks a security defect, `quality` a quality finding, the rest defects.
- **Severity**: per the ladder below.
- **Evidence**: `file:line` plus at most one quoted line, from the diff or a verified scout citation.
- **Typed evidence**: a `quality` finding at Medium or above carries a typed bullet naming one kind (`Evidence (metric): <cite>`, or `idiom` or `convention` in its place), as idiom-evidence.md defines.
- **Why it matters**: the concrete failure mode in one or two sentences.
- **Fix**: the action an engineer agent could take without re-deriving your analysis.
- **Verify**: how to confirm the fix landed (a command, a grep, a test to run).
- **Confidence**: High when the evidence is verified, Low when it rests on inference.
- **Signals** (optional): qualitylens churn or coupling values that bear on the finding, with the analysis name.
- **Architect escalation** (optional): request it only when the fix needs a design decision beyond the finding's own Fix line, and say why. review-circus decides; you never dispatch an implementer.

Severity ladder:

- **Critical**: merging ships harm now. Exploitable security defect reachable from an untrusted boundary, committed secret (including branch history), removed authn or authz enforcement, data loss or corruption path.
- **High**: merging ships unacceptable risk, or removes the net that catches future defects. Security defect requiring preconditions, deleted or skipped test without replacement, weakened CI gate, breaking change with confirmed live callers, unexplained security-suppression marker, plan commitment silently dropped.
- **Medium**: will cost real time later. New logic without tests, compounding maintainability debt, public doc drift, swallowed errors, non-security suppressions without justification.
- **Low**: nits, style, internal doc drift.

Two guards. Inflation: a finding is Critical only if you can name the attacker action or the failure event; if you cannot, it is High at most. A report that cries Critical loses the credibility that makes its next BLOCK stick. Deflation: a deleted test or a lowered coverage gate is High even though no shipped line is wrong; the safety net is part of the product.

### Phase 4: verdict and report

The verdict is deterministic:

- Any Critical or High finding: **BLOCK**.
- Otherwise, any Medium: **MERGE WITH CONDITIONS**, with each condition enumerated.
- Otherwise: **CLEAR**.
- Cap: if any security-relevant question ended `UNKNOWN-BLOCKED`, or blast-radius checks could not be performed, the verdict cannot be CLEAR. You cannot clear what nobody could see.

Return the complete report as your whole response, following [report-template.md](report-template.md) exactly; the `VERDICT:` line must stay machine-greppable. review-circus writes it to `MERGE-VADER-REPORT.md` in the review run directory unchanged, so anything outside the template ends up in the file.

Report clean dimensions too, one line each stating what was checked and found clean. "Nothing found" is information the merger needs, and its absence reads as "not examined".
