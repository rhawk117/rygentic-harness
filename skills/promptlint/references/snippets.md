# Proven prompt snippets

Battle-tested language from Anthropic's prompting guidance, adapted for embedding inside generated prompts. Each entry: when to include it, and the snippet. Adapt phrasing to the task — these are ingredients, not boilerplate to paste verbatim. Most prompts need one or two of these at most; adding all of them buries the task.

## Scope guard (anti-overengineering)

Include when: the task is a focused change in an existing codebase — bugfixes, small features — where agents tend to "improve" surrounding code, add speculative flexibility, or annotate untouched code.

```
Only make changes that are directly requested or clearly necessary for the task.
A bug fix doesn't need surrounding code cleaned up; a simple feature doesn't need
extra configurability. Don't add error handling for scenarios that can't happen —
validate at system boundaries only. Don't create helpers or abstractions for
one-time operations. The right amount of complexity is the minimum the current
task needs.
```

## General solution (anti-hardcoding)

Include when: tests exist and could be gamed, or the task will be judged by a test suite. Without this, agents can converge on making the checks green rather than solving the problem.

```
Write a general-purpose solution that works for all valid inputs, not just the
test cases. Tests verify correctness; they do not define the solution. Do not
hard-code values or special-case test inputs. If a test appears incorrect or the
task infeasible as stated, say so in your report instead of working around it.
```

## Investigate before answering (anti-hallucination)

Include when: the agent must reason about existing code — always for bugfixes and refactors. This is the core of the `<discovery>` section.

```
Never speculate about code you have not opened. Read the relevant files before
making claims about them, and verify assumptions against the actual code before
changing anything. If the investigation contradicts anything in this brief,
report the contradiction rather than silently following the brief.
```

## Evidence-based reporting

Include when: the agent reports completion — effectively always. Pairs with the `<verification>` section.

```
In your final report, show evidence rather than asserting success: the exact
commands you ran and their actual output. "Tests pass" is not evidence; the
test runner's output is.
```

## Action default — proactive

Include when: the prompt is for an autonomous run and you want implementation, not suggestions. Agents sometimes respond to "improve X" with a list of suggestions.

```
Implement the changes directly using your editing tools rather than describing
or suggesting them. If details are ambiguous, investigate to resolve them
instead of guessing or stopping to ask.
```

## Action default — conservative

Include when: the task is investigation or planning and edits would be unwelcome (e.g. feeding a planning phase, or a review).

```
Do not modify any files. Your deliverable is the analysis/plan itself: findings
grounded in specific files and line references, and a recommendation. Editing
comes later, in a separate session, after review.
```

## Risky-action gate

Include when: the run is unattended and could touch anything hard to reverse — deletions, force-pushes, migrations, anything visible to other people or shared systems.

```
Local, reversible actions (editing files, running tests) are fine. For anything
hard to reverse or visible beyond this working copy — deleting files or branches,
force-pushing, schema migrations, posting comments, touching shared infra — stop
and ask first. When blocked, don't reach for destructive shortcuts like
--no-verify or discarding unfamiliar files.
```

## Temp-file hygiene

Include when: unattended runs where scratch scripts and debug files would otherwise litter the diff.

```
If you create temporary scripts or scratch files while iterating, remove them
before finishing. The final diff should contain only the change itself.
```

## Long-context ordering

Not a snippet — a structural rule for the generated prompt itself: when the prompt embeds long material (logs, transcripts, pasted docs of roughly 20k+ tokens), place that material at the TOP of the prompt and the instructions/question at the BOTTOM. Queries after the data measurably outperform queries before it. For multiple documents, wrap each in `<document>` tags with a source attribute, and consider asking the agent to quote the relevant parts before acting — it anchors the work in the actual content.

## Self-check

Include when: correctness is checkable by inspection at the end (math, parsing, tricky logic) and no test suite covers it. Skip when the verification gate already catches errors, and skip for frontier models that self-verify by default — redundant checking burns tokens without catching more.

```
Before finishing, re-verify your result against the requirements above and
correct anything that fails.
```

## Session-scale note (very long tasks)

Include when: the task will plausibly exceed one context window (large migrations, repo-wide sweeps). Tell the agent to externalize state so progress survives:

```
This task may span a long session. Keep durable state outside the conversation:
track progress in a progress file, keep the task list in a structured file, and
commit incrementally so completed work is checkpointed. After any context reset,
re-read those files and the git log before continuing.
```
