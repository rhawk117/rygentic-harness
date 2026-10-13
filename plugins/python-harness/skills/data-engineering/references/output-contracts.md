# Output contracts: return, publish, log

Read when analysis results must be reused, handed off, or published. `assets/results.py` implements the pattern; copy it into the project and extend it rather than writing another reporting framework.

## Three boundaries

1. Computation returns values: a dataframe, array, fitted estimator, figure or typed record. Terminal text is never the programmatic result.
2. Publication writes artifacts to a fresh run directory, refuses to overwrite one, and writes the manifest last by same-directory rename. A consumer treats a bundle without `manifest.json` as incomplete.
3. Logging records lifecycle events (start, phase timings, completion, failure) to stderr with module loggers, configured once at the CLI boundary. Log identifiers and counts, never raw records or whole tables. Emit completion only after publication succeeds, never from a `finally` block.

## Representations

| output              | format                       | must carry                                                                   |
| ------------------- | ---------------------------- | ---------------------------------------------------------------------------- |
| scalar measurements | typed records, strict JSON   | name, value, unit, n, interval level and method                              |
| tables              | Parquet with explicit dtypes | grain, key, null meaning, units, sort guarantee if any                       |
| arrays              | suitable array format        | shape, dtype, dimension meaning, coordinates                                 |
| figures             | SVG or PNG/PDF               | labels, units, population, window, uncertainty                               |
| interpretation      | Markdown report              | question, method, evidence, implications, limits                             |
| provenance          | JSON                         | input digests or query bounds, parameters, seed policy, environment, status  |
| inventory           | manifest JSON                | relative paths, byte counts, digests, completion status                      |
| trained model       | framework format             | versions, feature schema, preprocessing, evaluation, load-trust requirements |

## Values and units

- Reject nonfinite scalar metrics. msgspec encodes NaN and infinity as `null` without error, so check finiteness before encoding; `results.py` returns the violation and the caller raises.
- An undefined rate (zero denominator) is not zero and not the string "NaN". Omit the scalar and record the reason in the report's issues.
- Missing table values stay as documented nulls.
- Store canonical units (proportion 0.25) and format for humans at render time (25 percentage points). Never mix fractions and percents in one column.
- A p-value is a tail probability under a model; label it so.
- Do not reach for a stringifying default encoder to make serialization pass; it hides contract errors.

## Provenance

Hash the immutable snapshot actually used, at the time it was used; hashing a path later can describe different bytes. For database inputs record the query and extraction bounds. Hashing is identity, not authentication. Record the packages actually used and keep the lockfile.

## CLI shape

`main()` returns an exit code and `__main__` does `raise SystemExit(main())`. Catch only errors the CLI can turn into a meaningful message and status; log once at that boundary. Stdout is reserved for an explicitly requested, versioned machine protocol; otherwise a successful run may print nothing.
