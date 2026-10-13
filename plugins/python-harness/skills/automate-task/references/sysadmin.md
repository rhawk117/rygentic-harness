<!-- Reference: local and fleet system-administration automations. Read when the routed request manages processes, services, hosts, disks, certificates, schedules, or notifications. -->

# System administration

## Typical automations

- Run a bounded local subprocess and collect a checked result. \[doc-verified: https://docs.python.org/3.12/library/subprocess.html]
- Inspect processes, CPU, memory, disks, and network state across hosts. \[doc-verified: https://psutil.readthedocs.io/]
- Check or restart a systemd unit and read structured journal entries. \[doc-verified: https://www.freedesktop.org/software/systemd/man/latest/systemctl.html]
- Parse YAML inventory and execute a controlled fleet operation over SSH. \[doc-verified: https://yaml.readthedocs.io/en/latest/]
- Check TLS certificate expiry and notify an operations channel. \[doc-verified: https://docs.python.org/3.12/library/ssl.html]
- Enforce a disk-usage threshold with a dry-run remediation path. \[doc-verified: https://docs.python.org/3.12/library/shutil.html]

## Package menu

| need                                        | options (recommended first, marked **rec**)                                | choose when                                                                                                                                                                                                                                                  | avoid when                                                                                                                            | latest version       | source                                                                                                                                                      |
| ------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| subprocess, paths, locking, TLS, scheduling | **stdlib `subprocess`, `shlex`, `shutil`, `ssl`, `socket`, `fcntl` (rec)** | One host, minimal dependencies, explicit argv and Unix locking. \[doc-verified: https://docs.python.org/3.12/library/subprocess.html]                                                                                                                        | Windows portability for `fcntl`; complex fleet orchestration. \[doc-verified: https://docs.python.org/3.12/library/fcntl.html]        | Python 3.12+         | \[doc-verified: https://docs.python.org/3.12/library/]                                                                                                      |
| host metrics                                | **psutil (rec)**                                                           | Cross-platform process, memory, CPU, disk, and network metrics. \[doc-verified: https://psutil.readthedocs.io/]                                                                                                                                              | A script needing only one stdlib metric.                                                                                              | 7.2.2                | \[doc-verified: https://pypi.org/project/psutil/]                                                                                                           |
| YAML inventory                              | **PyYAML (rec)**; ruamel.yaml                                              | Conventional YAML loading with a small API; use safe loading for untrusted files. \[doc-verified: https://pyyaml.org/wiki/PyYAMLDocumentation]                                                                                                               | Untrusted input with unsafe loaders; round-trip formatting requirements. \[doc-verified: https://pyyaml.org/wiki/PyYAMLDocumentation] | 6.0.3; 0.19.1        | \[doc-verified: https://pypi.org/project/PyYAML/]; \[doc-verified: https://pypi.org/project/ruamel.yaml/]                                                   |
| SSH fleet access                            | **asyncssh (rec)**; Fabric; Paramiko                                       | Many concurrent SSH operations; Fabric for task-oriented imperative SSH; Paramiko for lower-level SSH primitives. \[doc-verified: https://asyncssh.readthedocs.io/]; \[doc-verified: https://docs.fabfile.org/]; \[doc-verified: https://docs.paramiko.org/] | Mixing async and blocking clients without an explicit boundary; secrets in inventory.                                                 | 2.24.1; 3.2.3; 5.0.0 | \[doc-verified: https://pypi.org/project/asyncssh/]; \[doc-verified: https://pypi.org/project/fabric/]; \[doc-verified: https://pypi.org/project/paramiko/] |
| Ansible execution                           | ansible-runner                                                             | Existing Ansible playbooks, inventories, and event streams are the contract. \[doc-verified: https://ansible.readthedocs.io/projects/runner/en/latest/]                                                                                                      | A small one-off command where subprocess/SSH is clearer.                                                                              | 2.4.3                | \[doc-verified: https://pypi.org/project/ansible-runner/]                                                                                                   |
| HTTPS notification                          | **httpx (rec)**; stdlib `urllib.request`                                   | Slack webhook or other HTTPS API; set explicit timeouts and inspect status. \[doc-verified: https://www.python-httpx.org/advanced/timeouts/]                                                                                                                 | No network notification is required.                                                                                                  | 0.28.1               | \[doc-verified: https://pypi.org/project/httpx/]                                                                                                            |

## Design choices to put to the user

1. **Scope:** local host, selected inventory, or all eligible hosts; recommend an explicit allowlist first to limit blast radius.
2. **Execution boundary:** argv list with `shell=False` (recommended), or a reviewed shell command; never interpolate user input into `shell=True`. \[doc-verified: https://docs.python.org/3.12/library/subprocess.html]
3. **Privileges:** unprivileged account (recommended), narrowly scoped `sudo`, or root; require least privilege and make escalation explicit.
4. **Authentication and secrets:** SSH agent/key, environment/secret manager, or webhook URL from environment; never commit or print secrets.
5. **Idempotency:** inspect-before-change and converge to desired state (recommended), force action, or report-only; dry-run must perform no mutation.
6. **Failure policy:** fail-fast, continue and summarize per-host failures (recommended for fleets), or retry with bounded backoff; choose maximum attempts and timeout.
7. **Output:** human summary, JSON records, or both; recommend JSON lines for machine consumers and redacted logs.
8. **Scheduling:** cron for a simple command, or a systemd service/timer for journald, dependencies, and missed-run policy. \[doc-verified: https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html]
9. **Overlap policy:** skip if a lock is held (recommended), wait with a deadline, or allow overlap; use `fcntl.flock` on Unix. \[doc-verified: https://docs.python.org/3.12/library/fcntl.html]

## Concurrency profile

This domain is usually I/O-bound or subprocess-bound, not CPU-bound. Use `asyncio` with AsyncSSH for many SSH targets; use `ThreadPoolExecutor` around blocking psutil/subprocess/SSH APIs; use no parallelism for one local mutation. \[doc-verified: https://docs.python.org/3.12/library/asyncio.html] Cap concurrency by operator-specified host allowlist, SSH server connection limits, API/webhook rate limits, subprocess resource usage, and a per-host semaphore. Prefer bounded concurrency and per-operation timeouts; do not use `ProcessPoolExecutor` or `InterpreterPoolExecutor` unless measured CPU-heavy parsing is the dominant work.

## Pitfalls

- Passing a command string instead of an argv sequence: use a list and `shell=False`. \[doc-verified: https://docs.python.org/3.12/library/subprocess.html]
- Omitting a subprocess timeout: set one and handle `TimeoutExpired`, then terminate or kill deliberately. \[doc-verified: https://docs.python.org/3.12/library/subprocess.html]
- Treating `shlex.split` as sanitization: use it only for tokenization of a reviewed command line, not trust. \[doc-verified: https://docs.python.org/3.12/library/shlex.html]
- Restarting a healthy service on every run: inspect state and make the change conditional.
- Using `df` text parsing when `shutil.disk_usage` supplies structured bytes. \[doc-verified: https://docs.python.org/3.12/library/shutil.html]
- Reading journald as human text: request `journalctl --output=json` and parse records. \[doc-verified: https://www.freedesktop.org/software/systemd/man/latest/journalctl.html]
- Running overlapping cron jobs: acquire a non-blocking `flock` and exit with a distinct code. \[doc-verified: https://docs.python.org/3.12/library/fcntl.html]
- Disabling TLS verification to make certificate checks pass: use a verified `SSLContext` and separately report expiry. \[doc-verified: https://docs.python.org/3.12/library/ssl.html]
- Logging private keys, tokens, inventory credentials, or full webhook URLs: redact at the logging boundary.

## Skeleton

```python
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True, frozen=True)
class DiskPolicy:
    mount: Path = Path('/')
    threshold: float = 0.9
    service: str = 'example.service'
    dry_run: bool = True


def disk_usage_ratio(mount: Path) -> float:
    usage = shutil.disk_usage(mount)
    return usage.used / usage.total


def restart_if_full(policy: DiskPolicy) -> bool:
    if disk_usage_ratio(policy.mount) < policy.threshold:
        return True
    argv = ['systemctl', 'restart', policy.service]
    if policy.dry_run:
        logger.warning('dry-run: would run %s', argv)
        return True
    completed = subprocess.run(argv, check=False, timeout=30, capture_output=True, text=True)
    return completed.returncode == 0
```
