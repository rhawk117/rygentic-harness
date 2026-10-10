# Idiom evidence

Read before recording findings, and pass this file's absolute path to every reviewer. A quality finding (structure, naming, abstraction, idiom, duplication) at Medium or above needs structured evidence. Without it the finding is a preference, and preferences are Low at most. The `review` tool's `add` refuses a quality finding at Medium or above whose report block has no typed bullet naming one kind (`Evidence (metric): <cite>`, or `idiom` or `convention` in its place), so the rule holds whether or not a reviewer remembered it. The bullet sits beside the block's `Evidence:` line, and `add` reads the kind and the cite from it.

Defects (wrong behavior, security, data loss, broken compatibility) are not quality findings. Their location and the quoted line are the evidence, and this file does not apply to them. `add` takes a finding as quality when it is uncle-bob's, or merge-vader's in the `quality` dimension; merge-vader's `security`, `sdlc`, `docs` and `plan` findings are defects.

## The three kinds

| Kind         | What the cite names                                                                                                                      | Example cite                                                                       |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `metric`     | A value from `metrics.py` or `mightymodels review-signals` output past its stated threshold, with the file and key it came from.         | `uncle-bob-metrics.json violations.functions_over_20_loc: billing/core.py:busy 38` |
| `idiom`      | Official language, framework, or library documentation for the version the lockfile pins, fetched by web-scout, as `URL#heading`.        | `https://docs.python.org/3.12/library/dataclasses.html#frozen-instances`           |
| `convention` | The repository's own rule: a lint or formatter setting, a documented guideline, or at least two existing sites that do it the other way. | `ruff.toml PLR0913 max-args=3; src/billing/io.py:12, src/billing/store.py:40`      |

A blog post, a style opinion, or "best practice" with no source is not evidence. When the documentation for the pinned version disagrees with the reviewer's habit, the documentation wins.

## Weighing it

- A metric alone makes a finding Medium at most. Add an idiom or convention cite to justify High, since a number says where to look, not that the design is wrong.
- A convention with fewer than two counter-sites is a hint, not evidence.
- A finding that cites evidence the reviewer never retrieved is fabricated. Every cite must appear in the reviewer's scout log or in a measurement file review-circus produced.
