<!-- Reference: rendering Markdown, HTML, or text reports with Jinja2 templates. Read when the automation's output is a report and the user chose templates over f-strings. Researched 2026-10-06. -->

# Reports with Jinja2

## When to use

When the output is a report, ask: "Jinja template or f-strings?" Recommend **f-strings** for single-section text or Markdown under about 30 lines. Recommend **Jinja2** (3.1.6, \[doc-verified: https://pypi.org/pypi/Jinja2/json]) for HTML, for loops and conditionals over rows, for reports that non-developers edit, and for more than one output format from the same data. Templates live in a `templates/` directory next to the script. For a single-file script, the template can be an inline string constant.

## Verified facts

- Build one `Environment` with a loader. Use `FileSystemLoader(searchpath, encoding='utf-8', followlinks=False)` for a directory, resolving relative paths against the script rather than the current working directory, or `PackageLoader('pkg')` for an installed package. \[doc-verified: https://jinja.palletsprojects.com/en/stable/api/]
- Autoescaping is off by default. `select_autoescape(enabled_extensions=('html', 'htm', 'xml'), default_for_string=True, default=False)` turns it on by file extension, so it is always on for HTML and off for `.md` or `.txt`. \[doc-verified: https://jinja.palletsprojects.com/en/stable/api/]
- `undefined=StrictUndefined` raises on any undefined variable instead of rendering blank. Always set it so a typo fails loudly. \[doc-verified: https://jinja.palletsprojects.com/en/stable/api/]
- `trim_blocks=True` removes the first newline after a block tag, and `lstrip_blocks=True` strips whitespace before a block tag. Set both for Markdown and text output. `keep_trailing_newline=True` keeps the file's final newline (the default strips it). \[doc-verified: https://jinja.palletsprojects.com/en/stable/api/]
- `jinja2.sandbox.SandboxedEnvironment` restricts attribute and function access and raises `SecurityError` on unsafe access. Use it only when the user supplies the template text. It is not a full security boundary for hostile templates. \[doc-verified: https://jinja.palletsprojects.com/en/stable/sandbox/]

## Design rules

- Pass plain data to `render()`: frozen dataclasses, lists, and precomputed totals. Compute in Python, and keep only layout in the template.
- Mark values safe with `|safe` only for HTML that the script built itself, never for input data.
- Write the report with `encoding='utf-8'`, print its path at the end, and honor `--dry-run` by rendering to stdout instead of writing the file.

## Skeleton

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True, kw_only=True, frozen=True)
class ReportRow:
    host: str
    status: str
    detail: str


def build_environment(template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=('html', 'htm', 'xml')),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def write_report(
    environment: Environment, template_name: str, *, rows: list[ReportRow], output: Path
) -> None:
    template = environment.get_template(template_name)
    output.write_text(
        template.render(rows=rows, failed=sum(row.status != 'ok' for row in rows)), encoding='utf-8'
    )
```
