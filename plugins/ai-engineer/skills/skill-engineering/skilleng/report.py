"""Rendering. Every value that reaches a page is escaped, and the tier gates claims.

Agent-produced output is attacker-influenced data: the executor acts on a
user-supplied prompt and possibly untrusted input files, so everything it writes is
untrusted input to every rendering path. skill-creator embeds it with `json.dumps`
straight into a <script> block, where a single `</script>` in an output file both
breaks the viewer and opens an injection sink on the reviewer's localhost origin.
"""

from __future__ import annotations

import html
import json
from typing import Any

from .schema import Provenance, Tier


def safe_json_for_script(obj: Any) -> str:
    """JSON safe to place inside a <script> element.

    `json.dumps` alone is not: it escapes quotes but not `</script`, and the HTML
    parser ends the element at the first literal `</script` regardless of JS string
    context. Also neutralises `<!--` and U+2028/9, which break older parsers.
    """
    return (json.dumps(obj, default=str)
            .replace("</", "<\\/")
            .replace("<!--", "<\\!--")
            .replace(" ", "\\u2028")
            .replace(" ", "\\u2029"))


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def _iv(d: dict | None, pct: bool = True) -> str:
    if not d:
        return ""
    f = _pct if pct else (lambda v: f"{v:+.2f}")
    if d["low"] == float("-inf"):
        return " (interval undefined at n=1)"
    return f" [{f(d['low'])}, {f(d['high'])}]"


def to_markdown(bench: dict) -> str:
    prov = Provenance(**bench["provenance"])
    tier = Tier(prov.tier)
    L: list[str] = []
    L.append(f"# Benchmark — {prov.skill_name or '(unnamed skill)'}")
    L.append("")
    L.append(f"**Host** {prov.host or '?'} {prov.host_version or ''} · **Model** {prov.model or '?'} · "
             f"**Tier** {tier.value} · **Skill** `{prov.skill_content_hash or '?'}` · "
             f"**Assertions** `{prov.assertion_set_hash or '?'}`")
    L.append(f"**Run** {prov.created_at} on {prov.platform}")
    L.append("")
    L.append(f"> {bench['claims_permitted']['note']}")
    L.append("")

    L.append("## Arms")
    L.append("")
    show_tokens = any(a["tokens_available"] for a in bench["arms"])
    head = "| Arm | Runs | Errors | Score | Fired |" + (" Tokens |" if show_tokens else "") + " Time |"
    L.append(head)
    L.append("|---|---|---|---|---|" + ("---|" if show_tokens else "") + "---|")
    for a in bench["arms"]:
        score = _pct(a["mean_score"]) + _iv(a["score_interval"])
        fired = "n/a" if not a["trigger_rate"] else _pct(a["trigger_rate"]["point"]) + _iv(a["trigger_rate"])
        row = (f"| `{a['arm']}` | {a['runs']} | {a['errors']} ({_pct(a['error_rate'])}) | {score} | {fired} |")
        if show_tokens:
            row += f" {'—' if a['mean_tokens'] is None else format(a['mean_tokens'], '.0f')} |"
        row += f" {'—' if a['mean_duration_seconds'] is None else format(a['mean_duration_seconds'], '.1f')}s |"
        L.append(row)
    L.append("")

    L.append("## Deltas")
    L.append("")
    if not bench["deltas"]:
        L.append("_No arm pair was scored on a shared eval, so no delta can be computed._")
    else:
        L.append("| Delta | Treatment − Control | Paired evals | Value | Means |")
        L.append("|---|---|---|---|---|")
        for d in bench["deltas"]:
            val = f"{d['point']:+.2f}" + _iv(d["interval"], pct=False)
            L.append(f"| **{d['name']}** | `{d['treatment']}` − `{d['control']}` | {d['paired_evals']} | "
                     f"{val} | {d['interpretation']} |")
    L.append("")

    L.append("## Per eval")
    L.append("")
    arms = [a["arm"] for a in bench["arms"]]
    L.append("| Eval | " + " | ".join(f"`{a}`" for a in arms) + " |")
    L.append("|---|" + "---|" * len(arms))
    for row in bench["per_eval"]:
        cells = []
        for a in arms:
            c = row.get(a) or {}
            s = _pct(c.get("mean_score"))
            if c.get("errors"):
                s += f" ({c['errors']} err)"
            cells.append(f"{s} (n={c.get('runs', 0)})")
        L.append(f"| {row['eval_id']} | " + " | ".join(cells) + " |")
    L.append("")

    if bench["diagnostics"]:
        L.append("## Read this before quoting a number")
        L.append("")
        for d in bench["diagnostics"]:
            L.append(f"- {d}")
        L.append("")
    return "\n".join(L)


