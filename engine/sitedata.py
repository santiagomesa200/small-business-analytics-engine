"""Turns one real pipeline run into the data the site draws: scripts/make_site.py saves it, and the browser's "Run it live" button
calls the same code in Pyodide, so there is one implementation to compare against."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from . import pipeline
from . import verify as verify_mod
from .analyses import fmt
from .extract import file_label
from .normalize import parse_month, to_number
from .plain import ANALYSIS_NAMES, dates_to_words, first_month, fix, metric_name, pretty, why
from .read import read_folder
from .report import FIX, attention

LINES = {
    "revenue": "Net sales",
    "cogs": "Cost of goods sold",
    "gross_profit": "Gross profit",
    "opex": "Operating expenses",
    "ebitda": "EBITDA",
}


def causes(x, say=why) -> str:
    """Every distinct root cause of an analysis (or its fix, with say=fix), joined with 'and' (not the knock-on 'needs DSO' ones)."""
    found = [say(m.reason) for m in x.metrics if m.reason and "needs DSO" not in m.reason and "at least one month" not in m.reason]
    return " and ".join(dict.fromkeys(found)) or (say(x.reason) if x.reason else "")


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def flag_rows(ledger, results) -> list[dict]:
    out = []
    for i in ledger.issues:
        fig = ledger.figs.get(i.key)  # issues about a whole file are keyed by its name, not by a figure
        month = first_month(i.key) or ""
        blocked = []
        for r in results:
            if r.blocked and i.key in r.blocked:
                blocked.append(r.title[0].lower() + r.title[1:])
            blocked += [metric_name(m.label) for m in r.metrics if m.reason and i.key in m.reason]
        line = i.key.split(".")[1] if fig else ""
        label = f"{LINES.get(line, line)}, {month}" if fig else i.key
        if fig is None:
            reason, cell, action = dates_to_words(i.message) + ".", i.key, FIX.get(i.kind, fix(""))
            where = cell
        elif i.kind == "missing_period":
            reason, cell, action = (
                f"{month}'s column is missing from the Monthly P&L.",
                f"Monthly P&L, {month} column (absent)",
                f"send the {month} column",
            )
            where = cell
        else:
            m = re.match(r"(.+?) \d{4}-\d{2}: file says ([\d,]+) but its parts give ([\d,]+)", i.message)
            reason = f"The file says ${m.group(2)}; its parts add up to ${m.group(3)}." if m else dates_to_words(i.message) + "."
            cell, action = fig.source.split(" | ")[-1], FIX.get(i.kind, fix("parts give"))
            where = f"{fig.source.split(' | ')[-2]}, cell {cell}"
        out.append(
            dict(
                figure=i.key,
                label=label,
                kind=i.kind,
                cell=cell,
                where=where,
                reason=reason,
                unblocks=list(dict.fromkeys(blocked)),
                fix=action,
            )
        )
    return out


def grid(sheets, ledger) -> dict:
    sh = next(s for s in sheets if s.name == "Monthly P&L")
    flagged = {i.key: ledger.figs[i.key].source.split(" | ")[-1] for i in ledger.issues if i.kind == "subtotal_mismatch"}
    cells_flagged = set(flagged.values())
    missing = [first_month(i.key) for i in ledger.issues if i.kind == "missing_period"]
    head = sh.rows[2]
    months = [parse_month(c) for c in head]
    rows, gap_at = [], None
    if missing:  # place the absent month after the last month before it
        want = next(i.key for i in ledger.issues if i.kind == "missing_period")[-7:]
        gap_at = max(i for i, m in enumerate(months) if m and m < want) + 1
    for r_i, row in enumerate(sh.rows[2:], start=2):
        cells = []
        for c_i, v in enumerate(row):
            addr = f"{chr(65 + c_i)}{r_i + 1}"
            text = f"{v:,}" if isinstance(v, (int, float)) else str(v)
            kind = "trip" if addr in cells_flagged else ("fixed" if isinstance(v, str) and to_number(v) is not None else "")
            cells.append(dict(t=text, k=kind, a=addr))
        if gap_at is not None:
            cells.insert(gap_at, dict(t="" if r_i > 2 else f"{(missing[0] or '')[:3]}-25", k="absent", a=""))
        rows.append(cells)
    return dict(title=sh.rows[0][0], rows=rows, gap_at=gap_at)


def stage_numbers(sheets) -> dict:
    texty = sum(
        1
        for s in sheets
        if not s.file.endswith(".pdf")
        for r in s.rows
        for v in r
        if isinstance(v, str) and to_number(v) is not None and any(ch in v for ch in "($,")
    )
    return dict(
        files=len({s.file for s in sheets}),
        sheets=len(sheets),
        rows=sum(len(s.rows) for s in sheets),
        text_numbers=texty,
        thousands_sheets=sum(
            1 for s in sheets if re.search(r"in thousands|\$000|\(000", " ".join(str(c) for c in (s.rows[0] if s.rows else []) if c), re.I)
        ),
    )


def one(folder: str, base: str | Path = ".") -> dict:
    """One company's site data from a real engine run on base/folder. The page runs this same function in the browser."""
    sheets = read_folder(Path(base) / folder)
    with tempfile.TemporaryDirectory() as d:
        r = pipeline.run(Path(base) / folder, d, offline=True)
        report_html = (Path(d) / "report.html").read_text()
    ledger, results, verdict = r["ledger"], r["results"], r["verdict"]
    n_ok = sum(f.value is not None for f in ledger.figs.values())
    count = lambda s: sum(x.status == s for x in results)
    summary = r["summary"]
    return dict(
        folder=folder,
        files=r["files"],
        file_labels=[dict(file=f, label=file_label(f)) for f in r["files"]],
        read=stage_numbers(sheets),
        figures=dict(total=len(ledger.figs), usable=n_ok, flagged=len(ledger.figs) - n_ok),
        flags=flag_rows(ledger, results),
        grid=grid(sheets, ledger),
        attention=[dict(text=t, figures=k) for t, k in attention(ledger, results)],
        counts=dict(computed=count("computed"), partial=count("partial"), blocked=count("blocked"), total=len(results)),
        analyses=[
            dict(
                id=x.id,
                title=x.title,
                name=ANALYSIS_NAMES.get(x.id, x.title),
                status=x.status,
                why=causes(x),
                fix=causes(x, fix),
                metrics=[
                    dict(
                        label=pretty(m.label),
                        value=fmt(m) if m.value is not None else None,
                        why=why(m.reason) if m.reason else "",
                        source=m.source,
                    )
                    for m in x.metrics
                ],
                assumptions=x.assumptions,
            )
            for x in results
        ],
        summary=summary,
        drafter=r["drafter"],
        verifier=dict(
            ok=verdict.ok,
            problems=verdict.problems,
            sentences=len(re.split(r"(?<=[.!?])\s+", summary.strip().replace(". [", " ["))),
            numbers_checked=sum(len(verify_mod.numbers(s)) for s in re.split(r"(?<=[.!?])\s+", summary)),
        ),
        report=dict(
            strip=[
                ("figures read", str(len(ledger.figs))),
                ("need attention", str(len(attention(ledger, results)))),
                ("analyses fully computed", f"{count('computed')} of {len(results)}"),
                ("verifier", "PASS" if verdict.ok else "FAIL"),
            ]
        ),
        trace=trace(sheets, ledger, results, summary, verdict),
        _report_html=report_html,
    )


