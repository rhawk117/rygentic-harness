# Agents and model routing

Twelve workers live in `plugins/mightymodels/agents/` as plain markdown files, in three folders.
Claude Code makes the folder part of the agent type, so a worker is dispatched as
`mightymodels:<folder>:<name>`, for example `mightymodels:workers:engineer`. Neither the bare
name nor `mightymodels:<name>` is its type.

| Folder | Workers |
| --------- | ------------------------------------------------- |
| `triage` | code-scout, web-scout, wingman, terry-toolchain |
| `workers` | engineer, architect, intern, gitty-up |
| `review` | uncle-bob, merge-vader, qualitylens, fact-checker |

All of them are delegation-only: the primary dispatches them with a self-contained task and they
report in a structured format.
Worker conversational state is never authoritative: a worker may retain task-local context for
bounded follow-ups in the same conversation, but all state required for recovery is
externalized to the ticket directory before the workflow advances, and verification that
requires independence uses a fresh worker context. What keeps the fleet cheap is that each
worker refuses the work of the tier above it.

## triage

### code-scout

The repository retrieval worker. It locates files and symbols, finds call sites and imports,
reads a config value, lists declared and resolved dependency versions, pulls git history for a
path, reads a GitHub issue or pull request through `gh`, or runs one named read-only command and
captures its output. It reports facts with `file:line` citations in an XML report and does not
analyze, diagnose, recommend or edit; judgment questions route elsewhere. Its verdict vocabulary
is `VERIFIED` / `INFERRED` / `NEEDS-ANALYSIS` / `UNKNOWN-BLOCKED`, and the hard state names where
the missing answer lives instead of guessing. Tools: `Read`, `Grep`, `Glob`, `Bash`, with a
ceiling of ten turns.

Scouts fail fast: a dispatch missing a concrete question or scope comes back `UNKNOWN-BLOCKED`
before any budget is spent. That keeps a sloppy dispatch cheap to discover.

### web-scout

The documentation retrieval worker. It fetches one official documentation page, changelog or
release note and cites the URL and section that answers a question about documented behavior,
defaults, deprecations or version differences. It reads only the manifest or lockfile it needs
to pin the version, and it fetches the public web only: a question about a GitHub issue or pull
request goes to code-scout. It shares code-scout's verdict vocabulary. Tools: `Read`, `WebFetch`,
`WebSearch`, with a ceiling of ten turns.

### wingman

The no-tools decision advisor. It receives a complete escalation packet (the decision at stake,
the active ticket's text and every fact gathered so far) and returns a recommendation, the
reasoning behind it, missing information, and questions for the user. Its `tools` list is empty,
so it cannot read the ticket, read a file or run a command: what the packet leaves out it does
not know. Use it through `ask-an-adult` when a judgment call cannot be settled from available
evidence.

### terry-toolchain

The environment surveyor. `game-plan` dispatches it once per run, before the plan is drafted, to
find what the session and the repository will impose on the workers: the harness's tools, the
installed skills, plugins and agents, the repository's own toolchain (git hooks, lint and format
bans, the test, lint and build commands, CI), and the sandbox and permission limits. It returns
one Markdown report of at most 80 lines, each line with an id (`TC-n`), a `[seen]` or
`[declared]` tag and a source, and a `Not seen` section for what it could not read or run.
`game-plan` saves the report as `toolchain.md` in the ticket directory and each brief copies the
lines that bind its task. It writes no file, installs nothing and dispatches nobody. Tools:
`Read`, `Grep`, `Glob`, `Bash`, `Skill`. A `one-shot` ticket gets no survey.

## workers

### engineer

The default implementer. It executes exactly one task group from a plan it did not write, or one
residual fix carrying explicit Fix and Verify lines, edits only the files the dispatch owns,
runs each verification in order, and commits its own work. It never pushes. When a brief path is
named in the dispatch, it appends the DONE half of the two-half brief, at most 65 lines, with
the commit on a `commit: <hash>` line of its own. It reports `done`, `failed`, `blocked` or
`too-large`. A failed verification on a plan task starts the preloaded `agent-debugging`
protocol: it debugs alone, records each fix that failed with the `failed_fix` state tool, and
reports `blocked` when the tool refuses a fourth. A residual gets one attempt. `too-large` names
where to cut the task and commits nothing. It may dispatch code-scout and nobody else.

