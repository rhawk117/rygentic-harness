<!-- Reference: dirty-data ingestion, validation, transformation, and export. Read when the automation request processes CSV, Excel, JSON, or tabular data. -->

# Data processing and data science

## Typical automations

- Detect encoding and delimiter, normalize messy CSV rows, parse dates and currency, and emit validated CSV/JSONL plus a rejects file.
- Read Excel workbooks, select sheets, normalize headers, validate rows, and write clean tabular output.
- Join, deduplicate, aggregate, and filter large CSV, Parquet, or database datasets.
- Convert JSON or newline-delimited JSON into validated records, preserving rejected records with reasons.
- Apply row-level or dataframe-level schemas before loading data into a database or analytical file.
- Produce summary statistics and charts from cleaned data.
- Process data larger than memory with lazy or streaming execution.

## Package menu

| need                            | options (recommended first)                          | choose when                                                                                                                                                                                                                                                     | avoid when                                                                                                                  | latest version                                   | source                                                                                                                                                           |
| ------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tabular cleaning and transforms | **polars 2.0.0 (rec)**; pandas 3.0.6                 | Polars provides a Rust query engine, lazy execution, streaming, and internal parallelism; pandas has a broad, familiar API. \[doc-verified: https://docs.pola.rs/]; \[doc-verified: https://pandas.pydata.org/docs/]                                            | Avoid pandas for data that cannot fit comfortably in memory; avoid Polars when a required pandas-only extension is central. | polars 2.0.0; pandas 3.0.6                       | \[doc-verified: https://pypi.org/pypi/polars/json]; \[doc-verified: https://pypi.org/pypi/pandas/json]                                                           |
| SQL over files and tables       | **duckdb 1.5.6 (rec)**                               | Run SQL over CSV, Parquet, JSON, and database data, especially for joins and aggregations. \[doc-verified: https://duckdb.org/docs/current/]                                                                                                                    | Avoid adding an outer process pool around DuckDB queries; DuckDB parallelizes query execution internally.                   | 1.5.6                                            | \[doc-verified: https://pypi.org/pypi/duckdb/json]                                                                                                               |
| Numeric vectorized work         | **numpy 2.5.3**                                      | Use for dense numeric arrays, linear algebra, broadcasting, and vectorized numerical operations. \[doc-verified: https://numpy.org/doc/stable/]                                                                                                                 | It is overkill for simple parsing, string cleanup, or ordinary dataframe expressions.                                       | 2.5.3                                            | \[doc-verified: https://pypi.org/pypi/numpy/json]                                                                                                                |
| Arrow and Parquet               | **pyarrow 25.0.1**                                   | Use for Arrow interoperability, columnar memory, Parquet read/write, and typed interchange. \[doc-verified: https://arrow.apache.org/docs/python/]                                                                                                              | Avoid introducing it when stdlib CSV/JSON is sufficient and no columnar interchange is needed.                              | 25.0.1                                           | \[doc-verified: https://pypi.org/pypi/pyarrow/json]                                                                                                              |
| Minimal CSV/JSON                | **stdlib csv/json (rec)**                            | Use `csv.DictReader`/`DictWriter` and `json.load`/`dump` for small, dependency-free scripts. \[doc-verified: https://docs.python.org/3/library/csv.html]; \[doc-verified: https://docs.python.org/3/library/json.html]                                          | Avoid for complex joins, large datasets, schema-heavy validation, or Parquet.                                               | Python 3.12+ stdlib                              | \[doc-verified: https://docs.python.org/3/library/csv.html]                                                                                                      |
| Encoding detection              | **charset-normalizer 3.5.2**                         | Detect likely text encodings before decoding unknown input. \[doc-verified: https://charset-normalizer.readthedocs.io/]                                                                                                                                         | Detection is heuristic; do not treat it as proof when provenance or an explicit encoding is available.                      | 3.5.2                                            | \[doc-verified: https://pypi.org/pypi/charset-normalizer/json]                                                                                                   |
| Excel files                     | **openpyxl 3.1.5**; fastexcel 0.21.0                 | Use openpyxl for `.xlsx` workbook access; use fastexcel when its fast Excel-to-Arrow/Polars path fits the input. \[doc-verified: https://openpyxl.readthedocs.io/]; \[doc-verified: https://fastexcel.readthedocs.io/]                                          | Avoid assuming either library handles every legacy `.xls` feature or preserves all workbook presentation details.           | openpyxl 3.1.5; fastexcel 0.21.0                 | \[doc-verified: https://pypi.org/pypi/openpyxl/json]; \[doc-verified: https://pypi.org/pypi/fastexcel/json]                                                      |
| Row validation                  | **pydantic 2.13.5**; pandera 0.34.1                  | Pydantic suits record-shaped Python models; Pandera suits dataframe and column checks. \[doc-verified: https://docs.pydantic.dev/]; \[doc-verified: https://pandera.readthedocs.io/]                                                                            | Avoid using row-only validation as a substitute for cross-row or dataframe-level invariants.                                | pydantic 2.13.5; pandera 0.34.1                  | \[doc-verified: https://pypi.org/pypi/pydantic/json]; \[doc-verified: https://pypi.org/pypi/pandera/json]                                                        |
| Charts                          | **matplotlib 3.11.2**; plotnine 0.15.8; altair 6.3.0 | Use matplotlib for general static plots, plotnine for grammar-of-graphics workflows, and Altair for declarative charts. \[doc-verified: https://matplotlib.org/stable/]; \[doc-verified: https://plotnine.org/]; \[doc-verified: https://altair-viz.github.io/] | Avoid chart generation in a batch path unless the output format, size, and headless backend are specified.                  | matplotlib 3.11.2; plotnine 0.15.8; altair 6.3.0 | \[doc-verified: https://pypi.org/pypi/matplotlib/json]; \[doc-verified: https://pypi.org/pypi/plotnine/json]; \[doc-verified: https://pypi.org/pypi/altair/json] |

## Design choices to put to the user

1. **Input contract:** explicit encoding/delimiter and schema, or detection plus warnings? Recommend explicit values when known; detection is heuristic.
2. **Output format:** CSV, JSONL, Parquet, database table, or multiple outputs? Recommend Parquet for typed analytical data and JSONL for record interchange.
3. **Validation policy:** fail-fast, skip invalid rows, or clean output plus rejects file? Recommend clean output plus rejects with row number, field, value, and reason.
4. **Duplicate policy:** reject, keep first, keep last, or aggregate by key? Recommend an explicit stable key and a documented policy.
5. **Missing-value policy:** preserve nulls, fill defaults, infer values, or reject required fields? Recommend preserve nulls unless a domain default is specified.
6. **Scale:** fits in memory, or use lazy/streaming/chunked processing? Recommend lazy/streaming for uncertain or larger-than-memory inputs. \[doc-verified: https://docs.pola.rs/]
7. **Idempotency:** overwrite, fail if output exists, or atomic replacement? Recommend deterministic output plus atomic replacement and an explicit overwrite flag.
8. **Observability:** counts only, structured logs, or a run manifest? Recommend input/output/reject counts, schema summary, and elapsed time.
9. **Charts:** none, saved PNG/SVG, or interactive HTML? Recommend no chart unless requested; use a headless, deterministic output path.

## Concurrency profile

- Parsing and dataframe transforms are usually CPU- and memory-bound; file and database access may be I/O-bound.
- Prefer library-internal parallelism in Polars and DuckDB; both are designed to use available CPU resources. \[doc-verified: https://docs.pola.rs/]; \[doc-verified: https://duckdb.org/docs/current/]
- Do not wrap one Polars or DuckDB job in an outer `ProcessPoolExecutor` or thread pool unless independent inputs demonstrably improve throughput; nested parallelism can oversubscribe CPUs and memory.
- Use `ThreadPoolExecutor` only for independent blocking I/O with explicit service and file-descriptor limits.
- Use `ProcessPoolExecutor` for independent pure-Python CPU work that cannot use vectorized or library-native execution.
- Treat `InterpreterPoolExecutor` as an advanced Python 3.14+ option requiring a measured benefit and serialization design.
- Pure-Python per-row or per-file CPU work that Polars and DuckDB cannot express (custom parsers, regex-heavy cleanup) belongs in a process pool over independent files; see `concurrency.md` § multiprocessing.
- Cap concurrency by available memory, input-file count, database connections, and remote-service rate limits; start with one worker and benchmark.

## Pitfalls

- **Treating encoding detection as certainty:** accept an explicit encoding when available and log the detector result.
- **Parsing currency by deleting one symbol:** handle locale-specific decimal and thousands separators, then validate ambiguous values.
- **Relying on inferred date formats:** accept configured formats, normalize timezone policy, and reject ambiguous dates.
- **Silently coercing invalid values to null:** retain the original value and write a reason to rejects.
- **Deduplicating without a stable key:** define the key and deterministic winner before deduplication.
- **Loading everything eagerly:** use Polars lazy/streaming, DuckDB SQL, chunks, or Parquet scans for large inputs. \[doc-verified: https://docs.pola.rs/]; \[doc-verified: https://duckdb.org/docs/current/]
- **Assuming CSV is standardized:** configure delimiter, quoting, escaping, newline handling, and header behavior. \[doc-verified: https://docs.python.org/3/library/csv.html]
- **Using NumPy for string-heavy cleanup:** prefer dataframe expressions or ordinary Python parsing when numeric vectorization is not the bottleneck.
- **Validating only after export:** validate before writing the clean output and verify output counts afterward.
- **Creating charts in headless jobs without a backend plan:** specify a non-interactive backend and close figures after saving.

## Skeleton

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from pathlib import Path

CURRENCY_NOISE = r'[$€,\s]'


@dataclass(slots=True, kw_only=True, frozen=True)
class SplitCounts:
    clean: int
    rejected: int


def normalize_amounts(frame: pl.LazyFrame) -> pl.LazyFrame:
    amount = pl.col('amount').str.replace_all(CURRENCY_NOISE, '').cast(pl.Float64, strict=False)
    return frame.with_columns(amount)


def split_rows(source: Path, clean: Path, rejects: Path) -> SplitCounts:
    normalized = normalize_amounts(pl.scan_csv(source)).collect(engine='streaming')
    is_valid = pl.col('id').is_not_null() & pl.col('amount').is_not_null()
    valid = normalized.filter(is_valid)
    invalid = normalized.filter(~is_valid).with_columns(
        pl.lit('missing id or amount').alias('reject_reason')
    )
    valid.write_parquet(clean)
    invalid.write_ndjson(rejects)
    return SplitCounts(clean=valid.height, rejected=invalid.height)
```