_CSS = """
:root{--bg:#f2f4f4;--fg:#14191b;--mut:#5b686b;--line:#cfd7d8;--card:#fbfcfc;--acc:#0d6e77;--warn:#8a5a00}
@media(prefers-color-scheme:dark){:root{--bg:#0e1214;--fg:#e6ecec;--mut:#9fadb0;--line:#2c3639;--card:#151b1d;--acc:#46b9c2;--warn:#e0a93f}}
*{box-sizing:border-box}body{margin:0;padding:32px 20px 64px;background:var(--bg);color:var(--fg);
font:16px/1.6 ui-serif,Georgia,serif}main{max-width:960px;margin:0 auto}
h1{font-family:ui-sans-serif,system-ui,sans-serif;font-size:30px;margin:0 0 4px}
h2{font-family:ui-sans-serif,system-ui,sans-serif;font-size:13px;letter-spacing:.1em;text-transform:uppercase;
margin:36px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--fg)}
.meta{font-family:ui-monospace,monospace;font-size:12px;color:var(--mut);margin:0 0 18px}
.note{border-left:3px solid var(--acc);background:var(--card);padding:12px 14px;margin:0 0 8px;font-size:15px}
.wrap{overflow-x:auto;border:1px solid var(--line);background:var(--card)}
table{border-collapse:collapse;width:100%;min-width:520px}
th{font-family:ui-monospace,monospace;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
color:var(--mut);text-align:left;padding:10px 12px;border-bottom:1px solid var(--line)}
td{padding:10px 12px;border-bottom:1px solid var(--line);font-size:15px;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}code{font-family:ui-monospace,monospace;font-size:.86em}
ul{padding-left:20px}li{margin-bottom:8px;color:var(--mut)}li b{color:var(--warn)}
"""


def _table(md_lines: list[str]) -> str:
    """Render a markdown table block as escaped HTML."""
    rows = [r.strip().strip("|").split("|") for r in md_lines if r.strip().startswith("|")]
    rows = [r for r in rows if not all(set(c.strip()) <= set("-: ") for c in r)]
    if not rows:
        return ""
    def cell(c: str, tag: str) -> str:
        t = html.escape(c.strip()).replace("`", "")
        t = t.replace("**", "")
        return f"<{tag}>{t}</{tag}>"
    head = "".join(cell(c, "th") for c in rows[0])
    body = "".join("<tr>" + "".join(cell(c, "td") for c in r) + "</tr>" for r in rows[1:])
    return f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def to_html(bench: dict) -> str:
    prov = Provenance(**bench["provenance"])
    md = to_markdown(bench).splitlines()
    sections: list[str] = []
    buf: list[str] = []
    title = ""
    for line in md:
        if line.startswith("## "):
            if buf:
                sections.append(_table(buf))
            sections.append(f"<h2>{html.escape(line[3:])}</h2>")
            buf = []
        elif line.startswith("|"):
            buf.append(line)
        elif line.startswith("- "):
            if buf:
                sections.append(_table(buf)); buf = []
            sections.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("_"):
            sections.append(f"<p class='meta'>{html.escape(line.strip('_'))}</p>")
    if buf:
        sections.append(_table(buf))
    body = "".join(sections).replace("<li>", "<ul><li>").replace("</li>", "</li></ul>")
    title = f"Benchmark — {prov.skill_name or 'skill'}"
    meta = (f"{prov.host or '?'} {prov.host_version or ''} · model {prov.model or '?'} · tier {prov.tier} · "
            f"skill {prov.skill_content_hash or '?'} · assertions {prov.assertion_set_hash or '?'} · {prov.created_at}")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body><main>"
            f"<h1>{html.escape(title)}</h1><p class='meta'>{html.escape(meta)}</p>"
            f"<p class='note'>{html.escape(bench['claims_permitted']['note'])}</p>"
            f"{body}</main></body></html>")