### architect

The higher-cost recovery implementer. It takes one task after the engineer returned `failed` or
`blocked`, or after a reviewer rejected an implementation with structured evidence. It names the
root cause, makes the design decisions, and implements and verifies inside the task's original
owned files. Its mode is `recovery-implementation` by default, `systemic-refactor` when the user
approved a wider set of files, or `diagnose-replan`, which edits nothing and returns a revised
ASKED. It reports `completed`, `replanned`, `scope-expansion-requested`, `too-large` or
`blocked`. The `task` tool allows it one implementation pass per task, plus one more when a
wider set of files was approved, and it is never used for new work. It may dispatch code-scout
and nobody else.

### intern

The lowest-cost implementer, for a task the plan sizes `tiny`: one owned file, and every
acceptance criterion a command with an expected result. It edits, runs the verification once,
commits, appends a DONE half of at most 30 lines and reports `done`. At the first wall it
reports `blocked` and leaves its edits uncommitted; it takes one attempt and does not debug. A
blocked intern task goes to the engineer with no question to the user. It holds no `Agent` tool.

### gitty-up

The CI watcher. It opens the pull request for a pushed branch, or takes an existing one, waits
for the checks to settle under a time budget (20 minutes by default, 60 at most) and reports
`pass`, `fail` with the relevant log tails, or `error` when checks are absent, pending, or
unresolvable. `error` is never treated as pass. It never modifies code; its only tool is `Bash`,
and all of its work goes through the plugin's `gitty-up` script, which is on the Bash `PATH`.

## review

### uncle-bob

The maintainability reviewer, dispatched by `review-circus`. It grades a branch or a codebase
against SOLID, the Clean Code smells catalog and the Clean Architecture component metrics, and
returns an UNCLE-BOB report with letter grades and `UB-n` findings. Its doctrine is the
preloaded skill `becoming-uncle-bob`. It is read-only and gathers evidence through code-scout
and qualitylens.

### merge-vader

The release-readiness reviewer, dispatched by `review-circus`. It reads the whole diff for
correctness, regressions, compatibility, security and SDLC gates, operational behavior and
documentation drift, and returns a MERGE-VADER report with `MV-n` findings and a `BLOCK`,
`MERGE WITH CONDITIONS` or `CLEAR` verdict. Its doctrine is the preloaded skill
`becoming-merge-vader`. It is read-only and gathers evidence through code-scout, web-scout and
qualitylens.

### qualitylens

The measurement worker. A reviewer or `review-circus` gives it a bounded target and a history
window, and it runs `mightymodels review-signals` for code churn, change coupling and hotspots
and transcribes the numbers into an XML report. It does not judge maintainability or
architecture and does not edit. Tools: `Read`, `Grep`, `Glob`, `Bash`, with a ceiling of ten
turns.

### fact-checker

The task verifier. The primary dispatches it after an engineer, architect or intern reports a
task done and before the task closes. It checks the brief's DONE half against its ASKED half on
the assertion criteria, one criterion at a time (`VERIFIED` with a `file:line`, `REFUTED` or
`UNCHECKED`), and reads the task's commit for defects rated on the severity table. Its verdict
is `CLEAR`, `HOLD` or `UNKNOWN-BLOCKED`. A finding holds the task only when it is Critical or
High and cites both a `file:line` and the criterion or written rule the line breaks; any other
finding is recorded in the brief and goes to `review-circus`. It does not run the contract
commands or the gate, which stay with the primary, and it does not fix, edit or dispatch. Tools:
`Read`, `Grep`, `Glob`, `Bash` and the read-only `snapshot` state tool, with a ceiling of twenty
turns.

