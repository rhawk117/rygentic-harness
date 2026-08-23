# Agents and model routing

Seven workers live in `agents/` as `.agent.md` files. All of them are delegation-only: the
primary dispatches them with a self-contained task, they report in a structured format, and they
hold no memory between dispatches. What keeps the fleet cheap is that each worker refuses the
work of the tier above it.

## scout

The retrieval specialist. It locates files and symbols, finds call sites and references, lists
dependencies and versions, extracts a config value, or runs one command and captures its output.
It reports facts with citations in an XML report and explicitly does not analyze, diagnose, or
recommend; judgment questions route elsewhere. Its verdict vocabulary is `VERIFIED` / `INFERRED`
/ `NEEDS-ANALYSIS` / `UNKNOWN-BLOCKED`, and the hard state names where the missing answer lives
instead of guessing. Tools: read-only plus bash.

Scouts fail fast: a dispatch missing a concrete question or scope comes back `UNKNOWN-BLOCKED`
before any budget is spent. That keeps a sloppy dispatch cheap to discover.

## engineer

The implementer. It executes exactly one task group from a plan it did not write, edits only the
files the group owns, runs each verification in order, and commits its own work. When a brief
path is named in the dispatch, it appends the DONE half of the two-half brief, at most 65 lines.
A verification timeout marks the task `verified="false"` with one retry allowed; a rejected push
is reported, never forced. Before reporting it sweeps its own diff for slop: restated comments,
defensive checks on trusted paths, type-bypass casts, needless nesting.

## budgetron

The budgeted single-concern fixer, and the valve that keeps cheap work cheap. It takes one named
residual issue with a known, bounded fix, a failing lint rule, a missed verification item, a
review finding carrying explicit Fix and Verify lines, works within roughly ten tool calls, and
never expands scope. When the fix turns out larger than named, it reports `escalated` instead of
improvising, and the primary re-dispatches to a full engineer. That escalation path is why
routing merge-vader findings here is safe: misjudged bounds cost one cheap bounce, not a bad
fix.

## gitty-up

The CI watcher. After a PR is opened or updated, it waits for checks to finish and reports
`pass`, `fail` with the relevant logs, or `error` when checks are absent, pending, or
unresolvable. `error` is never treated as pass. It never modifies code; its only tool is command
execution for the GitHub CLI.

## grumpy

The adversarial reasoning reviewer. It attacks the assumptions, evidence, and failure paths in
another agent's plan, diff, analysis, or root-cause claim. It reports only defects, risks, and
open questions; it never validates or fixes the work.

## sunny

The corroborating reasoning reviewer. It independently tests another agent's claims and records
only load-bearing confirmations and unconfirmed areas. It never criticizes, fixes, or grades the
work. In a dialectic, it is normally assigned the stronger model.

## wingman

The no-tools decision advisor. It receives a complete escalation packet and returns a recommendation,
the reasoning behind it, missing information, and questions for the user. Use it through
`ask-an-adult` when a judgment call cannot be settled from available evidence.

## How models are routed

Every agent file carries a `model:` pin, and the pin is only the fallback for headless runs
where nobody answered a routing question. The real source of truth is the active ticket's
`ticket.yml`, whose `subagent-models` block the primary reads at dispatch time:

| Role        | Default            | Why                                                                   |
| ----------- | ------------------ | --------------------------------------------------------------------- |
| scout       | `gpt-5.6-luna`     | Retrieval is cheap-tier work by design                                |
| engineer    | derived from scope | `large` pulls `sonnet-5` or `gpt-5.6-terra`; otherwise `gpt-5.6-luna` |
| budgetron   | `gpt-5.6-luna`     | Bounded fixes do not need a frontier model                            |
| grumpy      | `gpt-5.6-luna`     | Adversarial existence proofs are cheap to obtain                      |
| sunny       | `claude-opus-5`    | Corroboration carries the universal-claim burden                      |
| wingman     | `claude-opus-5`    | Tool-less judgment needs the strongest available reasoner             |
| uncle-bob   | `claude-opus-5`    | Abstraction and structure judgment gets the frontier Claude           |
| merge-vader | `gpt-5.6-sol`      | Cross-vendor diversity on the adversarial pass                        |

The engineer value in the ticket is the default for every task; the primary may bump a single
gnarly task one tier at dispatch, logging the reason in that task's ASKED stanza. The reviewer
split is a decision of record and user-overridable per ticket, like everything else in the
block.

The model ids above are GitHub Copilot CLI ids, since that is the harness this plugin targets
first. Under Claude Code, either edit the pins or let dispatches name models your installation
resolves; [docs/copilot.md](copilot.md) covers where each id is read.

## The two-half brief

The contract that connects primary, engineer, and verifying scout is `briefs/task-NN.md`, capped
at 80 lines. The primary writes the ASKED half at dispatch, roughly 15 lines: objective,
checkable acceptance criteria, verification commands in order, the files the task owns, and the
engineer tier with any bump reason. The engineer appends the DONE half on completion, up to 65
lines. The verifying scout then checks DONE against ASKED criterion by criterion, which means
neither side's claims are taken on faith. The full schema, with the severity table and every
verdict vocabulary, is in `skills/agents-assemble/references/contracts.md`.

## Report formats

Workers report in XML with a shared tag vocabulary (`<report>`, `<findings>`, `<verdict>`,
`<confidence>`, `<follow_up>`), so the primary parses one shape regardless of which worker
answered. Scouts separate `VERIFIED` facts from `INFERRED` ones, and anything inferred names
what it rests on. If you extend the fleet, keep new agents inside this vocabulary; the
coordinator skills parse it.

In a session, the `using-mightymodels` skill is the compact form of this page for the primary
itself: the routing rules, dispatch contents, and refusal boundaries, consultable at dispatch
time without loading the agent files.
