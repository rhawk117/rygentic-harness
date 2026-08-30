# Target: Claude Code

Claude Code is a fully agentic environment: it reads files, runs commands, edits, and iterates against checks. Prompts for it can delegate whole problems — the leverage is in the verification gate and scope boundary, not in step-by-step direction.

## Shaping the prompt

- **XML sections work natively.** Claude parses XML-tagged structure reliably; the house architecture applies as-is.
- **Delegate the plan, keep the goal.** State goal, constraints, and quality bar; let Claude explore and plan. For multi-file or uncertain work, recommend the user run the prompt in **plan mode** (Shift+Tab) so exploration is separated from execution and the plan gets reviewed before edits. If the prompt itself must enforce this, include: "Present your plan and wait for approval before editing any file."
- **Verification closes the loop.** Claude will iterate until a check passes — so give it the check: exact commands and expected results, and "run these after implementing; fix failures; show the output." For UI work, screenshots-and-compare works: "take a screenshot of the result, compare to the target, list differences, fix them."
- **Reproduce-then-fix for bugs.** "Write a failing test that reproduces the issue, then fix it, then show the test passing" — this turns the bug report into a check and prevents symptom-suppression. Pair with "address the root cause, don't suppress the error."
- **Reference, don't restate.** `@path/to/file` pulls files into context; tell the user to attach error logs by piping (`cat error.log | claude`) or pasting. Point at an exemplar file for conventions ("follow the pattern in HotDogWidget.php") instead of describing style.
- **CLAUDE.md already loads.** Assume repo conventions, build commands, and workflow rules live there. The prompt adds task-specific context only; if a convention matters unusually much for this task, one pointed reminder is enough.

## Capabilities the prompt can invoke

- **Subagents** — "use subagents to investigate X" keeps bulk file-reading out of the main context; "use a subagent to review the diff against the requirements above and report gaps" adds an independent check with fresh eyes. Worth including for large investigations and as a final review step on bigger changes. Temper it: reviewers asked for gaps will find some — scope the review to correctness and stated requirements, not style.
- **Deeper reasoning** — for genuinely hard problems, asking Claude to think through the approach before acting ("think hard about the concurrency implications before choosing a fix") allocates more reasoning. Don't sprinkle it on routine tasks; it adds latency and tokens for nothing.
- **Headless / fan-out** — for batch work, the prompt may be destined for `claude -p "<prompt>"` in a loop. Then it must be fully self-contained (no interactive clarification possible), demand a machine-checkable final line (e.g. "end with OK or FAIL: <reason>"), and assume `--allowedTools` limits what it can do. Keep per-item prompts small; the loop provides the scale.
- **Long sessions** — context is the scarce resource. For big tasks, scope the investigation ("read src/auth/, not the whole repo"), and for very large tasks include the session-scale snippet (progress file + incremental commits) from snippets.md.

## Pitfalls specific to this target

- Claude stops when work *looks* done — a prompt without a runnable check invites a plausible-looking, unverified result.
- Frontier Claude models self-verify and delegate to subagents readily; don't add "double-check everything" or "use subagents for each step" boilerplate — over-prompting thoroughness produces busywork. Add such language only to counter an observed failure.
- Eagerness cuts both ways: if the user only wants analysis, say so explicitly (conservative action default from snippets.md), or Claude may implement.