## Who may dispatch whom

The main conversation dispatches every worker. A worker dispatches only the workers its agent
file names, and a `PreToolUse` hook on `Agent` denies anything else: the engineer and the
architect may dispatch code-scout, merge-vader may dispatch code-scout, web-scout and
qualitylens, uncle-bob may dispatch code-scout and qualitylens, and the other eight dispatch
nobody. Whoever the caller is, the hook denies a dispatch of the intern unless the task started
for it owns exactly one file, and its denial names the engineer.

While the checked-out branch has one unclosed ticket, the hook also denies the main
conversation's dispatch of the engineer or the architect until a task has been started with the
`task` tool, and answers its dispatch of the architect or the wingman with `ask` when a task is
blocked or failed and the ticket's `auto-escalate` is off. [docs/claude-code.md](claude-code.md)
lists every hook.

## How models are routed

Models are the Claude Code aliases `haiku`, `sonnet`, `opus` and `fable`. Ten workers run on one
fixed model at every scope. The agent file's `model:` pin carries it, the ticket's
`subagent-models` block repeats it, and the `ticket` tool's `validate` refuses a ticket whose
value differs:

| Worker | Model | Why |
| --------------- | -------- | ------------------------------------------------------------- |
| code-scout | `haiku` | Retrieval is cheap-tier work by design |
| web-scout | `haiku` | Fetching and citing one page is retrieval too |
| qualitylens | `haiku` | It transcribes a script's numbers and judges nothing |
| fact-checker | `haiku` | It checks cited lines against written criteria |
| intern | `haiku` | A one-file task with command criteria needs no more |
| gitty-up | `haiku` | Watching CI is polling, the cheapest job in the fleet |
| engineer | `sonnet` | The default implementer, at every scope |
| terry-toolchain | `sonnet` | A survey has to weigh what bears on the ticket |
| architect | `opus` | Recovery sits one tier above the engineer that failed |
| wingman | `fable` | Tool-less judgment needs the strongest available reasoner |
| uncle-bob | by depth | `sonnet` for a quick review, `opus` for standard and deep |
| merge-vader | by depth | `sonnet` for a quick review, `opus` for standard and deep |

The two reviewers take their model from the review run, not from the ticket: `review-circus`
asks for a depth, and one run may spend a single override that moves its heavier-weighted
reviewer to `fable`. The reviewer keys in `ticket.yml` are written for completeness and change
no review.

The primary passes the alias as the `Agent` tool's `model` parameter at dispatch. It may bump
the engineer one tier for a single gnarly task, logging the reason in that task's ASKED stanza.
The table itself is `ROUTING` in `plugins/mightymodels/src/mightymodels_plugin/core/routing.py`.

## The two-half brief

The contract that connects primary, implementer, and fact-checker is `briefs/task-NN.md`, capped
at 80 lines. The primary writes the ASKED half at dispatch, roughly 15 lines: objective,
checkable acceptance criteria, verification commands in order, the files the task owns, and the
engineer tier with any bump reason. The implementer appends the DONE half on completion, up to
65 lines. The fact-checker then checks DONE against ASKED criterion by criterion, which means
neither side's claims are taken on faith. The full schema, with the severity table and every
verdict vocabulary, is in `plugins/mightymodels/skills/agents-assemble/references/contracts.md`.

## Report formats

Workers report in XML with a shared tag vocabulary (`<report>`, `<findings>`, `<verdict>`,
`<confidence>`, `<follow_up>`), so the primary parses one shape regardless of which worker
answered. Scouts separate `VERIFIED` facts from `INFERRED` ones, and anything inferred names
what it rests on. terry-toolchain is the one exception: its report is Markdown, because it is
saved verbatim as `toolchain.md`. If you extend the fleet, keep new agents inside this
vocabulary; the coordinator skills parse it.

In a session, the `prompting-subagents` skill is the compact form of this page for the primary
itself: which worker for which job, the dispatch template for each, and how to read the report
that comes back.
