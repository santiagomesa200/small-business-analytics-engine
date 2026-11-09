"""Write report.md and a one-page report.html from the same list of blocks."""

from __future__ import annotations

import html
import os
import re
from pathlib import Path

import pandas as pd

from .analyses import Result, fmt
from .model import Ledger
from .plain import COMPANY, dates_to_words, first_month, fix, metric_name, pretty, why
from .verify import Verdict

ROOT = Path(__file__).resolve().parent.parent
CSS = (Path(__file__).parent / "report.css").read_text()
FIX = {
    "cross_file_mismatch": "confirm which file is right",
    "balance_sheet_imbalance": "confirm which total is right",
    "unrecognized_file": "tell us what this file is",
    "missing_input": "send the file",
    "missing_value": "fill in the blank value",
    "unreadable_file": "send the file again, or save it as .xlsx or .csv",
    "bad_schema": "check the file has these columns and send it again",
    "bad_row": "fix or remove that row and send the file again",
    "empty_file": "send a file with data in it",
}

FILE_KINDS = {"unreadable_file", "bad_schema", "bad_row", "empty_file", "unrecognized_file", "missing_input"}


def attention(ledger: Ledger, results: list[Result]) -> list[tuple[str, str]]:
    """One plain-English item per problem: (text, technical keys)."""
    groups: dict[tuple[str, str], list[str]] = {}
    for i in ledger.issues:
        groups.setdefault((i.kind, i.message), []).append(i.key)
    items = []
    for (kind, msg), keys in groups.items():
        month = first_month(keys[0]) or ""
        blocked = []  # what this problem stops us from computing
        for r in results:
            if r.blocked and any(k in r.blocked for k in keys):
                blocked.append(r.title[0].lower() + r.title[1:])
            blocked += [metric_name(m.label) for m in r.metrics if m.reason and any(k in m.reason for k in keys)]
        if kind == "missing_period":
            sheet = re.search(r"'([^']+)'", msg)
            what, action = f"{month} is missing from the {sheet.group(1) if sheet else 'file'}.", f"send the {month} column"
        elif kind == "subtotal_mismatch" and (m := re.match(r"(.+?) \d{4}-\d{2}: file says ([\d,]+) but its parts give ([\d,]+)", msg)):
            what = f"{month}'s {m.group(1).lower()} is ${m.group(2)} in the file, but its parts add up to ${m.group(3)}."
            action = fix("parts give")
        else:
            what, action = (
                (msg if kind in FILE_KINDS else dates_to_words(msg)) + ".",
                FIX.get(kind, fix("")),
            )  # a file name may hold 2025-06
        if kind == "unreadable_file" and keys[0].lower().endswith(".pdf"):
            action = "send the file again"  # a PDF cannot be saved as .xlsx or .csv
        text = what + (f" This blocks: {', '.join(dict.fromkeys(blocked))}." if blocked else "") + f" Fix: {action}."
        items.append((text, ", ".join(keys)))
    return items


def blocks(ledger: Ledger, results: list[Result], summary: str, drafter: str, verdict: Verdict) -> list:
    count = lambda s: sum(r.status == s for r in results)
    items = attention(ledger, results)
    b = [
        ("h1", f"{COMPANY} – Analysis report"),
        ("p", "Synthetic data. Every figure traces to a source file; missing or inconsistent figures are flagged, never estimated."),
        (
            "strip",
            [
                (str(len(ledger.figs)), "figures read"),
                (str(len(items)), "need attention"),
                (
                    f"{count('computed')} of {len(results)}",
                    f"analyses fully computed ({count('partial')} partial, {count('blocked')} blocked)",
                ),
                ("PASS" if verdict.ok else "FAIL", "verifier"),
            ],
        ),
        ("h2", "Executive summary"),
    ]
    if verdict.ok:
        b += [("summary", summary), ("small", f"Drafted by: {drafter}. Checked by a separate verifier before it appears here.")]
    else:
        b += [
            ("p", "Summary blocked: the verifier rejected the draft, so it is not shown."),
            ("ul", verdict.problems),
            ("small", f"Drafted by: {drafter}."),
        ]
    b += [("h2", f"Needs attention ({len(items)} item{'' if len(items) == 1 else 's'})"), ("box", items or [("Nothing flagged.", "")])]
    for n, r in enumerate(results, 1):
        b.append(("h2", f"{n}. {r.title} ({r.status})"))
        if r.blocked:
            b += [("p", f"Not computed because {why(r.reason)}. Fix: {fix(r.reason)}."), ("small", f"Technical detail: {r.blocked}")]
        if r.metrics:
            b.append(
                (
                    "table",
                    [
                        (pretty(m.label), fmt(m) if m.value is not None else f"not computed ({why(m.reason or '')})", m.source)
                        for m in r.metrics
                    ],
                )
            )
        if r.assumptions:
            b += [("small", "Assumptions"), ("ul", r.assumptions)]
    b.append(("small", "Provenance for every figure (file, sheet, cell, and the reason for any gap): figures.csv."))
    return b


