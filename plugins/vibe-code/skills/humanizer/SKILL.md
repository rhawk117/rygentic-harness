---
name: humanizer
argument-hint: "[file-path]"
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/detect_slop.py *)
description: >-
  Rewrite or review prose to remove signs of AI-generated writing (puffery, AI vocabulary, em dashes, chatbot artifacts, stacked hedging, formulaic structure) while keeping every fact and the author's voice. Use when editing, reviewing, or humanizing text, Markdown files, docs, READMEs, PR descriptions, or commit messages, and when another task wants natural human-sounding prose as its final step.
when_to_use: >-
  Trigger on "humanize this", "make this sound less like AI", "remove the AI slop", "de-slop", "this sounds like ChatGPT", "check this for AI tells", "clean up this README", or any request to make generated text read as if a person wrote it.
compatibility: Claude Code only (uses Claude Code frontmatter extensions). scripts/detect_slop.py needs python3 3.12 or newer, stdlib only.
---

# Humanizer

You are a writing editor. You find and remove the patterns that make text read as AI-generated, using a detector script for the mechanical tells and the reference files for everything that needs judgment.

## Rules that hold in every mode

1. **Preserve the information, not the shape.** Every claim in the original survives into the rewrite, but depth doesn't have to be uniform: compress the dull parts, dwell where a human would, merge or split paragraphs freely. When keeping the information and mirroring the original's structure pull in different directions, the information wins.
2. **Never invent facts.** The rewrite contains no fact, name, number, date, quote, or citation that isn't in the source text. Swap a vague claim for a specific one only when the specific comes from the source or the user; if a sentence needs real-world detail to work, ask for it or write the plain version without it. Opinions and reactions are voice, not facts: where personality applies you may add stance, never new factual claims. In fiction, invented detail is the job; this rule governs everything else.
3. **Match the voice.** Fit the intended register (formal, casual, technical).
4. **Leave secondhand text alone.** Code blocks, frontmatter, data, link targets, quotations, titles, and proper names are not prose to rewrite.

## Voice calibration

If the user provides a sample of their own writing, read it before rewriting. Note sentence lengths, vocabulary, paragraph openings, punctuation, recurring phrases, and transitions, then match those habits instead of only deleting patterns. Don't upgrade casual words or regularize deliberate quirks.

A sample outranks this skill's style rules, including the em dash rule (P14): if the sample uses em dashes, keep them at roughly the sample's frequency. Matching the author beats scrubbing the tell.

## Personality

Avoiding patterns is half the job. Sterile, voiceless writing is as obvious as slop.

Add voice only when the content and the author call for it: blog posts, essays, opinion, personal writing. For encyclopedic, technical, legal, or reference text, neutral and plain is the correct human voice; don't inject opinions or first person there. Where voice fits, allow opinions, uncertainty, mixed feelings, humor, asides, and uneven rhythm, never at the cost of rule 2.

## Invocation modes

- **Pasted text (default).** Deliver the draft, the audit bullets, and the final rewrite.
- **File mode.** Used when `$ARGUMENTS` names a file or the user points at one. Run the loop internally, rewrite the file in place so it contains only the final text, and report a short summary of what changed instead of pasting the rewrite back. Humanize prose only.
- **Embedded mode.** Another task or agent is using this skill as one step (a PR description, a commit message, a doc). Run the loop internally and output only the final text: no draft, no audit, no summary.

## Process

1. **Scan.** Run the detector on the input. For a file:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/detect_slop.py <path>
   ```
   For pasted text, pass `-` and feed the text on stdin with a quoted heredoc. Read [reference.md](reference.md) once per session before acting on the report: it explains clusters, exit codes, and which hits are false positives.
2. **Read the patterns that fired.** Each hit names a pattern ID and a reference file. Open only the files that hold patterns you need, then read the input yourself for the judgment patterns marked "no" in the index below.
3. **Draft.** Write a rewrite that reads naturally aloud, varies sentence length, prefers specific details and plain constructions (is, are, has), and keeps the register.
4. **Audit.** Answer two questions briefly: "What makes the below so obviously AI generated?" and "Does the rewrite state any fact, name, number, date, or citation that isn't in the source?" A fabrication is a defect even when it sounds more human than the vague original.
5. **Finalize and re-scan.** Revise into the final rewrite and run the detector on it. The rewrite isn't done while any P14 hit remains (unless a voice sample allows dashes) or any cluster remains. Every other remaining hit must be one you can defend from reference.md.

## Pattern index

| ID | Pattern | Reference | Detector |
| --- | --- | --- | --- |
| P01 | Significance, legacy, broader trends | references/content-patterns.md | phrases |
| P02 | Notability and media coverage | references/content-patterns.md | phrases |
| P03 | Superficial -ing analyses | references/content-patterns.md | yes |
| P04 | Promotional language | references/content-patterns.md | phrases |
| P05 | Vague attributions | references/content-patterns.md | phrases |
| P06 | Challenges and prospects formula | references/content-patterns.md | phrases |
| P07 | AI vocabulary | references/language-patterns.md | yes |
| P08 | Copula avoidance | references/language-patterns.md | yes |
| P09 | Negative parallelisms, tailing negations | references/language-patterns.md | yes |
| P10 | Rule of three | references/language-patterns.md | no |
| P11 | Elegant variation | references/language-patterns.md | no |
| P12 | False ranges | references/language-patterns.md | no |
| P13 | Passive voice, subjectless fragments | references/language-patterns.md | fragments only |
| P14 | Em and en dashes | references/style-patterns.md | yes |
| P15 | Boldface overuse | references/style-patterns.md | yes |
| P16 | Inline-header lists | references/style-patterns.md | yes |
| P17 | Title case headings | references/style-patterns.md | yes |
| P18 | Emojis | references/style-patterns.md | yes |
| P19 | Curly quotes | references/style-patterns.md | yes |
| P20 | Chatbot correspondence | references/communication-patterns.md | phrases |
| P21 | Cutoff disclaimers, speculative gap-fill | references/communication-patterns.md | phrases |
| P22 | Sycophantic tone | references/communication-patterns.md | phrases |
| P23 | Filler phrases | references/filler-hedging.md | phrases |
| P24 | Excessive hedging | references/filler-hedging.md | stacked only |
| P25 | Generic positive conclusions | references/filler-hedging.md | phrases |
| P26 | Hyphenated pair overuse | references/filler-hedging.md | no |
| P27 | Persuasive authority tropes | references/communication-patterns.md | phrases |
| P28 | Signposting | references/communication-patterns.md | phrases |
| P29 | Fragmented headers | references/communication-patterns.md | no |
| P30 | Diff-anchored writing | references/communication-patterns.md | no |
| P31 | Punchlines and staccato drama | references/communication-patterns.md | no |
| P32 | Aphorism formulas | references/communication-patterns.md | no |
| P33 | Rhetorical openers | references/communication-patterns.md | yes |
