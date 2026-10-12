<!-- Reference: colorized terminal output, progress bars, tables, and pretty logging with rich. Read when the user opts into pretty output during design. -->

# Terminal output with rich

## When to use

Ask during design: "Pretty, colorized terminal output?" Default **no** for cron, CI, systemd, and anything piped or parsed: plain `logging` to stderr. Choose **yes** for scripts a person watches interactively. A yes adds `rich` (15.0.0, \[doc-verified: https://pypi.org/pypi/rich/json]) to the PEP 723 `dependencies`. Pretty output never replaces exit codes or machine-readable output. A `--json` or CSV result still goes to stdout untouched.

## Verified facts

- `Console(stderr=True)` writes to `sys.stderr`. Use one stderr console for logs, progress, and tables so stdout stays clean for data. \[doc-verified: https://rich.readthedocs.io/en/stable/console.html]
- Rich auto-detects terminals and writes plain text when output is piped to a file or another program. `force_terminal=True` overrides this, and `TTY_COMPATIBLE=1` does the same from the environment. \[doc-verified: https://rich.readthedocs.io/en/stable/console.html]
- `NO_COLOR` disables color (styles such as bold and dim remain) and takes precedence over `FORCE_COLOR`. Do not add a custom `--no-color` flag that duplicates it. \[doc-verified: https://rich.readthedocs.io/en/stable/console.html]
- `RichHandler` plugs into `logging.basicConfig(handlers=[...])` with `format='%(message)s'` because the handler renders the time and level itself. `rich_tracebacks=True` formats exceptions. \[doc-verified: https://rich.readthedocs.io/en/stable/logging.html]
- `track(sequence, description=...)` covers simple loops. Use `Progress(transient=True)` with `add_task` and `advance` for several concurrent tasks, which also removes the bar when the work finishes. \[doc-verified: https://rich.readthedocs.io/en/stable/progress.html]
- `Table(title=...)`, `add_column(..., justify='right')`, and `add_row(...)` build the end-of-run summary. \[doc-verified: https://rich.readthedocs.io/en/stable/tables.html]

## Concurrency notes

- Update one `Progress` from the main thread or the event loop. Have worker threads or processes return results, and advance the bar as futures complete (`as_completed`) rather than inside workers.
- Process-pool workers must not hold a `Console`. Log from the parent, or let child records use plain `logging`.

## Pitfalls

- Printing progress or tables to stdout breaks pipelines. Always use the stderr console.
- Under `--verbose` with `RichHandler`, keep the `%(message)s`-only format. Adding `%(asctime)s` prints the time twice.

## Skeleton

```python
import logging
from typing import TYPE_CHECKING

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import track
from rich.table import Table

if TYPE_CHECKING:
    from collections.abc import Sequence

console = Console(stderr=True)


def configure_logging(*, verbose: bool) -> None:
    handler = RichHandler(console=console, rich_tracebacks=True, show_path=False)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(message)s', datefmt='[%X]', handlers=[handler])


def process_all(items: Sequence[str]) -> list[str]:
    return [item.upper() for item in track(items, description='processing', console=console)]


def render_summary(rows: Sequence[tuple[str, int]]) -> Table:
    table = Table(title='Summary')
    table.add_column('Item')
    table.add_column('Count', justify='right')
    for name, count in rows:
        table.add_row(name, str(count))
    return table
```
