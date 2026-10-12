# Description tuning run

This records one run of the description tuning for the eight skills in `skills/`, so a later maintainer can see what the descriptions were tested against and decide whether to trust the result or repeat it. The requests are in `trigger-set.yml` in this directory: 48 requests, five for each skill and eight that should load no skill (`skills: []`).

The run was made on 2026-10-11 against the descriptions as they ship in 0.2.0, from a directory outside the repository.

## Judge and options

The judge was `subagent`. The evaluation ran as four packets of 12 requests. Each packet was judged by its own fresh general-purpose subagent on Haiku, which read the judging instructions and its packet and nothing else.

This judge is a proxy for Claude Code's routing, and an optimistic one. The tuning skill's own note says that on one test library it scored vague descriptions about 0.83 where real routing scored 0.50. The scores below are subagent scores, not scores from Claude Code.

The run used `--judge subagent --max-rounds 3 --patience 1`. The other options kept their defaults: validation fraction 0.3, seed 0, packets of 12 requests. The split gave 30 training requests and 18 held out for validation (two per skill and two that should load no skill).

## Result

Baseline and final scores were the same: 1.000 on the training requests and 1.000 on the held-out requests. The run ended after the baseline with "no training failures remain; tuning finished".

No rewrite round ran. No rewrite was kept and none was rejected, and the eight descriptions are the ones committed before the run. `tune apply --dry-run` printed `"written": false, "changes": []`.

Held-out hits, correct requests out of those held out:

| Skill | Hits |
| --- | --- |
| `automate-task` | 2/2 |
| `build-web-service` | 2/2 |
| `data-analysis` | 2/2 |
| `data-engineering` | 2/2 |
| `design-persistence` | 2/2 |
| `design-tests` | 2/2 |
| `enterprise-design` | 2/2 |
| `tactical-slop-review` | 2/2 |
| no skill | 2/2 |

Training hits were 30/30.

`tune lint` over the eight skills printed `[]`, and the run's report lists no remaining collisions above the threshold. It recorded no competing skills, because the subagent judge sees only the tuned skills. Skills from other installed plugins were not in the comparison.

## What this shows

The eight descriptions separate these 48 requests from each other for this judge.

It does not show that Claude Code loads the right skill in a real session. The requests were written for this run, not collected from use. A perfect baseline means the run had nothing to tune, and a skill's name is part of what Claude Code routes on, so the names carry part of the routing.

## Rerun

Run these from a directory outside the repository, with `vibe-code` from the `vibe-code` plugin and the paths adjusted to your checkout:

```text
vibe-code tune lint --skills plugins/python-harness/skills
vibe-code tune init --skills plugins/python-harness/skills --triggers plugins/python-harness/tuning/trigger-set.yml --judge subagent --max-rounds 3 --patience 1
```

`tune init` starts a run; the tuning skill in the `vibe-code` plugin describes how to continue it. `--skills` takes the directory that holds the skills, not one skill's own directory.
