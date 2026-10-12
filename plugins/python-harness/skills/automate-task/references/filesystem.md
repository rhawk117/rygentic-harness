<!-- Reference: filesystem and file-processing automations with Python. Read when the request walks, copies, archives, watches, hashes, rotates, deletes, or batch-processes files. -->

# Filesystem / File Processing

## Typical automations

- Find files by suffix, glob, age, size, or metadata and emit a report.
- Walk a tree, copy or move selected files, preserving metadata.
- Create or extract ZIP/TAR archives with safe destination handling.
- Compress/decompress streams with gzip, lzma, or Zstandard.
- Watch a directory and trigger processing for filesystem events.
- Hash files, detect duplicates, and verify copies.
- Rotate files by mtime/retention policy, with dry-run and recoverable deletion.
- Batch-convert, resize, or inspect images.

## Package menu

| need                       | options (recommended first)                    | choose when                                                                                                                                                                                 | avoid when                                                                                                  | latest version             | source                                                                      |
| -------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------- | --------------------------------------------------------------------------- |
| Paths, walking, globs      | **rec** `pathlib` (`Path.walk` on 3.12+)       | Zero dependencies; clear path operations. `Path.walk` uses `os.scandir` and does not follow symlinks by default. \[doc-verified: https://docs.python.org/3.14/library/pathlib.html]         | You must support Python \<3.12 or need a specialized watcher.                                               | stdlib (Python 3.12+)      | \[doc-verified: https://docs.python.org/3.14/library/pathlib.html]          |
| Directory enumeration      | **rec** `os.scandir`                           | Need `DirEntry` metadata efficiently or compatibility with older Python. \[doc-verified: https://docs.python.org/3.14/library/os.html#os.scandir]                                           | Simple recursive traversal already handled by `Path.walk`.                                                  | stdlib                     | \[doc-verified: https://docs.python.org/3.14/library/os.html#os.scandir]    |
| Copy/move/archive creation | **rec** `shutil.copy2`, `move`, `make_archive` | Standard copy, metadata preservation, moves, and common archive formats. \[doc-verified: https://docs.python.org/3.14/library/shutil.html]                                                  | You need member-level archive validation or custom compression.                                             | stdlib                     | \[doc-verified: https://docs.python.org/3.14/library/shutil.html]           |
| ZIP/TAR member control     | **rec** `zipfile`, `tarfile`                   | Need explicit member selection, inspection, or safe extraction. TAR uses `data` extraction filtering by default in 3.14. \[doc-verified: https://docs.python.org/3.14/library/tarfile.html] | A one-call directory archive is sufficient.                                                                 | stdlib                     | \[doc-verified: https://docs.python.org/3.14/library/zipfile.html]          |
| gzip/lzma/Zstandard        | **rec** `gzip`, `lzma`, `compression.zstd`     | Stream compression; `compression.zstd` is available in Python 3.14 and TAR/ZIP support follows it. \[doc-verified: https://docs.python.org/3.14/library/compression.zstd.html]              | You target Python 3.13 or earlier without an external Zstandard package.                                    | stdlib; Zstd: Python 3.14+ | \[doc-verified: https://docs.python.org/3.14/library/compression.zstd.html] |
| File hashing               | **rec** `hashlib.file_digest`                  | Verify content or deduplicate; use SHA-256 unless a non-security checksum is explicitly required. \[doc-verified: https://docs.python.org/3.12/library/hashlib.html]                        | You need a manifest format or remote storage integration.                                                   | stdlib (file_digest 3.11+) | \[doc-verified: https://docs.python.org/3.12/library/hashlib.html]          |
| Directory watching         | **rec** `watchdog`                             | Cross-platform event observers and recursive monitoring; latest 6.0.0. \[doc-verified: https://python-watchdog.readthedocs.io/en/stable/quickstart.html]                                    | A periodic scan is simpler, or events must be lossless without a reconciliation scan.                       | 6.0.0                      | \[doc-verified: https://pypi.org/pypi/watchdog/json]                        |
| Image batch work           | **rec** `Pillow`                               | Decode, transform, and save common image formats; latest 12.3.0. \[doc-verified: https://pillow.readthedocs.io/en/stable/handbook/tutorial.html]                                            | You only move/hash files or need a full computer-vision framework.                                          | 12.3.0                     | \[doc-verified: https://pypi.org/pypi/Pillow/json]                          |
| Safe deletion              | **rec** `send2trash`                           | User-recoverable deletion through the OS trash; latest 2.1.0. \[doc-verified: https://pypi.org/project/Send2Trash/]                                                                         | A policy explicitly requires permanent deletion; use `Path.unlink`/`shutil.rmtree` only after confirmation. | 2.1.0                      | \[doc-verified: https://pypi.org/pypi/Send2Trash/json]                      |

## Design choices to put to the user

01. **Scope and symlinks:** `Path.walk` without following links (recommended: avoids cycles and surprises) vs follow links (only with an explicit boundary). \[doc-verified: https://docs.python.org/3.14/library/pathlib.html]
02. **Mutation mode:** dry-run first (recommended: makes destructive impact reviewable) vs apply immediately; require `--yes` for deletion/overwrite.
03. **Idempotency:** skip existing matching outputs (recommended: reruns are safe) vs overwrite, version, or fail.
04. **Safety policy:** send to OS trash (recommended) vs permanent deletion; refuse paths outside an allowed root.
05. **Atomicity:** write to a same-filesystem temporary file then `os.replace` (recommended for generated files) vs direct writes.
06. **Archive policy:** ZIP vs TAR, compression level, symlink treatment, and extraction destination; reject traversal and absolute paths. TAR’s 3.14 default `data` filter is a useful baseline. \[doc-verified: https://docs.python.org/3.14/library/tarfile.html]
07. **Event reliability:** watchdog events plus periodic reconciliation (recommended) vs event-only; choose debounce duration for bursts. \[doc-verified: https://python-watchdog.readthedocs.io/en/stable/quickstart.html]
08. **Failure policy:** fail-fast vs continue and report per-file errors (recommended for batches); choose exit code for partial failure.
09. **Concurrency:** sequential (recommended baseline) vs bounded threads for I/O or processes for CPU-heavy image transforms.
10. **Output:** human-readable logs, JSONL manifest, or CSV; include source, destination, status, bytes, and digest where relevant.

## Concurrency profile

Filesystem traversal, copying, hashing, and archive I/O are usually I/O-bound: prefer sequential code first, then a bounded `ThreadPoolExecutor`; cap workers by storage throughput and open-file limits. Watchdog owns an observer thread; keep handlers quick and enqueue work rather than doing large transforms inline. \[doc-verified: https://python-watchdog.readthedocs.io/en/stable/quickstart.html] Image decoding/transforms are commonly CPU-bound: use `ProcessPoolExecutor`, bounded by CPU cores and memory per image (start method, main guard, and chunksize in `concurrency.md` § multiprocessing). Avoid unbounded queues; preserve per-file error reporting.

## Pitfalls

- Following symlinks can recurse into a parent or duplicate data; do not follow them by default. \[doc-verified: https://docs.python.org/3.14/library/pathlib.html]
- `Path.walk` directory and file lists are not guaranteed sorted; sort when deterministic output matters. \[doc-verified: https://docs.python.org/3.14/library/pathlib.html]
- Copying with `copy` drops metadata that `copy2` attempts to preserve; select deliberately. \[doc-verified: https://docs.python.org/3.14/library/shutil.html]
- Archive extraction can write outside the destination; validate members and retain TAR’s `data` filter. \[doc-verified: https://docs.python.org/3.14/library/tarfile.html]
- ZIP compression support depends on the corresponding codec module; handle `RuntimeError` and `NotImplementedError`. \[doc-verified: https://docs.python.org/3.14/library/zipfile.html]
- A watcher can receive bursts or miss state transitions; debounce and periodically reconcile with a scan.
- Files can change while being copied or hashed; use size/mtime stability checks or producer-specific completion markers.
- Direct writes can leave truncated output after interruption; write beside the destination and call `os.replace`.
- Permanent recursive deletion is irreversible; provide dry-run, root checks, confirmation, and preferably trash.
- Image work can exhaust memory when parallelized; bound processes and close image resources promptly.

## Skeleton

```python
import logging
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True, frozen=True)
class CopyPlan:
    source: Path
    target: Path


def plan_copies(source_root: Path, target_root: Path, suffix: str) -> Iterator[CopyPlan]:
    for directory, _, names in source_root.walk():
        for name in sorted(names):
            source = directory / name
            if source.suffix.lower() == suffix:
                yield CopyPlan(source=source, target=target_root / source.relative_to(source_root))


def apply_copy(plan: CopyPlan, *, dry_run: bool) -> None:
    logger.info('%s %s -> %s', 'would copy' if dry_run else 'copying', plan.source, plan.target)
    if not dry_run:
        plan.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plan.source, plan.target)
```
