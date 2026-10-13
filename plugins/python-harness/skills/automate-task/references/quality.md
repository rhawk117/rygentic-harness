<!-- Reference: Python code-quality automation with subprocess-based tool execution, structured aggregation, reporting, and trend storage. Read when the request runs quality tools across one or more Python repositories. -->

# Code quality automation

## Typical automations

- Run Ruff lint checks and formatting checks across one or many repositories. \[doc-verified: https://docs.astral.sh/ruff/]
- Run ty or an alternative type checker and aggregate machine-readable diagnostics. \[doc-verified: https://docs.astral.sh/ty/]
- Collect coverage.py JSON reports and compare coverage metrics between runs. \[doc-verified: https://coverage.readthedocs.io/en/latest/commands/cmd_json.html]
- Measure cyclomatic complexity and maintainability with Radon, or use Ruff's C901 rule. \[doc-verified: https://radon.readthedocs.io/en/latest/commandline.html] \[doc-verified: https://docs.astral.sh/ruff/rules/complex-structure/]
- Detect likely dead code with Vulture and preserve confidence levels for review. \[doc-verified: https://github.com/jendrikseipp/vulture]
- Scan source and dependencies for security issues with Bandit and pip-audit. \[doc-verified: https://bandit.readthedocs.io/en/latest/man/bandit.html] \[doc-verified: https://pypi.org/project/pip-audit/]
- Produce Markdown and JSON summaries, with SQLite history for per-repository trends. \[doc-verified: https://docs.python.org/3/library/sqlite3.html]

## Package menu

| need                      | options (recommended first)                                             | choose when                                                                                                                                                                                                                                                                                                                                       | avoid when                                                                                                                                                                  | latest version                                                             | source                                     |
| ------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------ |
| Linting and formatting    | **Ruff 0.16.10 (rec)**; stdlib `subprocess` only                        | One fast tool should lint and format-check Python. Ruff supports `check`, `format --check`, JSON output for lint diagnostics, configuration in `pyproject.toml`, and caching. \[doc-verified: https://docs.astral.sh/ruff/] \[doc-verified: https://docs.astral.sh/ruff/linter/] \[doc-verified: https://docs.astral.sh/ruff/formatter/]          | The project requires a checker or formatter whose rules are not available in Ruff.                                                                                          | 0.16.10 \[doc-verified: https://pypi.org/pypi/ruff/json]                   | https://docs.astral.sh/ruff/               |
| Type checking             | **ty 0.0.85 (rec)**; mypy; pyright; stdlib `subprocess`                 | Astral tooling is already preferred, or a fast checker with project configuration is wanted. Verify the installed ty CLI and output format with `ty check --help`; CLI details may change. \[doc-verified: https://docs.astral.sh/ty/]                                                                                                            | A project depends on mature checker plugins or an output schema not supported by the selected checker.                                                                      | 0.0.85 \[doc-verified: https://pypi.org/pypi/ty/json]                      | https://docs.astral.sh/ty/                 |
| Coverage                  | **coverage 7.16.2 (rec)**; stdlib `json` for reading an existing report | Tests already produce `.coverage`, and a JSON summary is needed. `coverage json` writes a JSON report. \[doc-verified: https://coverage.readthedocs.io/en/latest/commands/cmd_json.html]                                                                                                                                                          | Tests have not been run, or the desired metric is not represented by the available coverage data.                                                                           | 7.16.2 \[doc-verified: https://pypi.org/pypi/coverage/json]                | https://coverage.readthedocs.io/en/latest/ |
| Complexity                | **Radon 6.0.1 (rec)**; Ruff C901/mccabe; lizard 1.24.1                  | Python cyclomatic-complexity and maintainability-index metrics are required. Radon provides `cc` and `mi`; JSON output is available through its command-line options. \[doc-verified: https://radon.readthedocs.io/en/latest/commandline.html]                                                                                                    | Multiple languages must be measured uniformly; lizard may be a better fit for that case. \[doc-verified: https://pypi.org/project/lizard/]                                  | 6.0.1 \[doc-verified: https://pypi.org/pypi/radon/json]                    | https://radon.readthedocs.io/en/latest/    |
| Dead code                 | **Vulture 2.16 (rec)**; stdlib `subprocess` and `json`                  | Static dead-code candidates and confidence values are useful for review. Vulture accepts files or directories and reports confidence. \[doc-verified: https://github.com/jendrikseipp/vulture]                                                                                                                                                    | Dynamic registration, reflection, or framework conventions make static reachability unreliable without allowlists. \[doc-verified: https://github.com/jendrikseipp/vulture] | 2.16 \[doc-verified: https://pypi.org/pypi/vulture/json]                   | https://github.com/jendrikseipp/vulture    |
| Source security           | **Bandit 1.9.4 (rec)**; stdlib `subprocess` and `json`                  | Python AST security findings and JSON aggregation are needed. Bandit supports JSON output and recursive scanning. \[doc-verified: https://bandit.readthedocs.io/en/latest/man/bandit.html]                                                                                                                                                        | Dependency vulnerabilities are the target; use pip-audit as well. \[doc-verified: https://pypi.org/project/pip-audit/]                                                      | 1.9.4 \[doc-verified: https://pypi.org/pypi/bandit/json]                   | https://bandit.readthedocs.io/             |
| Dependency security       | **pip-audit 2.10.1 (rec)**; stdlib `subprocess` and `json`              | Installed environments or requirements-style files must be checked for known vulnerabilities, with JSON or other machine-readable output. \[doc-verified: https://pypi.org/project/pip-audit/]                                                                                                                                                    | Offline execution or a non-Python dependency inventory is required without a prepared compatible input.                                                                     | 2.10.1 \[doc-verified: https://pypi.org/pypi/pip-audit/json]               | https://pypi.org/project/pip-audit/        |
| Cross-language complexity | lizard 1.24.1; stdlib `subprocess`                                      | Python plus other supported languages must be analyzed with one complexity tool. Lizard supports many languages and reports NLOC, CCN, token count, and parameters. \[doc-verified: https://pypi.org/project/lizard/]                                                                                                                             | Python-only Radon metrics are sufficient.                                                                                                                                   | 1.24.1 \[doc-verified: https://pypi.org/pypi/lizard/json]                  | https://pypi.org/project/lizard/           |
| Aggregation and trends    | **stdlib `subprocess`, `json`, `sqlite3`, `concurrent.futures` (rec)**  | The script should have few dependencies, invoke pinned or environment-provided tools, parse JSON, and persist normalized run facts. \[doc-verified: https://docs.python.org/3/library/subprocess.html] \[doc-verified: https://docs.python.org/3/library/sqlite3.html] \[doc-verified: https://docs.python.org/3/library/concurrent.futures.html] | A vendor API or library API is required and has a stable, documented schema.                                                                                                | Python 3.12+ stdlib \[doc-verified: https://docs.python.org/3.12/library/] | https://docs.python.org/3/library/         |

## Design choices to put to the user

01. **Repository scope:** one path, an explicit list, or recursive discovery. Recommend explicit paths by default because the run set is auditable.
02. **Tool set:** Ruff only; Ruff plus ty; full suite including coverage, complexity, dead-code, and security tools. Recommend selecting tools per repository because optional tools and project readiness differ.
03. **Tool resolution:** commands on `PATH`, `uv run`/`uvx`, or repository-local environments. Recommend repository-local or explicitly pinned execution for reproducibility. \[doc-verified: https://docs.astral.sh/uv/guides/tools/]
04. **Configuration:** honor each repository's configuration, pass explicit overrides, or use a central policy. Recommend honoring repository configuration and recording the effective command.
05. **Failure policy:** fail fast, run all tools and return a nonzero aggregate status, or warnings-only. Recommend run-all with nonzero status when any required check fails, so one failure does not hide other findings.
06. **Output:** Markdown, JSON, both, or machine-readable JSON plus a concise terminal summary. Recommend both, with raw tool payloads retained in normalized result objects.
07. **Trend storage:** no persistence, one SQLite database, or one database per repository. Recommend one SQLite database with repository and revision keys for cross-repository comparison. \[doc-verified: https://docs.python.org/3/library/sqlite3.html]
08. **Concurrency:** sequential, bounded threads, or one subprocess per repository/tool. Recommend bounded `ThreadPoolExecutor` fan-out because child processes perform the work and the parent mainly waits. \[doc-verified: https://docs.python.org/3/library/concurrent.futures.html]
09. **Dry-run semantics:** print commands without executing, or validate paths and configuration only. Recommend print fully quoted commands and planned output paths without changing repositories.
10. **Secrets and network access:** inherit environment, use a named environment-file mechanism, or prohibit networked checks. Recommend inherit only explicitly named variables and never log secret values; pip-audit may access advisory services. \[doc-verified: https://pypi.org/project/pip-audit/]

## Concurrency profile

This domain is **subprocess-bound**: child tools perform CPU work, while the coordinator mostly waits for process completion. Use a bounded `ThreadPoolExecutor` for independent repository/tool invocations; threads are sufficient for waiting on subprocesses. \[doc-verified: https://docs.python.org/3/library/concurrent.futures.html] Do not use `ProcessPoolExecutor` for merely launching external tools, and do not add asyncio unless the surrounding application already uses async I/O. Ruff has internal performance and parallelism behavior, so avoid multiplying concurrency without a measured reason. \[doc-verified: https://docs.astral.sh/ruff/] Cap workers by the number of repositories and a conservative machine-specific limit; lower the cap when tools duplicate large source trees or consume substantial memory. Respect external service and host limits for networked dependency audits.

## Pitfalls

- Treating every nonzero exit code as an infrastructure error; preserve `returncode`, stdout, stderr, timeout, and parsed findings separately.
- Assuming every tool's JSON schema is identical or stable; parse each tool with a version-aware adapter and retain raw output.
- Assuming ty's CLI or output format matches mypy or Ruff; verify `ty check --help` and the installed version before building a parser. \[doc-verified: https://docs.astral.sh/ty/]
- Using Ruff's formatter check as a lint result; report `ruff check` and `ruff format --check` as separate checks. \[doc-verified: https://docs.astral.sh/ruff/linter/] \[doc-verified: https://docs.astral.sh/ruff/formatter/]
- Parsing human-oriented output when a documented machine-readable format exists; request JSON where supported and fail clearly when parsing fails. \[doc-verified: https://bandit.readthedocs.io/en/latest/man/bandit.html]
- Running coverage JSON before tests create coverage data; make test execution an explicit prerequisite or report missing data distinctly. \[doc-verified: https://coverage.readthedocs.io/en/latest/commands/cmd_json.html]
- Treating Vulture findings as proven dead code; review confidence values and account for dynamic imports, plugins, and framework callbacks. \[doc-verified: https://github.com/jendrikseipp/vulture]
- Mixing Radon versions or flags across repositories; record tool versions and command lines with every result. \[doc-verified: https://radon.readthedocs.io/en/latest/commandline.html]
- Logging environment variables or command arguments containing credentials; redact configured secret names before logging.
- Letting one hung child process block the entire run; use per-command timeouts, terminate timed-out children, and classify timeout separately from tool failure. \[doc-verified: https://docs.python.org/3/library/subprocess.html]
- Updating a trend database without a stable repository/revision key; store path, VCS revision when available, timestamp, tool, version, status, and metrics.

## Skeleton

```python
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

CHECK_TIMEOUT_SECONDS = 300


@dataclass(slots=True, kw_only=True, frozen=True)
class CheckJob:
    repo: Path
    argv: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class CheckResult:
    job: CheckJob
    returncode: int
    findings: object


def run_check(job: CheckJob) -> CheckResult:
    completed = subprocess.run(
        job.argv,
        cwd=job.repo,
        check=False,
        text=True,
        capture_output=True,
        timeout=CHECK_TIMEOUT_SECONDS,
    )
    findings = json.loads(completed.stdout) if completed.stdout.strip() else []
    return CheckResult(job=job, returncode=completed.returncode, findings=findings)


def run_checks(jobs: list[CheckJob], *, workers: int) -> list[CheckResult]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_check, jobs))
```
