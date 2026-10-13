<!-- Reference: CI and release automation scripts for GitHub Actions. Read when the request runs in GitHub Actions or another CI system, checks versions/changelogs, or publishes release metadata. -->

# CI / release automation

## Typical automations

- Compare the checked-out commit, base ref, and tags to decide whether a release is eligible.
- Validate that a changelog entry and project version agree before publishing.
- Read `pyproject.toml`, inspect dependencies, and enforce a supported Python or package version.
- Run `git diff`, `git describe`, or other repository checks in a workflow step.
- Emit GitHub Actions annotations, step outputs, environment variables, and a step summary. \[doc-verified: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands]
- Call GitHub REST or GraphQL endpoints to create/update release or deployment metadata. \[doc-verified: https://cli.github.com/manual/gh_api]
- Produce a deterministic release report locally and in `uv run`-backed CI.

## Package menu

| need                          | options (recommended first)                                 | choose when                                                                                                                                                                                                | avoid when                                                                                                                                      | latest version                                   | source                                               |
| ----------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ---------------------------------------------------- |
| Run `git` and other tools     | **stdlib `subprocess` (rec)**; GitPython                    | Prefer a small, auditable wrapper around the installed CLI; `subprocess` recommends argument sequences and supports captured output. \[doc-verified: https://docs.python.org/3.12/library/subprocess.html] | Avoid shell strings or GitPython when the runner's `git` is unavailable or repository state is not trusted.                                     | stdlib                                           | https://docs.python.org/3.12/library/subprocess.html |
| Parse and compare versions    | **`packaging` (rec)**; hand-written string comparison       | Use `packaging.version.Version` for comparison and validation; it raises `InvalidVersion` for invalid input. \[doc-verified: https://packaging.pypa.io/en/latest/version.html]                             | Avoid lexical comparison for pre-releases, epochs, or post-releases.                                                                            | 26.3                                             | https://pypi.org/project/packaging/                  |
| Read project metadata         | **stdlib `tomllib` (rec)**; `tomlkit`                       | Use `tomllib.load()` for Python 3.12+ read-only TOML; it accepts a binary file and returns a dict. \[doc-verified: https://docs.python.org/3.12/library/tomllib.html]                                      | Avoid it for style-preserving writes; the stdlib module does not write TOML. \[doc-verified: https://docs.python.org/3.12/library/tomllib.html] | stdlib                                           | https://docs.python.org/3.12/library/tomllib.html    |
| Write TOML (only if required) | `tomli-w`; `tomlkit`                                        | Choose `tomli-w` for straightforward writing, or `tomlkit` when preserving existing formatting matters. \[doc-verified: https://docs.python.org/3.12/library/tomllib.html]                                 | Avoid rewriting `pyproject.toml` in a validation-only job.                                                                                      | tomli-w 1.2.0; tomlkit 0.15.1                    | https://pypi.org/project/tomli-w/                    |
| GitHub API calls              | **`gh api` CLI (rec)**; PyGithub; stdlib `urllib.request`   | Choose `gh api` when Actions already supplies `gh` authentication; it performs authenticated REST or GraphQL requests. \[doc-verified: https://cli.github.com/manual/gh_api]                               | Avoid adding an SDK solely for one endpoint, or assuming `gh` exists on non-GitHub runners.                                                     | CLI version is runner-dependent; PyGithub 2.10.0 | https://cli.github.com/manual/gh_api                 |
| Script dependency execution   | **`uv` with PEP 723 metadata (rec)**; workflow-managed venv | Choose `uv run` for a self-contained script with declared dependencies; uv documents on-demand environments and inline metadata. \[doc-verified: https://docs.astral.sh/uv/guides/scripts/]                | Avoid unpinned ad-hoc installs that make CI depend on changing indexes.                                                                         | uv version is workflow-pinned                    | https://docs.astral.sh/uv/guides/scripts/            |

## Design choices to put to the user

1. **Trigger and ref semantics:** pull request base/head, push branch, tag, or manual dispatch. Recommend explicit `GITHUB_SHA` plus event-specific refs because `$GITHUB_SHA` points to an event-dependent commit. \[doc-verified: https://github.com/actions/checkout]
2. **Repository history:** shallow checkout or full history. Recommend `actions/checkout` with `fetch-depth: 0` for tag ancestry and diffs; the action fetches one commit by default. \[doc-verified: https://github.com/actions/checkout]
3. **Authentication:** `gh`/`GITHUB_TOKEN`, an explicitly named secret, or no network. Recommend least-privilege `GITHUB_TOKEN` and no secret in logs.
4. **Mutation policy:** validate-only, propose changes, or publish. Recommend `--dry-run` as the default and require an explicit publish flag.
5. **Idempotency:** fail on an existing release, update it, or treat it as success. Recommend repeat-safe checks before mutation.
6. **Outputs:** annotations, `GITHUB_OUTPUT`, `GITHUB_STEP_SUMMARY`, JSON, or exit status. Recommend human-readable logs plus stable machine outputs. \[doc-verified: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands]
7. **Failure policy:** fail fast, collect all validation errors, or warn and continue. Recommend non-zero exit for release-blocking findings and `::warning` only for advisory findings. \[doc-verified: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands]
8. **Dependency policy:** stdlib-only, pinned PEP 723 dependencies, or project lockfile. Recommend the smallest pinned set and `uv run` with a pinned uv/setup action.

## Concurrency profile

This domain is usually **subprocess-bound and I/O-bound**: git, API calls, filesystem reads, and runner command execution dominate. Use no concurrency for ordered release gates; use `asyncio` or a small `ThreadPoolExecutor` only for independent API or repository checks. Cap concurrency at the provider's documented rate limit, use per-host connection limits, and preserve ordering for mutations. Never parallelize two operations that can publish, tag, or update the same release.

## Pitfalls

- **Assuming a complete repository:** `actions/checkout` fetches one commit by default; set `fetch-depth: 0` when ancestry, tags, or cross-commit diffs are required. \[doc-verified: https://github.com/actions/checkout]
- **Using the wrong commit:** event-specific `GITHUB_SHA`, `GITHUB_BASE_REF`, and `GITHUB_EVENT_PATH` have different roles: `GITHUB_BASE_REF` is set only for `pull_request` and `pull_request_target`, `GITHUB_SHA` depends on the triggering event, and `GITHUB_EVENT_PATH` points at the full webhook payload; read the payload rather than guessing. \[doc-verified: https://docs.github.com/en/actions/reference/workflows-and-actions/variables]
- **Building shell command strings:** pass `subprocess` argument sequences, keep `shell=False`, and check return codes. \[doc-verified: https://docs.python.org/3.12/library/subprocess.html]
- **Comparing versions as strings:** use `packaging.version.Version`, including explicit handling of `InvalidVersion`. \[doc-verified: https://packaging.pypa.io/en/latest/version.html]
- **Treating TOML as writable through `tomllib`:** use a writer only when mutation is required; validation should remain read-only. \[doc-verified: https://docs.python.org/3.12/library/tomllib.html]
- **Leaking secrets:** do not print tokens, URLs containing credentials, or full event payloads; mask sensitive values before annotations or summaries.
- **Forgetting workflow file protocols:** write one line per output to `GITHUB_OUTPUT`, append environment values to `GITHUB_ENV`, and use documented `::error`, `::warning`, and `::group` commands. \[doc-verified: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands]
- **Unexpected network resolution:** declare pinned inline dependencies and pin the uv/setup action; otherwise repeated CI runs can resolve different artifacts.
- **Calling `gh` without runner assumptions:** verify the executable and authentication, or choose an SDK/stdlib HTTP path for other CI systems.

## Skeleton

```python
import os
import subprocess
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from packaging.version import Version

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True, kw_only=True, frozen=True)
class ReleaseContext:
    version: Version
    sha: str


def read_git(*args: str) -> str:
    argv = ['git', *args]
    completed = subprocess.run(argv, check=True, text=True, capture_output=True, timeout=30)
    return completed.stdout.strip()


def load_release_context(pyproject: Path) -> ReleaseContext:
    with pyproject.open('rb') as handle:
        project = tomllib.load(handle)
    sha = os.environ.get('GITHUB_SHA') or read_git('rev-parse', 'HEAD')
    return ReleaseContext(version=Version(project['project']['version']), sha=sha)
```
