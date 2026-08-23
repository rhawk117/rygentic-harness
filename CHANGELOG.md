# Changelog

## 0.4.0 — mightymodels rename + humansays toolchain (2026-08-20)

The plugin is mightymodels now: every occurrence renamed (package `mightymodels_evals`, `.mightymodels/` ticket dirs, manifests, docs, datasets, fixture templates), author set to BUSYSRE, LICENSE removed. Project restructured to the humansays shape: root `pyproject.toml` (Python 3.14; the package stays under `evals/src`), root `tests/`, `.ruff.toml` and `.pytest.toml` copied from humansays and adapted (curated rule set at line-length 90 replaces select-ALL; pytest 9 with coverage, random order, warnings-as-errors), scripts/ repurposed from humansays (log/format/lint/ci/precheck, commit-msg checker) plus `security.sh`, a six-class prompt-injection scanner over skills/ and agents/ (verified against planted overrides, pipe-to-shell, and zero-width Unicode; the PCRE arm fails loudly if a pattern cannot compile). Pre-commit hooks (ruff, markdownlint-cli2, whitespace, the security scan, commit-msg format; hook scripts stay 3.12-compatible), `.markdownlint*` config with the prose set now lint-clean, GitHub Actions CI (bootstrap composite action, lint + tests + security + gate jobs). `report.py` renders through Jinja2 with loops in the template instead of `__SLOT__` string replacement. The TC "move to TYPE_CHECKING" trio is off with a written rationale: 3.14 lazy annotations plus pydantic-evals runtime introspection make it a NameError generator. Replay regression preserved through the rename by migrating the recorded run trees (ticket dirs renamed inside each work repo, migration commits kept out of `src/` pathspecs, pre-existing dirty state left dirty): 65/65 with-skill vs 31/65 baseline, byte-identical verdicts.

## 0.3.3 — using-mightymodels fleet reference (2026-08-20)

New skill: `using-mightymodels`, the using-superpowers analog — the primary's in-session reference for the mightymodels (the worker fleet): roster with hard states and refusals, routing rules by need, per-worker dispatch requirements, model resolution order, report vocabulary, anti-patterns. Name is a decision of record: the fleet is the mightymodels, the plugin stays mightymodels. Shipped per the retention rule with a creation smoke eval (fx-sprint routing scenario, 7 checks): with-skill 7/7 vs baseline 4/7 — the baseline misrouted verification to merge-vader and, tellingly, sent a one-line lint fix to a full engineer after guessing budgetron "only scaffolds". Suite replay now 65/65 vs 31/65. Two integrity notes recorded in the skill's RESULTS file: the first baseline self-contaminated by reading the skill from a sibling path (re-run isolated), and the DONE/ASKED check needed case-sensitive contract terms after `(?i)` matched prose "asked". Trigger set with seven near-misses (agents-md-init and jira-sprint collisions included) under `evals/datasets/using-mightymodels/`.

## 0.3.2 — documentation and repository staples (2026-08-20)

Human-facing documentation, written under the humanizer rules: rewritten README plus a `docs/` set (workflow with Mermaid flowchart/sequence/state diagrams, skills roster, agents and model routing, `.mightymodels/` state, Copilot CLI specifics), each page 100-200 lines and split by subject. Staples: CONTRIBUTING.md (the gate, skill authoring, doc voice rules), SECURITY.md (threat model covers skill text, not just code), MIT LICENSE, PR and ticket issue templates matching the loop's own formats. Copilot support made checkable: `scripts/install-copilot.sh` (copy or `--link` into `~/.copilot`, `--uninstall`, touches only names this repo owns; smoke-tested both directions) and `evals/tests/test_plugin.py`, a 24-test portability contract over skill frontmatter, agent files, and manifest agreement. Gate grew: pytest collection pinned to `tests/` (template fixture files were being collected), ruff's own config lints applied (rule names over codes in selectors), 41 tests total. Docs corrections: evals/README trigger-dataset path was stale (`datasets/trigger/` from before the per-skill layout), plugin.json had been left at 0.3.0 by the 0.3.1 bump and is amended in that commit. All four Mermaid diagrams verified with mermaid-cli, not just eyeballed.

