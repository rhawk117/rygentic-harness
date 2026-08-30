# Why the checks in step 5 exist

Evidence behind each recommendation, for when the user asks why or pushes back. Sources are listed at the end. Numbers are quoted from the source, not estimated.

## Failure is a process, not an event

In a study of 1,794 CLI coding-agent trajectories across 7 models and 3 scaffolds:

- **57.9%** of decisive errors are epistemic rather than competence failures. The agent did not lack skill; it believed something false.
- **30.7%** of decisive errors are false premises the agent never checked - the single largest trigger.
- Decisive errors land at a **median of 7 execution steps**, the median recovery window is **one step**, and the first observable symptom appears around step 16.
- Repairs aimed at the wrong cause account for **39% of all wasted execution**, with a median of **21 steps remaining** after the misattribution. **82%** of failed recoveries never terminate on their own.

What follows: a turn cap does not save a loop that is confidently fixing the wrong thing, it just decides how much that costs. A progress measure is the only stop that catches it.

## Agents grade their own work generously

- **26% of failed trajectories fabricate success.**
- Anthropic reports the same from production: agents asked to evaluate work they produced "tend to respond by confidently praising the work, even when, to a human observer, the quality is obviously mediocre."

What follows: default-FAIL criteria, evidence read before a criterion flips, and a grader that did not do the work and cannot write.

## Watchdogs do not work yet

Automated monitors watching a trajectory reach **28.8% recall at best**, and their **median lead time relative to lock-in is zero** - they fire at or after the point of no return.

What follows: put the gate at the turn boundary, not in a supervisor agent. Spend the budget on the check, not the watcher.

## Compaction deletes standing rules

Across 1,323 episodes on 7 models:

- Policy violation is **0% while the rule is in full context** and **30% pooled after a single compaction**, reaching **59%** on some models.
- Decay is **8.3x larger for soft organizational policies** than for hard safety norms - exactly the project-specific rules that have no model prior to fall back on.
- In the worst case, stating a policy and then compacting was **worse than never stating it at all** (59% versus a 37% no-policy baseline).
- Violation tracks the **summarizer**, not the agent, and the summarizer is separately attackable.
- Pinning the constraint outside the lossy path restored **0% violation at roughly 47 tokens**, under 0.5% overhead.

What follows: rules that must hold for a whole run belong in a re-read contract file, a re-injected instruction file, or a hook. Not in the opening prompt.

## Long horizons degrade non-linearly

A synthesis of 27 papers across 19 benchmarks reports success falling from **40-50% on short horizons to under 10% on long ones**, with roughly **3-5% efficiency loss per 50% increase in conversation length**, as agents re-read processed files and repeat failed calls. Treat as directional; the numbers are inherited from the underlying benchmarks.

What follows: small units of work, and a fresh context between them, beat one heroic session.

## Parallel workers collide on shared state

From a production run of 64 concurrent agents producing 6,502 commits in 11 days: "One agent ran `git stash` before committing. Another ran `git stash pop`. And then `git reset HEAD --hard`." The fix was constraining the tool surface, not writing a more polite prompt. GitHub documents the same hazard for `/fleet`: subagents share a filesystem with no locking, and the last writer wins silently.

What follows: partition by file or module, and restrict tools rather than trusting instructions.

## Splitting agents pays for independence, not throughput

The reported wins from multi-agent setups come from adversarial review with a deliberately narrow context - one implementer to two or more reviewers who see only the diff and are told to assume it is wrong - not from dividing labour. A measured comparison of a full planner/generator/evaluator harness against a solo run showed **6 hours and $200 versus 20 minutes and $9**, a 20x cost delta for a quality difference described as immediately apparent. Worth it sometimes. Never free.

Countervailing: reviewers prompted to find gaps will find some even when the work is sound, and chasing every finding produces over-engineering. Triage findings before acting on them.

## Instructions are a weak enforcement layer

Anthropic on its own prompts: "we were overconstraining Claude Code, both through our system prompt and in our CLAUDE.md files and skills", producing direct conflicts between rules. Also: "If you emphasize many lines, none of them stands out", and "When there's something that absolutely must not happen, an instruction is the wrong tool."

Long prescriptive checklists also measurably suppress discovery: "more prescriptive prompts make discovery worse - long checklists tend to reduce the model's creativity and generate fewer novel bugs."

What follows: prefer a hook or a withheld tool over a rule, and keep the contract short.

## Sources

- Zhao, Li, Li, Zhao, Barr, Sarro, Ye. *Failure as a Process: An Anatomy of CLI Coding Agent Trajectories.* arXiv:2607.09510, 2026-07-10. https://arxiv.org/html/2607.09510
- Chen. *Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents.* arXiv:2606.22528v2, 2026-06-27. https://arxiv.org/html/2606.22528v2
- Albayaydh, Zhao, Flechais. *Beyond the Leaderboard.* arXiv:2607.05775, 2026-07. https://arxiv.org/html/2607.05775v1
- Anthropic. *Loop engineering: Getting started with loops*, 2026-06-30. https://claude.com/blog/getting-started-with-loops
- Anthropic. *A harness for every task*, 2026-06-02. https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code
- Anthropic. *The new rules of context engineering*, 2026-07-24. https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models
- Anthropic. *Best practices for Claude Code.* https://code.claude.com/docs/en/best-practices
- Anthropic. *Keep Claude working toward a goal.* https://code.claude.com/docs/en/goal
- Rajasekaran. *Harness design for long-running application development*, 2026-03-24. https://www.anthropic.com/engineering/harness-design-long-running-apps
- Yan, Dattani. *Using LLMs to secure source code*, 2026-05-22. https://github.com/anthropics/defending-code-reference-harness/blob/main/docs/blog-post.md
- Sumner. *Bun in Rust*, 2026-07. https://bun.com/blog/bun-in-rust
- GitHub. *Copilot CLI hooks reference.* https://docs.github.com/en/copilot/reference/hooks-reference
- GitHub. *Running tasks in parallel with /fleet.* https://docs.github.com/en/copilot/concepts/agents/copilot-cli/fleet
