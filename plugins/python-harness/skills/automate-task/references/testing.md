<!-- Reference: Python test-run orchestration with pytest, reporting, retries, matrices, coverage, property and load checks. Read when the request automates test execution or summarizes test results. Researched 2026-10-06. -->

# Testing automation

## Typical automations

- Run a pytest suite in a subprocess with a controlled environment and explicit exit code.
- Invoke pytest repeatedly to detect order-dependent or flaky failures.
- Emit `--junitxml` and summarize pass/fail/error/skip counts from XML.
- Parallelize tests with pytest-xdist, while avoiding outer-worker × xdist oversubscription.
- Run a Python-version matrix with nox, tox/tox-uv, or explicit `uv run --python X`.
- Combine per-process coverage data and produce a report.
- Run Hypothesis property checks or a short Locust load smoke test.

## Package menu

| need             | options (recommended first, marked **rec**)                           | choose when                                                                                                                                                                                                                                                                                                                          | avoid when                                                                                                                                                                                                           | latest version                                                                                                                                                                              | source                                                 |
| ---------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Test runner      | **rec** `pytest`                                                      | Need fixtures, discovery, parametrization, and rich CLI behavior. \[doc-verified: https://docs.pytest.org/en/stable/]                                                                                                                                                                                                                | A project has no pytest tests; use its native runner.                                                                                                                                                                | 9.1.1 \[doc-verified: https://pypi.org/pypi/pytest/json]                                                                                                                                    | https://docs.pytest.org/en/stable/                     |
| Process control  | **rec** stdlib `subprocess`; `pytest.main()`                          | Need isolation, streamed output, and a reliable child exit status; use `pytest.main()` only for in-process embedding. \[doc-verified: https://docs.python.org/3/library/subprocess.html] \[doc-verified: https://docs.pytest.org/en/stable/how-to/usage.html#calling-pytest-from-python-code]                                        | Do not use `pytest.main()` for repeated runs in one interpreter: imported state and pytest plugins can persist. \[doc-verified: https://docs.pytest.org/en/stable/how-to/usage.html#calling-pytest-from-python-code] | stdlib; pytest 9.1.1 \[doc-verified: https://pypi.org/pypi/pytest/json]                                                                                                                     | https://docs.python.org/3/library/subprocess.html      |
| JUnit XML        | **rec** stdlib `xml.etree.ElementTree`; `junitparser`                 | Use stdlib for a small, known XML shape; use junitparser for convenient suite/case manipulation. \[doc-verified: https://docs.python.org/3/library/xml.etree.elementtree.html] \[doc-verified: https://junitparser.readthedocs.io/en/latest/]                                                                                        | Avoid assuming one producer's exact schema; JUnit XML is a family of dialects.                                                                                                                                       | stdlib; junitparser 5.0.3 \[doc-verified: https://pypi.org/pypi/junitparser/json]                                                                                                           | https://junitparser.readthedocs.io/en/latest/          |
| Test parallelism | **rec** `pytest-xdist`; pytest serial                                 | Use `-n auto` or a bounded integer when tests are independent and the host has capacity. \[doc-verified: https://pytest-xdist.readthedocs.io/en/stable/]                                                                                                                                                                             | Avoid xdist for tests sharing files, ports, global state, or order; do not multiply outer workers by xdist workers. \[doc-verified: https://pytest-xdist.readthedocs.io/en/stable/distribution.html]                 | 3.8.0 \[doc-verified: https://pypi.org/pypi/pytest-xdist/json]                                                                                                                              | https://pytest-xdist.readthedocs.io/en/stable/         |
| Retry policy     | **rec** `pytest-rerunfailures`; explicit repeated subprocesses        | Use plugin retries for transient test failures; use repeated subprocesses to measure flake rate. \[doc-verified: https://pytest-rerunfailures.readthedocs.io/en/stable/]                                                                                                                                                             | Avoid retries when a failure is deterministic or when retries would hide regressions; report attempts separately.                                                                                                    | 16.7 \[doc-verified: https://pypi.org/pypi/pytest-rerunfailures/json]                                                                                                                       | https://pytest-rerunfailures.readthedocs.io/en/stable/ |
| Python matrix    | **rec** `nox` with uv; `tox` with `tox-uv`; plain `uv run --python X` | Use nox for Python-defined sessions, tox for existing tox ecosystems, and uv commands for a small explicit matrix. \[doc-verified: https://nox.thea.guide/] \[doc-verified: https://tox.wiki/en/latest/] \[doc-verified: https://tox-uv.readthedocs.io/en/latest/] \[doc-verified: https://docs.astral.sh/uv/concepts/projects/run/] | Avoid adding an orchestrator for one interpreter and one command.                                                                                                                                                    | nox 2026.8.17; tox 4.64.9; tox-uv 1.36.1 \[doc-verified: https://pypi.org/pypi/nox/json] \[doc-verified: https://pypi.org/pypi/tox/json] \[doc-verified: https://pypi.org/pypi/tox-uv/json] | https://nox.thea.guide/                                |
| Coverage         | **rec** `coverage.py`; `coverage combine` for parallel data           | Use parallel data files when processes run concurrently, then combine before reporting. \[doc-verified: https://coverage.readthedocs.io/en/latest/commands/cmd_combine.html]                                                                                                                                                         | Do not compare an uncombined partial report with a full run.                                                                                                                                                         | 7.16.2 \[doc-verified: https://pypi.org/pypi/coverage/json]                                                                                                                                 | https://coverage.readthedocs.io/en/latest/             |
| Property checks  | **rec** `hypothesis`                                                  | Use generated examples and shrinking for invariants and edge cases. \[doc-verified: https://hypothesis.readthedocs.io/en/latest/]                                                                                                                                                                                                    | Avoid unbounded profiles in CI; set an explicit deadline/example budget when runtime matters. \[doc-verified: https://hypothesis.readthedocs.io/en/latest/reference/api.html]                                        | 6.168.5 \[doc-verified: https://pypi.org/pypi/hypothesis/json]                                                                                                                              | https://hypothesis.readthedocs.io/en/latest/           |
| Load smoke tests | **rec** `locust`; stdlib/http client for one request                  | Use Locust when user behavior, concurrency, and request statistics matter. \[doc-verified: https://docs.locust.io/en/stable/]                                                                                                                                                                                                        | Avoid treating a short load smoke test as capacity certification.                                                                                                                                                    | 2.46.7 \[doc-verified: https://pypi.org/pypi/locust/json]                                                                                                                                   | https://docs.locust.io/en/stable/                      |

## Design choices to put to the user

01. **Isolation:** subprocess per run (recommended; clean imports and exit status) or `pytest.main()` (in-process embedding). \[doc-verified: https://docs.pytest.org/en/stable/how-to/usage.html#calling-pytest-from-python-code]
02. **Selection:** explicit paths/markers (recommended; reproducible) or repository discovery. \[doc-verified: https://docs.pytest.org/en/stable/how-to/usage.html]
03. **Parallelism:** serial (recommended default), xdist, or outer fan-out; never enable both without a worker budget. \[doc-verified: https://pytest-xdist.readthedocs.io/en/stable/distribution.html]
04. **Failure policy:** fail fast, collect all failures (recommended for CI summaries), or retry then fail; preserve original and retry outcomes. \[doc-verified: https://docs.pytest.org/en/stable/how-to/failures.html]
05. **Flake policy:** one run, N repeated subprocess runs, or plugin retries; recommend repeated subprocesses for a flake signal because process state is reset.
06. **Report:** console only, JUnit XML (recommended for CI ingestion), JSON/custom summary, or both. \[doc-verified: https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files]
07. **Matrix:** Python versions and environment variables; recommend explicit versions with nox/uv for small matrices. \[doc-verified: https://nox.thea.guide/]
08. **Coverage:** disabled, per-run, or parallel combine; recommend combine whenever runs are parallel or matrixed. \[doc-verified: https://coverage.readthedocs.io/en/latest/commands/cmd_combine.html]
09. **Secrets and targets:** environment/secret manager source, base URL, and whether load tests may run; recommend no secrets in argv or reports.
10. **Dry run and exit contract:** print planned commands without execution (recommended) and return distinct usage, test-failure, and orchestration-error codes. \[doc-verified: https://docs.python.org/3/library/argparse.html]

## Concurrency profile

- Test orchestration is usually **subprocess-bound**; pytest itself may be CPU- or I/O-mixed.
- Prefer one bounded outer scheduler **or** pytest-xdist; if both are required, cap `outer workers × xdist workers` to available CPU, memory, file descriptors, and service capacity. \[doc-verified: https://pytest-xdist.readthedocs.io/en/stable/distribution.html]
- `ThreadPoolExecutor` fits independent subprocess launches or I/O summaries; `ProcessPoolExecutor` is rarely needed because pytest/xdist already creates processes. \[doc-verified: https://docs.python.org/3/library/concurrent.futures.html]
- Load tests need explicit request rate, user count, duration, host connection limits, and a target-approved cap. \[doc-verified: https://docs.locust.io/en/stable/configuration.html]

## Pitfalls

- Calling `pytest.main()` repeatedly in one process leaks imported/plugin state; use a subprocess per attempt. \[doc-verified: https://docs.pytest.org/en/stable/how-to/usage.html#calling-pytest-from-python-code]
- Treating every nonzero pytest code as the same hides usage errors, no-tests-collected, and test failures; map documented exit codes separately. \[doc-verified: https://docs.pytest.org/en/stable/reference/exit-codes.html]
- Parsing only `<testsuite tests="...">` misses nested suites or producer differences; recursively inspect XML and tolerate absent attributes.
- Using one JUnit filename for concurrent runs causes clobbering; give each process a unique path, then aggregate.
- Running outer fan-out with `-n auto` oversubscribes CPU and memory; choose one parallel layer or calculate the product.
- Retries can turn a flaky test green; report retry count and original failure, not only final status. \[doc-verified: https://pytest-rerunfailures.readthedocs.io/en/stable/]
- Combining coverage without `parallel=True` or distinct data files can overwrite measurements; configure parallel data before fan-out. \[doc-verified: https://coverage.readthedocs.io/en/latest/commands/cmd_combine.html]
- Matrix jobs may use different dependency resolutions; log Python, uv, pytest, and project versions.
- Hypothesis deadlines and example counts can make CI nondeterministic in slow environments; choose and document a profile. \[doc-verified: https://hypothesis.readthedocs.io/en/latest/reference/api.html]
- A Locust smoke test is not a load-capacity claim; define pass thresholds and duration with the service owner.

## Skeleton

```python
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True, kw_only=True, frozen=True)
class RunSummary:
    returncode: int
    tests: int
    failures: int


def count_attribute(root: ET.Element, name: str) -> int:
    return sum(int(suite.get(name, 0)) for suite in root.iter('testsuite'))


def run_pytest_once(target: str, report: Path, *, timeout_seconds: float) -> RunSummary:
    argv = ['pytest', target, f'--junitxml={report}']
    completed = subprocess.run(
        argv, check=False, text=True, capture_output=True, timeout=timeout_seconds
    )
    root = ET.parse(report).getroot()
    return RunSummary(
        returncode=completed.returncode,
        tests=count_attribute(root, 'tests'),
        failures=count_attribute(root, 'failures') + count_attribute(root, 'errors'),
    )
```