## 0.3.1 — harness hardening (2026-08-20)

Strict gate: ruff select-ALL with preview, ignores cut to six documented policy lines, remaining suppressions are per-site noqa with reasons; ty 0.0.73 wired in (error-on-warning, four rules escalated) and clean. Maintainability: evaluators split into a package (files / workdir / response / domain over a typed base), repository operations standardized behind `repo.Repo` (used by fixtures and evaluators; grew `GitCommitsTouchingAtMost`'s data source), fixture file bodies extracted from string constants into `templates/` with base+overlay composition and a `TemplateDriftError` guard, report payload typed with TypedDicts, HTML template extracted to `report_template.html`. Datasets: per-skill `datasets/<skill>/{behavior,trigger}.{yaml,schema.json}` replaces the flat layout; schemas committed. Replay regression: 58/58 with-skill vs 27/58 baseline, unchanged.

## 0.3.0 — plugin restructure + pydantic-evals harness (2026-08-20)

See evals/README.md. Repository becomes a Claude-plugin-compatible layout; ad-hoc eval scripts replaced by the mightymodels-evals package.

## 0.2.0 — the ten loop skills (2026-08-20)


10 new skills (prepare-handoff, what-we-know, agents-assemble, lets-investigate, inline-sendoff, plan-work, finish-assembly, review-circus, whats-broken, prune-ticket) with shared contracts in agents-assemble/references/contracts.md and the ticket/dir schemas in prepare-handoff/references/.

Every skill ships evals/: the smoke scenario + assertions (evals.json), a trigger set with the sprint/jira collision near-misses (trigger-eval.json), and a dated RESULTS-2026-08-20.md — harvested before session end, per the retention rule. Shared fixtures under evals/fixtures/ (rebuild with git state: evals/fixtures-build.sh).

Benchmark (iteration 1, smoke scope, runner claude-opus-5, dispatch simulated): with-skill 37/37 assertions, baseline 15/37, delta +0.59; cost +60s / +11.6k tokens mean per run. Review the per-case evidence in the eval viewer HTML delivered alongside; feedback.json from the viewer drives iteration 2.

Known iteration-2 items: bury fx-debug's cause deeper (cause-finding barely discriminated); add a scope-creep trap to lets-investigate's eval; make fx-finish's REPORT-vs-source trap officially documented expected behavior (it discriminated perfectly by accident); run description optimization + embedcache self-test on your machine.

One design edit made mid-eval, before any run: review-circus gained the dual-provenance routing rule (a finding both reviewers flag routes to the engineer — when the structure judge saw it too, the fix is rarely mechanical). Surfaced by fixture design, not by a failure.

## 0.1.0 — alignment pass (2026-08-20)


Alignment pass bringing the existing skills and agents in line with the v2 methodology, plus the two new items turn-2 skills depend on. Review gate per file below: each entry is what changed, why, and the one thing to check.

**Decisions of record baked in:** reviewer split uncle-bob=claude-opus-5 / merge-vader=gpt-5.6-sol (lands in turn 2's ticket-schema reference) · two-half task briefs (ASKED by primary at dispatch, DONE by engineer) · source-based fix routing (uncle-bob findings→engineer, merge-vader findings→budgetron) with the escalation valve in budgetron's own contract · review-weight cut from ticket.yml · `whats-broken` joins the turn-2 roster.

## Edited

| File | Change | Why | Check |
|---|---|---|---|
| agents/scout.agent.md | Model pin annotated as ticket.yml-overridable default; fail-fast first act (missing question or scope → UNKNOWN-BLOCKED before spending budget) | Routing single-source-of-truth; agents assumed dispatcher packed context with no fail-fast | The fail-fast wording doesn't tempt refusal on merely terse-but-complete tasks |
| agents/engineer.agent.md | Pin annotation; rule 0 fail-fast (plan/owned-set/brief present); verification timeout = `verified="false"`, one retry max; rejected push = report, never force; slop sweep before reporting (deslop folded in: restating comments, defensive checks on trusted paths, type-bypass casts, needless nesting); DONE-half duty when a brief path is named (≤65 lines) | Feeds the two-half brief contract; closes undefined timeout/push outcomes; deslop retired as a standalone skill | Rule numbering starts at 0 — confirm your Copilot parsing has no issue with it; DONE duty is conditional on a brief path, so non-mightymodels dispatches are unaffected |
| agents/gitty-up.agent.md | Pin annotation; `pr="unresolved"` on unresolvable PR; `dev` → "the base branch"; `.agent-lens-phase/` rule removed | Malformed-XML edge; repo-specific leak; agentlens leak into a standalone agent | Nothing else in your harness relied on gitty-up refusing phase files |
| skills/merge-vader/SKILL.md | Report path: `.mightymodels/<task-slug>/review/` when an active ticket exists, repo root + ignore-guard fallback otherwise. Frontmatter description untouched (zero retrieval risk) | Reports live with their ticket; root stays clean | Fallback keeps standalone invocations working outside mightymodels repos |
| skills/merge-vader/references/scout.md | Model pin annotated in the bundled contract copy | Same routing rule | — |
| skills/uncle-bob/SKILL.md + references/report.md | Same report-path rule with repo-root fallback | Same | Codebase-wide runs outside a ticket still write to root |
| skills/promptlint/SKILL.md | §3b fast path: known mightymodels role → instantiate references/templates/, interview only for novel prompts; line-budget knob in Deliver | "promptlint every dispatch" stops costing an interview per dispatch | Fast path is scoped to *active loop* dispatches — everyday promptlint use is unchanged |

## Added

| File | What | Check |
|---|---|---|
| agents/budgetron.agent.md | The budgeted single-concern fixer: ~10-call budget, named-issue-only scope, mandatory Verify on `fixed`, `escalated` on budget/scope excess (the safety valve under source-based routing), house report format with examples | Budget phrasing ("about ten") is advisory-firm, not hook-enforced — iteration 2's hooks can count if you want it hard |
| skills/promptlint/references/templates/{scout,engineer,budgetron,reviewer}.md | Pre-linted parametric dispatch templates; engineer template emits the ASKED stanza used in both brief and dispatch; none restate the agents' standing contracts | Slot lists at the bottom of each — confirm they match what your dispatch flow actually has in hand |

## Renamed

`skills/agent-md-init/` → `skills/agents-md-init/` — directory now matches the frontmatter `name: agents-md-init`. Frontmatter (the embedding key) unchanged, so your retrieval cache is unaffected; update any path-based references on your side.

## Deliberately untouched

`jira` (BUSYSRE/instance split is the overlay iteration), `humanizer` (in the flow via prepare-handoff; overlay decision deferred), `thermo-nuclear-code-quality-review` (needs an evidence model + exit criteria before core; personal lens until then). `export.zip` is excluded from the package — stale duplicate of the tree; its only unique content, `deslop`, is superseded by the engineer's slop sweep above.

## Correction against the earlier triage

The scout-reported claim that uncle-bob's report template lacks the Coverage section was wrong — it's present at the template's end (references/report.md, "Coverage and method"). No edit made; noting it so the finding doesn't resurface.

## Turn 2 preview

Creation order: prepare-handoff → what-we-know → agents-assemble (contracts hub) → lets-investigate → inline-sendoff → plan-work → finish-assembly → review-circus → whats-broken → prune-ticket. Each per its brief in the v2 packet, standard closeout every session (evals + trigger set + dated RESULTS harvested into the skill dir). The sprint/jira embedding collision gets its near-misses written into both sides' trigger evals.
