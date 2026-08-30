# Harness mechanics

Load this when you are actually running something.

## Contents

- [Layout](#layout)
- [Eval file format](#eval-file-format)
- [The event log](#the-event-log)
- [Gates](#gates)
- [Cost](#cost)
- [Isolation](#isolation)
- [Still to verify](#still-to-verify)

## Layout

You never construct these paths. `skilleng.workspace.Workspace` owns them, the runner writes
through it and the aggregator reads through it, so the writer and the reader cannot drift
apart. Given here only so you can find things.

```
<workspace>/
  state.json                              phase + gates
  iteration-<N>/
    provenance.json                       model, hashes, host, tier, actual run count
    events.ndjson                         normalised hook events for the whole iteration
    runs/<eval>/<arm>/run-<i>/
      outputs/                            everything the agent produced
      run.json                            the RunRecord
      stdout.log  stderr.log              never discarded
    benchmark.json  benchmark.md  report.html
    feedback.json
```

A layout described in prose and globbed separately in code is a bug category, not a bug. The
predecessor documents `eval-N/with_skill/outputs/` and globs
`eval-*/<config>/run-*/grading.json`; the two never meet, and the result is a benchmark of
zeros that exits 0.

## Eval file format

```json
{
  "schema_version": 1,
  "skill_name": "csv-tidy",
  "cases": [
    {
      "id": "merge-monthly",
      "prompt": "combine the twelve monthly exports in ./data into one csv, dropping the repeated header rows",
      "expected_output": "a single merged csv with one header",
      "files": ["fixtures/data"],
      "assertions": [
        {"id": "single-file", "kind": "mechanical", "text": "produced exactly one csv",
         "check": "test $(ls *.csv | wc -l) -eq 1"},
        {"id": "one-header", "kind": "mechanical", "text": "only one header row survives",
         "check": "test $(grep -c '^date,' *.csv) -eq 1"},
        {"id": "readable", "kind": "judged", "text": "the summary explains what was dropped and why"}
      ]
    }
  ],
  "trigger_queries": [
    {"query": "i've got 12 monthly csv exports in ~/finance/2026 and need them as one file", "should_trigger": true},
    {"query": "write a python function that merges two dicts", "should_trigger": false}
  ]
}
```

One name for one concept: they are `assertions` everywhere, in the eval file, in the run
record and in the report. Loading refuses a duplicate `id` — duplicates silently merge
results and inflate the apparent run count.

## The event log

Both hosts hand a JSON payload to a hook command. `skilleng/hookshim.py` normalises both
spellings into one line-delimited log, and every downstream consumer reads that log:

```json
{"ts":"2026-08-27T21:04:11.220+00:00","event":"pre_tool_use","run_id":"a1b2c3","arm":"available",
 "tool":"Skill","skill":"csv-tidy","session_id":"s-88","unmapped":false,"raw_keys":["..."]}
```

Three properties matter. It is **ground truth** — the host reports the invocation rather than
a parser inferring it. It is **complete** — the whole session, not the first tool block, so a
run that opens with a todo list is not miscounted as a non-trigger. And an uninstrumented run
returns **unknown, not false** — "we did not observe" is a different answer from "it did not
fire", and conflating them is how a broken harness looks like a working one.

Unrecognised payloads are kept with `unmapped: true` and their key list, so a host that
changes its shape shows up as an adapter mismatch instead of a silent zero.

The shim fails open. Instrumentation never breaks the run it observes.

## Gates

`state.json` tracks phase and gates; `skilleng gate --phase X` refuses to advance when a
precondition is unmet.

| Phase | Requires |
|---|---|
| `measure` | `controls` |
| `improve` | `controls`, `review` |
| `package` | `controls`, `review` |

The `review` gate is the human-in-the-loop step. It exists as a gate rather than a strongly
worded instruction because a precondition holds and a paragraph does not.

## Cost

`skilleng run` prints the run count before starting. The arithmetic is unforgiving:
5 evals × 3 arms × 3 runs = 45 agent sessions for one `standard` iteration. At `rigorous`,
120. Say the number out loud before spending it, and prefer raising the number of *evals*
over the number of *runs* — variance between prompts is almost always larger than variance
between repeats of one prompt, so evals buy more resolution per session.

## Isolation

Every run gets a throwaway config directory (`COPILOT_HOME` or `CLAUDE_CONFIG_DIR`) and the
skill is installed there, never into the person's real configuration. Nothing is written to
their project, and `$HOME` is never used as a working directory.

This is not fussiness. A harness that discovers a project root by walking up for a config
directory will land in `$HOME` when run from inside an installed skill, and then spawn
parallel autonomous agents there.

## Still to verify

Honest gaps, all detectable with `skilleng doctor --probe-hooks`:

- Whether Copilot CLI fires hooks under `-p`, and the exact payload key spellings. The
  normaliser accepts several candidate spellings and flags anything it cannot map.
- Hook config precedence under a temporary `COPILOT_HOME`.
- Whether the host reports token counts anywhere the adapter can read. Until one does,
  `tokens` is `null` and the column is omitted — never filled with a character count.
- Copilot hook timeouts fail open even for `preToolUse`, which is fine for instrumentation
  and disqualifying for anything used as a guard.

Run the probe on any host you have not used before. It records raw payloads next to the event
log, so an adapter fix is a small edit to `_EVENT_KEYS` in `skilleng/events.py` rather than an
investigation.