def trace(sheets, ledger, results, summary, verdict) -> list[dict] | None:
    """One real figure followed from its cell to the verifier, for the engineers' sheet. Every value comes from the run."""
    key = next((i.key for i in ledger.issues if i.kind == "subtotal_mismatch"), None)
    if key is None:
        return None
    _, line, month = key.split(".")
    fig, issue = ledger.figs[key], next(i for i in ledger.issues if i.key == key)
    cell_of = lambda k: ledger.figs[k].source.split(" | ")[-1]
    sheet = next(sh for sh in sheets if sh.name == fig.source.split(" | ")[1])
    raw = lambda k: sheet.rows[int(re.sub(r"\D", "", cell_of(k))) - 1][col_index(re.sub(r"\d", "", cell_of(k)))]
    rev, cogs = f"pnl.revenue.{month}", f"pnl.cogs.{month}"
    gm = next(r for r in results if r.id == "gross_margin")
    metric = next(m for m in gm.metrics if m.label.endswith(month))
    sentence = next(x for x in re.split(r"(?<=[.!?])\s+", summary.replace(". [", " [")) if "[gross_margin]" in x)
    matched = []
    for value, dec, unit in verify_mod.scan(sentence):
        label = next((m.label for m in gm.metrics if m.value is not None and fmt(m).startswith(f"{value:.{dec}f}")), "")
        matched.append(f"{value:.{dec}f}{unit or ''} = {pretty(label)}")
    d = lambda v: f"{v:,.0f}"
    month_name = first_month(key)
    attn = next(t for t, k in attention(ledger, results) if key in k)
    return [
        dict(
            stage="READ",
            file="engine/read.py",
            text=f"{fig.source.split(' | ')[0]}, sheet {sheet.name}, cell {cell_of(key)} holds {raw(key)!r}. Nothing is interpreted yet.",
        ),
        dict(
            stage="NORMALIZE",
            file="engine/normalize.py",
            text=f"{raw(key)!r} becomes the number {d(fig.reported)}. The neighboring cost cell {raw(cogs)!r} becomes {d(ledger.figs[cogs].value)}, stored as a positive amount.",
        ),
        dict(
            stage="EXTRACT",
            file="engine/extract.py",
            text=f"Ledger key {key} gets the value {d(fig.reported)} and the source {fig.source}.",
        ),
        dict(
            stage="CHECK",
            file="engine/checks.py",
            text=f"{month_name} revenue {d(ledger.figs[rev].value)} minus cost of goods {d(ledger.figs[cogs].value)} is {d(ledger.figs[rev].value - ledger.figs[cogs].value)}, but the file says {d(fig.reported)}. The ledger value becomes None, the reported {d(fig.reported)} is kept for the audit trail, and an issue is logged: {dates_to_words(issue.message)}.",
        ),
        dict(
            stage="ANALYZE",
            file="engine/analyses.py",
            text=f"{pretty(metric.label)} is not computed ({why(metric.reason)}). The other months still compute, so the analysis status is {gm.status}.",
        ),
        dict(stage="DRAFT", file="engine/summarize.py", text=f"The template writes: {sentence}"),
        dict(
            stage="VERIFY",
            file="engine/verify.py",
            text=f"The sentence cites [gross_margin]. Its numbers match computed figures with the same unit ({'; '.join(matched)}), and {month_name} is described as not computed. Verdict: {'PASS' if verdict.ok else 'FAIL'}.",
        ),
        dict(
            stage="REPORT",
            file="engine/report.py",
            text=f"Needs attention: {attn} The row in figures.csv has an empty value and the reason.",
        ),
    ]
