# Authoring

How to write the skill itself. This is the least instrumented phase on purpose — writing is
a writing problem — but two of the checks at the end turn taste into evidence.

## Contents

- [Capturing intent](#capturing-intent)
- [The description](#the-description)
- [Structure and progressive disclosure](#structure-and-progressive-disclosure)
- [Writing style](#writing-style)
- [When to bundle a script](#when-to-bundle-a-script)
- [Improving from feedback](#improving-from-feedback)
- [Two checks that replace taste with evidence](#two-checks-that-replace-taste-with-evidence)

## Capturing intent

Four questions, and the conversation may already answer several:

1. What should this let the agent do that it cannot do well now?
2. When should it fire? What would someone actually type?
3. What does the output look like when it goes right?
4. Is the output objectively checkable? File transforms, data extraction, code generation and
   fixed workflows are. Writing voice, design taste and judgement calls are not — and forcing
   assertions onto them produces a number that measures the wrong thing.

If they said "turn this into a skill", the transcript above is the spec. Extract the tools
used, the sequence, the corrections they made, the formats observed — then confirm the gaps
rather than re-interviewing them on things they already told you.

## The description

The description is the entire trigger surface. Everything about *when* to use the skill goes
here, not in the body; the body is only read after the decision to read it has been made.

Anthropic's guidance and GitHub's agree on the shape: state what it does **and** when to use
it, in the imperative, aimed at the person's intent rather than the implementation. Under
1024 characters, hard.

On pushiness: agents under-trigger skills more often than they over-trigger them, so leaning
towards inclusion is usually right. But this is a real trade, not a free win. A description
that claims a broad territory takes invocations from neighbouring skills, and in isolation
you cannot see it happen. `skilleng trigger --roster` measures that directly; use it before
committing to an aggressive description, and read the cannibalisation line in the output.

Descriptions rot. New skills arrive and compete for the same queries; models change how they
weigh descriptions. A description that measured well six months ago is an untested
description today.

## Structure and progressive disclosure

```
skill-name/
├── SKILL.md          required: frontmatter + instructions
├── references/       markdown loaded on demand
├── scripts/          executable code
├── assets/           templates, schemas, fixtures used in output
└── evals/            the skill's own test suite — ships with it
```

Three loading levels, and each has a real budget:

| Level | Loaded | Budget |
|---|---|---|
| `name` + `description` | always, for every skill installed | ~100 tokens |
| SKILL.md body | when the skill fires | < 500 lines, < 5k tokens |
| Bundled files | when the body points at them | none |

Level 2 is paid on **every** invocation, which is what makes it worth defending. When a skill
grows past its budget, the fix is a router: SKILL.md decides which phase or variant applies
and names exactly one file to read next. Depth of one — a reference that points at another
reference that points at a third burns turns and loses the thread.

Organise references by the axis the reader chooses along. For a multi-cloud deploy skill that
is `references/aws.md`, `gcp.md`, `azure.md`; for a phased workflow it is one file per phase.
Never split a file for tidiness alone; every split is a decision the reader has to make.

`skilleng lint` enforces the budgets, checks every referenced file exists, and flags bundled
files nothing points at.

## Writing style

Imperative, and explain the why. Models have good theory of mind and generalise from a
reason far better than they comply with a rule; a rule covers the case you thought of, a
reason covers the ones you did not.

Capitals are a smell. If you are writing ALWAYS or NEVER, the usual cause is that a
behaviour keeps failing and prose is the only lever you have reached for. It is rarely the
only one available — a gate, a script that refuses to proceed, or a check the agent must run
turns an exhortation into a precondition. The predecessor to this skill ends with an all-caps
paragraph roughly two hundred lines after advising against them, which is not hypocrisy so
much as evidence: the author hit a real behavioural failure and had no mechanism to reach for.

Skip what the model already knows. Do not explain what a PDF is or how HTTP works. The
content worth its context is what it could not have known: your conventions, your formats,
the non-obvious edge case, the API that behaves unlike its documentation.

One default beats three options. "You could use X, Y or Z" spends turns on a comparison the
author should have already made. Name the default, mention the alternative in a clause.

## When to bundle a script

Bundle when the logic is deterministic and gets re-derived every run. Do not bundle
reasoning — a script that encodes a judgement call makes the skill worse and more brittle
at the same time.

The strongest signal is empirical rather than aesthetic: run the evals, then read the
transcripts. If three independent runs each wrote their own `build_chart.py`, that is the
skill telling you what to bundle. `agents/analyst.md` covers doing this systematically, and
`skilleng` records tool sequences in the event log so the comparison is mechanical rather
than a memory exercise.

## Improving from feedback

You will iterate against two or three examples the person knows intimately, because that is
fast. The skill will then be invoked thousands of times on prompts nobody in this
conversation has imagined. Everything about how to use feedback follows from that gap.

Generalise. A complaint about a missing axis label is rarely about axis labels; it is about
charts being readable without the surrounding conversation. Fix the general thing. Fixes that
name the specific example are how a skill ends up working beautifully on exactly three
prompts.

Cut as readily as you add. Improvement has a bias toward accretion, and a skill that only
grows eventually spends its whole budget on instructions that no longer earn it. Read
transcripts, not just outputs: if the skill is sending the model down an unproductive path,
delete the part that does that and measure again.

When something resists three attempts, stop escalating the wording and change the frame.
A different metaphor, a worked example, a different decomposition of the task. Escalation
past the second attempt has poor returns; reframing does better than it has any right to.

## Two checks that replace taste with evidence

**Section ablation.** Delete a section, re-run the evals, see whether anything moves. Sections
that do not move the number are costing context on every invocation for nothing. "Remove what
is not pulling its weight" is good advice that nobody can follow by intuition; this makes it
a measurement. It costs a full eval run per section, so save it for a skill you consider
finished — and expect it to surprise you.

**Repeated-work detection.** Cluster the tool sequences across runs and look for logic the
agent rebuilt from scratch each time. See `agents/analyst.md`.
