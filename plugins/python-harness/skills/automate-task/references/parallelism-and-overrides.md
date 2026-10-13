<!-- Reference: parallelism levels, hard caps, and how explicit user choices override the analysis. Read when: the request mentions speed, parallelism, workers, threads, processes, asyncio, or a level such as "a lot" or "toaster", or the workload is not trivially sequential. -->

# Parallelism levels and overrides

## Levels

`C` is `os.process_cpu_count()` (honours CPU affinity and `PYTHON_CPU_COUNT`), lowered to the cgroup v2 CPU quota in `/sys/fs/cgroup/cpu.max` when one is set. Run `scripts/parallelism.py` rather than computing these by hand, so every run maps a level to the same numbers on the same host.

| level                           | cpu (pure Python)     | subprocess (ruff, pytest, ffmpeg) | io (HTTP, SSH, sockets)    | library (polars, duckdb, numpy) |
| ------------------------------- | --------------------- | --------------------------------- | -------------------------- | ------------------------------- |
| sequential                      | 1                     | 1                                 | 1                          | library defaults, outer pool 1  |
| moderate (machine stays usable) | max(1, C//2), nice 10 | max(2, C//2), children nice 10    | 8 in flight                | library threads C//2            |
| a lot                           | C−1                   | C                                 | 32 in flight               | library threads C−1             |
| turn my computer into a toaster | C                     | C                                 | min(256, RLIMIT_NOFILE//4) | library threads C               |

Subprocess work stops at C even at toaster, because the child tools do the CPU work and more workers than cores only adds contention.

User phrasings map to levels: "a bit faster", "in parallel", "don't hog my laptop" → moderate; "go a lot parallel", "as fast as reasonable" → a lot; "turn my computer into a toaster", "max it out", "I don't care about my machine" → toaster. "Fast" alone names no level, so ask.

## Hard caps at every level

These protect correctness and other people's systems, so toaster keeps them and removes only the comfort limits (nice, the spare core):

- per-host connection limit (default 6)
- the remote API's documented rate limit and `Retry-After` on 429 and 503
- a timeout on every network call, subprocess, and pool wait
- memory per worker, when it can be estimated (images, dataframes)
- the open-file-descriptor limit (`RLIMIT_NOFILE`)

## When no level is given

Ask through the design form, with the level the analysis recommends preselected. Recommend sequential when the work is small (under about a hundred items, or under a minute sequentially) or is library-parallel, because concurrency then adds failure modes without saving time.

## Choosing the mechanism

| workload                                             | default mechanism                                                                                | notes                                                             |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| io, async-capable client (httpx, asyncssh, aioboto3) | `asyncio.TaskGroup` + `asyncio.Semaphore(n)` + `asyncio.timeout`                                 | one semaphore per host for the per-host cap                       |
| io, sync-only client (boto3, paramiko, requests)     | `ThreadPoolExecutor(max_workers=n)`                                                              | match boto3 `max_pool_connections` to n                           |
| subprocess                                           | `ThreadPoolExecutor` around `subprocess.run(..., timeout=)`, or `asyncio.create_subprocess_exec` | children do the CPU work, so the parent only waits                |
| cpu, GIL build                                       | `ProcessPoolExecutor(max_workers=n)`                                                             | top-level picklable functions, `__main__` guard, batch tiny items |
| cpu, free-threaded build (GIL disabled)              | `ThreadPoolExecutor`                                                                             | only when every C extension in use supports free-threading        |
| cpu, Python 3.14+, isolation wanted                  | `InterpreterPoolExecutor`                                                                        | bump `requires-python` to 3.14, picklable arguments               |
| library                                              | none outside; set `POLARS_MAX_THREADS`, duckdb `SET threads`, or `OMP_NUM_THREADS`               | an outer pool on top oversubscribes                               |

Never nest two parallel layers (outer workers × xdist workers, or a process pool around polars) without multiplying them out against C and saying so in the brief.

## Overrides

1. An explicit technical choice is binding: a named mechanism ("use processes", "use threads", "asyncio", "multiprocessing"), a worker count, or a named package. The brief states it once: "You asked for X; the analysis suggests Y because Z; keeping X." Never swap it silently, and never argue twice.
2. Implement X as well as X allows. For example, processes running subprocess-bound work get a `__main__` guard, top-level picklable worker functions, `max_tasks_per_child` when workers leak, and `forkserver`-safe startup (the POSIX default since 3.14).
3. Vague wishes ("make it fast", "parallel please") are not overrides. The analysis picks the mechanism and the level comes from the form.
4. If X cannot work at all (`InterpreterPoolExecutor` below 3.14, a client that is not thread-safe shared across threads, a lambda that must be pickled), ask with concrete options through `AskUserQuestion` rather than substituting.
5. An explicit count above a hard cap is kept. Pass it as `--requested-workers` to `scripts/parallelism.py`, which keeps it and prints the warning, and repeat the warning in the brief.
6. Every concurrent script exposes `--workers`, defaulting to the mapped value, so the user can retune without regenerating.
