<!-- Reference: HTTP APIs, scraping, downloads, retries, and bounded concurrency. Read when the automation performs network I/O or web scraping. -->

# Network / HTTP APIs / scraping

## Typical automations

- Call a JSON/REST API with pagination, authentication, retries, and structured output.
- Download a large artifact with streaming, checksum validation, and resume support.
- Scrape static HTML while honoring `robots.txt`, rate limits, and `Retry-After`.
- Fetch JavaScript-rendered pages with a browser only when plain HTTP is insufficient.
- Probe TCP reachability for a host/port.
- Run bounded requests across many URLs or API resources.

## Package menu

| need                 | options (recommended first)                                               | choose when                                                                                                                                                    | avoid when                                                      | latest version                          | source                                                                                                                                                                                                             |
| -------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Sync/async HTTP      | **httpx 0.28.1 (rec)**; requests 2.34.2; aiohttp 3.14.4; `urllib.request` | httpx for one API surface in sync or async code; requests for mature sync-only integrations; aiohttp for an asyncio-heavy client; stdlib for zero dependencies | Do not mix clients without a reason; urllib needs more plumbing | versions checked at PyPI JSON endpoints | \[doc-verified: https://www.python-httpx.org/] \[doc-verified: https://requests.readthedocs.io/] \[doc-verified: https://docs.aiohttp.org/] \[doc-verified: https://docs.python.org/3/library/urllib.request.html] |
| Retries              | **tenacity 9.1.4 (rec)**; stamina 26.1.0; httpx transport retries         | tenacity for explicit exception/status policies; stamina for decorator-based retries; HTTPX transport retries only for connect failures                        | Never blindly retry non-idempotent operations or every 4xx      | versions checked at PyPI JSON endpoints | \[doc-verified: https://tenacity.readthedocs.io/] \[doc-verified: https://stamina.hypermodern.io/] \[doc-verified: https://www.python-httpx.org/advanced/transports/]                                              |
| Async rate limiting  | **aiolimiter 1.3.0 (rec)**; `asyncio.Semaphore`; server-provided delays   | aiolimiter for a rate-per-time-window; Semaphore for in-flight caps; combine both when required                                                                | A semaphore alone does not enforce requests/second              | version checked at PyPI JSON endpoint   | \[doc-verified: https://aiolimiter.readthedocs.io/] \[doc-verified: https://docs.python.org/3/library/asyncio-sync.html]                                                                                           |
| Static HTML parsing  | **selectolax 1.0.0 (rec)**; beautifulsoup4 4.15.0 + lxml 6.1.3            | selectolax for fast CSS-selector parsing; Beautiful Soup when parser flexibility/ecosystem matters                                                             | Neither executes page JavaScript                                | versions checked at PyPI JSON endpoints | \[doc-verified: https://selectolax.readthedocs.io/] \[doc-verified: https://beautiful-soup-4.readthedocs.io/] \[doc-verified: https://lxml.de/]                                                                    |
| JavaScript pages     | **playwright 1.63.0 (rec)**                                               | browser-rendered content, interactions, or authenticated sessions                                                                                              | Avoid for ordinary HTML APIs: browser startup is heavier        | version checked at PyPI JSON endpoint   | \[doc-verified: https://playwright.dev/python/docs/intro]                                                                                                                                                          |
| Robots and TCP probe | **urllib.robotparser / asyncio.open_connection (rec)**                    | stdlib policy checks and port reachability with no extra dependency                                                                                            | A TCP connect proves reachability, not application health       | Python 3.12+ stdlib                     | \[doc-verified: https://docs.python.org/3/library/urllib.robotparser.html] \[doc-verified: https://docs.python.org/3/library/asyncio-stream.html#asyncio.open_connection]                                          |

## Design choices to put to the user

01. **Client:** httpx (recommended: sync/async parity and HTTP/2 option), requests, aiohttp, or stdlib; recommend httpx for most APIs.
02. **HTTP/2:** enabled or HTTP/1.1; recommend HTTP/1.1 unless the endpoint benefits and `http2=True` is requested \[doc-verified: https://www.python-httpx.org/http2/].
03. **Timeouts:** total and connect/read/write/pool values; recommend explicit finite values. HTTPX defaults to a 5-second network-inactivity timeout; `Limits` defaults are 100 total, 20 keep-alive, and 5-second keep-alive expiry \[doc-verified: https://www.python-httpx.org/advanced/timeouts/] \[doc-verified: https://www.python-httpx.org/advanced/resource-limits/].
04. **Retries/failure policy:** retry transient network errors and 429/5xx with exponential backoff and a cap; recommend honoring `Retry-After`, then fail with a nonzero exit code.
05. **Rate and concurrency:** requests/second, burst, and per-host in-flight cap; recommend explicit values plus one semaphore per host.
06. **Pagination:** page/offset, cursor, Link header, or next URL; recommend stop on absent/unchanged cursor and cap pages.
07. **Secrets:** environment variable (recommended for automation), OS keyring, or explicit prompt; never CLI arguments, logs, or source control.
08. **Downloads:** overwrite, atomic temp-and-rename, or resume with `Range`/`ETag`; recommend streaming, checksum, and atomic rename.
09. **Scraping policy:** user-agent, robots handling, delay, and static parser versus Playwright; recommend honor robots and prefer static HTML \[doc-verified: https://docs.python.org/3/library/urllib.robotparser.html].
10. **Output/idempotency:** JSON/CSV/file, overwrite versus skip, and dry-run behavior; recommend deterministic output and safe repeatability.

## Concurrency profile

This domain is usually I/O-bound. Use `asyncio` with a per-host `Semaphore` for async clients, or `ThreadPoolExecutor` for sync clients \[doc-verified: https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread]. Cap concurrency by provider quota, `Retry-After`, per-host connection limits, and response/download memory; HTTPX's pool defaults are 100 connections and 20 keep-alives \[doc-verified: https://www.python-httpx.org/advanced/resource-limits/]. Use `ProcessPoolExecutor`/`InterpreterPoolExecutor` only for substantial CPU parsing.

## Pitfalls

- No timeout: set finite connect/read/write/pool or total timeouts \[doc-verified: https://www.python-httpx.org/advanced/timeouts/].
- Unbounded fan-out: use per-host semaphores and client pool limits \[doc-verified: https://www.python-httpx.org/advanced/resource-limits/].
- Retrying all failures: retry only transient, safe operations; honor `Retry-After` on 429.
- Ignoring pagination: follow the documented cursor/next link, detect repeats, and cap pages.
- Buffering downloads: use streamed chunks, resume validation, checksum, and atomic rename.
- Logging secrets: redact authorization headers, cookies, URLs, and response bodies.
- Scraping without permission: fetch and evaluate robots rules with `RobotFileParser.can_fetch` \[doc-verified: https://docs.python.org/3/library/urllib.robotparser.html].
- Treating TCP success as HTTP health: perform an application-level request when health is required.
- Using a browser for static HTML: choose an HTTP client and parser first.

## Skeleton

```python
import asyncio
from dataclasses import dataclass

import httpx


@dataclass(slots=True, kw_only=True, frozen=True)
class FetchOptions:
    concurrency: int = 10
    deadline_seconds: float = 120.0
    request_seconds: float = 20.0
    connect_seconds: float = 5.0


async def fetch_json(client: httpx.AsyncClient, gate: asyncio.Semaphore, url: str) -> dict:
    async with gate:
        response = await client.get(url)
    response.raise_for_status()
    return response.json()


async def fetch_all(urls: list[str], options: FetchOptions) -> list[dict]:
    limits = httpx.Limits(max_connections=options.concurrency)
    timeout = httpx.Timeout(options.request_seconds, connect=options.connect_seconds)
    gate = asyncio.Semaphore(options.concurrency)
    async with (
        httpx.AsyncClient(limits=limits, timeout=timeout) as client,
        asyncio.timeout(options.deadline_seconds),
        asyncio.TaskGroup() as group,
    ):
        tasks = [group.create_task(fetch_json(client, gate, url)) for url in urls]
    return [task.result() for task in tasks]
```
