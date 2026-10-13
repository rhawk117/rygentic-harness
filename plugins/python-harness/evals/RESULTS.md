# Smoke eval results

This records one run of the six cases, made on 2026-10-11 with Claude Code 2.1.296 against the
plugin at 0.2.0. Each case ran once with the plugin loaded and no baseline arm
(`--runs 1 --ablation none`), on a Claude plan login. Medium effort was requested through
`CLAUDE_CODE_EFFORT_LEVEL=medium`. Nothing in the results or the session traces states the effort a
session used, so the effort is not confirmed.

## Scores

A score of 1 on a `-loads` case means the session called the Skill tool for that skill. A score of
1 on a `-stays-out` case means it did not.

| Case | Haiku 5.5 | Sonnet 5.5 |
| --- | --- | --- |
| `automate-task-loads` | 0 (two runs) | 1 |
| `data-analysis-loads` | 0 | 1 |
| `data-engineering-loads` | 0 | 0 |
| `automate-task-stays-out` | 1 | not run |
| `data-analysis-stays-out` | 1 | not run |
| `data-engineering-stays-out` | 1 | not run |

## What the sessions did

On Haiku, no session called the Skill tool in any case, so its three `-stays-out` scores carry no
information. In each `-loads` case Haiku started on the work itself: it read the files and then
either answered or tried to write a file, which the cases do not allow. In a separate session with
the same setup, asked to read `pyproject.toml` and name the skills it could see, Haiku listed all
eight. The skills were visible to it and it did not load them.

On Sonnet, the Skill call was the first tool call in `automate-task-loads` and
`data-analysis-loads`. In `data-engineering-loads` Sonnet read `load.py` and the two CSV files,
found the duplicated `account_id` in the four-line `accounts.csv`, and reported the cause without
loading the skill.

## What this shows

On Sonnet, a matching request loaded `automate-task` and `data-analysis`. On Haiku, a matching
request loaded nothing.

`data-engineering-loads` loaded its skill on neither model. Its fixture is small enough that the
cause is visible by reading the files. Whether a larger fixture or different wording changes the
result was not tested.

The run does not show more than that. Each case ran once, apart from the one Haiku case that ran
twice. The `-stays-out` cases were not run on Sonnet, and the other five skills have no case. The
cases allow only read-only tools, so they do not show what a skill does after it loads.

The description tuning run in `tuning/REPORT.md` scored the same skill text 1.000 with its proxy
judge. The table above is what real sessions did with six of those kinds of request.