def strip_md(num: str, label: str) -> str:
    """'2 of 5', 'analyses fully computed (2 partial, 1 blocked)' -> 'analyses fully computed: 2 of 5 (2 partial, 1 blocked)'."""
    head, _, rest = label.partition(" (")
    return f"{head}: {num}" + (f" ({rest}" if rest else "")


def to_md(bl: list) -> str:
    out = []
    for kind, x in bl:
        if kind == "h1":
            out.append(f"# {x}\n")
        elif kind == "h2":
            out.append(f"## {x}\n")
        elif kind in ("p", "small", "summary"):
            out.append(x + "\n")
        elif kind == "strip":
            out.append(" | ".join(strip_md(num, label) for num, label in x) + "\n")
        elif kind == "ul":
            out.append("\n".join(f"- {i}" for i in x) + "\n")
        elif kind == "box":
            out.append("\n".join(f"- {t}" + (f"\n  Technical detail: {k}" if k else "") for t, k in x) + "\n")
        elif kind == "table":
            cell = lambda t: t.replace("|", "\\|")  # a raw pipe would split the cell and GitHub would drop the Source column
            rows = "\n".join(f"| {cell(a)} | {cell(v)} | {cell(s)} |" for a, v, s in x)
            out.append("| Item | Value | Source |\n|---|---|---|\n" + rows + "\n")
    return "\n".join(out)


def fonts_rel(out_dir) -> str:
    return os.path.relpath(ROOT / "docs/fonts", Path(out_dir).resolve()) + "/"


def to_html(bl: list, title: str | None = None, fonts: str = "../docs/fonts/") -> str:
    e, out = html.escape, []
    title = title or next(x for kind, x in bl if kind == "h1")  # the page title is the heading
    li = lambda t, k: f"<li>{e(t)}" + (f"<details><summary>technical detail</summary><code>{e(k)}</code></details>" if k else "") + "</li>"
    for kind, x in bl:
        if kind in ("h1", "h2"):
            st = re.search(r"\((computed|partial|blocked)\)$", x)
            out.append(
                f"<{kind}>{e(x[: st.start()].rstrip()) if st else e(x)}"
                + (f' <span class="st st-{st.group(1)}">{st.group(1)}</span>' if st else "")
                + f"</{kind}>"
            )
        elif kind == "p":
            out.append(f"<p>{e(x)}</p>")
        elif kind == "summary":  # [analysis_id] becomes a small grey source tag
            out.append(
                '<p class="summary">'
                + re.sub(r"\[(\w+)\]", lambda m: f'<span class="tag">{m.group(1).replace("_", " ")}</span>', e(x))
                + "</p>"
            )
        elif kind == "small":
            out.append(f'<p class="small">{e(x)}</p>')
        elif kind == "strip":
            out.append(
                '<p class="status">'
                + " &nbsp;|&nbsp; ".join(
                    f'<span class="{"bad" if (label == "need attention" and n != "0") or n == "FAIL" else "good" if n == "PASS" else ""}">{e(n)}</span> {e(label)}'
                    if label != "verifier"
                    else f'{e(label)} <span class="{"good" if n == "PASS" else "bad"}">{e(n)}</span>'
                    for n, label in x
                )
                + "</p>"
            )
        elif kind == "ul":
            out.append("<ul>" + "".join(f"<li>{e(i)}</li>" for i in x) + "</ul>")
        elif kind == "box":
            out.append(
                f'<div class="box{" ok" if x == [("Nothing flagged.", "")] else ""}"><ul>' + "".join(li(t, k) for t, k in x) + "</ul></div>"
            )
        elif kind == "table":
            rows = "".join(
                f"<tr><td>{e(a)}</td><td{' class=num' if re.match(r'[-$0-9]', v) else ''}>{e(v)}</td><td>{e(s)}</td></tr>" for a, v, s in x
            )
            out.append(f"<table><tr><th>Item</th><th>Value</th><th>Source</th></tr>{rows}</table>")
    ok = next((n for kind, x in bl if kind == "strip" for n, label in x if label == "verifier"), "")
    tb = (
        f'<footer class="tb"><div><span>Title</span><b>{e(title)}</b></div><div><span>Drawn by</span><b>Analytics engine</b></div>'
        f'<div><span>Checked by</span><b>Verifier <i class="{"g" if ok == "PASS" else "r"}" style="font-style:normal">{e(ok)}</i></b></div>'
        "<div><span>Source</span><b>Synthetic data</b></div></footer>"
    )
    css = CSS.replace("@FONTS@", fonts)
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="color-scheme" content="light dark"><title>{e(title)}</title><style>{css}</style>'
        '<body><main class="sheet">' + "".join(out) + tb + "</main></body></html>"
    )


def write(out_dir: Path, ledger: Ledger, results: list[Result], summary: str, drafter: str, verdict: Verdict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    bl = blocks(ledger, results, summary, drafter, verdict)
    (out_dir / "report.md").write_text(to_md(bl))
    (out_dir / "report.html").write_text(to_html(bl, fonts=fonts_rel(out_dir)))
    pd.DataFrame(
        [{"key": f.key, "value": f.value, "source": f.source, "reason": f.reason, "reported": f.reported} for f in ledger.figs.values()]
    ).to_csv(out_dir / "figures.csv", index=False)
