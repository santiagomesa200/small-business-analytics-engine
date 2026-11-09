"""Builds the GitHub Pages site: docs/site-data.json (from real engine runs), docs/index.html (data inlined),
and docs/reports/ (the HTML reports and the actions CSV). `python scripts/make_site.py`, or `--check` to compare without writing."""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import pipeline
from engine import verify as verify_mod
from engine.analyses import fmt
from engine.normalize import parse_month, to_number
from engine.plain import dates_to_words, first_month, fix, metric_name, pretty, why
from engine.read import read_folder
from engine.report import FIX, attention
from scripts.make_rejection_example import build as rejection_example

LINES = {
    "revenue": "Net sales",
    "cogs": "Cost of goods sold",
    "gross_profit": "Gross profit",
    "opex": "Operating expenses",
    "ebitda": "EBITDA",
}
SCENARIOS = {"messy": ("data/sample", "outputs/sample"), "clean": ("data/clean", "outputs/clean")}
INDEX = ROOT / "docs/index.html"
DATA = ROOT / "docs/site-data.json"
MARK = re.compile(r"(<!--SITE-DATA-->).*?(<!--/SITE-DATA-->)", re.S)


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
        elif i.kind == "missing_period":
            reason, cell, action = (
                f"{month}'s column is missing from the Monthly P&L.",
                f"Monthly P&L, {month} column (absent)",
                f"send the {month} column",
            )
        else:
            m = re.match(r"(.+?) \d{4}-\d{2}: file says ([\d,]+) but its parts give ([\d,]+)", i.message)
            reason = f"The file says ${m.group(2)}; its parts add up to ${m.group(3)}." if m else dates_to_words(i.message) + "."
            cell, action = fig.source.split(" | ")[-1], FIX.get(i.kind, fix("parts give"))
        out.append(dict(key=i.key, label=label, kind=i.kind, cell=cell, reason=reason, unblocks=list(dict.fromkeys(blocked)), fix=action))
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
            cells.insert(gap_at, dict(t="" if r_i > 2 else f"{missing[0][:3]}-25", k="absent", a=""))
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


def one(folder: str) -> dict:
    sheets = read_folder(ROOT / folder)
    with tempfile.TemporaryDirectory() as d:
        r = pipeline.run(ROOT / folder, d, offline=True)
        report_html = (Path(d) / "report.html").read_text()
    ledger, results, verdict = r["ledger"], r["results"], r["verdict"]
    n_ok = sum(f.value is not None for f in ledger.figs.values())
    count = lambda s: sum(x.status == s for x in results)
    summary = r["summary"]
    return dict(
        folder=folder,
        files=r["files"],
        read=stage_numbers(sheets),
        figures=dict(total=len(ledger.figs), usable=n_ok, flagged=len(ledger.figs) - n_ok),
        flags=flag_rows(ledger, results),
        grid=grid(sheets, ledger),
        attention=[dict(text=t, keys=k) for t, k in attention(ledger, results)],
        counts=dict(computed=count("computed"), partial=count("partial"), blocked=count("blocked"), total=len(results)),
        analyses=[
            dict(
                id=x.id,
                title=x.title,
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


def rejection(good: str) -> dict:
    bad, verdict = rejection_example()
    out = verdict.strip().splitlines()
    a, b = bad.split(), good.split()
    parts = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        parts.append(dict(t=" ".join(a[i1:i2]), bad=op != "equal", good=" ".join(b[j1:j2]) if op != "equal" else ""))
    rules = [re.sub(r"^\s*\d\.\s*", "", ln) for ln in (verify_mod.__doc__ or "").splitlines() if re.match(r"\s*\d\. ", ln)]
    return dict(parts=parts, verdict=out[0], problems=[ln[2:] for ln in out[1:]], rules=rules)


def licenses_data() -> dict:
    """The AI license and access reconciler run on data/licenses, shaped for the page."""
    from engine import licenses as lic

    res = lic.reconcile(ROOT / "data/licenses")
    summary = lic.draft(res)
    verdict = lic.verify(summary, res)
    cats = [
        dict(
            id=c,
            title=lic.TITLES[c],
            action=lic.ACTION[c],
            count=len(res.of(c)),
            monthly=res.saved(c),
            findings=[
                dict(
                    email=f.email,
                    tool=f.tool,
                    plan=f.plan,
                    cost=f.cost,
                    detail=f.detail,
                    action=f.action,
                    counted=f.counted,
                    sources=f.sources,
                )
                for f in res.of(c)
            ],
        )
        for c in lic.ORDER
    ]
    nums = sum(len(verify_mod.numbers(x)) for x in re.split(r"(?<=[.!?])\s+", summary))
    return dict(
        asof=str(res.asof),
        files=len(list((ROOT / "data/licenses").iterdir())),
        actions=len(res.findings),
        seats=res.seats,
        people=res.people,
        flagged=len({f.sources[0] for f in res.findings}),
        categories=cats,
        monthly=res.monthly,
        annual=res.annual,
        counted=sum(f.counted for f in res.findings),
        summary=summary,
        verifier=dict(ok=verdict.ok, problems=verdict.problems, numbers_checked=nums),
    )


def tests_collected() -> int:
    p = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True)
    return int(re.search(r"(\d+) tests? collected", p.stdout).group(1))


def build_data() -> tuple[dict, dict]:
    """(data for the page, html of each report). Deterministic: no timestamps, no runtimes."""
    sc = {k: one(f) for k, (f, _) in SCENARIOS.items()}
    reports = {k: v.pop("_report_html") for k, v in sc.items()}
    n = tests_collected()
    return dict(
        scenarios=sc,
        rejection=rejection(sc["messy"]["summary"]),
        licenses=licenses_data(),
        tests=n,
        engineering=dict(trace=sc["messy"]["trace"], tests=n),
    ), reports


def inline(data: dict, text: str) -> str:
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return MARK.sub(lambda m: f'{m.group(1)}<script id="site-data" type="application/json">{blob}</script>{m.group(2)}', text)


def sync_counts(n: int, write: bool = True, root: Path = ROOT) -> list[str]:
    """Put the gate's real test count into README.md. Returns the files that were out of date."""
    stale = []
    f = root / "README.md"
    old = f.read_text()
    new = re.sub(r"\b\d+ tests\b", f"{n} tests", old)
    if new != old:
        stale.append(f.name)
        if write:
            f.write_text(new)
    return stale


FONT_URL = re.compile(r"url\([^)]*?fonts/")  # the font path depends on where a report is written


def fresh_files() -> dict[str, str]:
    """Every committed report and CSV as a fresh offline run writes it, keyed by repo path. Font URLs are normalized."""
    from engine import licenses as lic

    out: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        runs = {**{k: (f, rel) for k, (f, rel) in SCENARIOS.items()}, "licenses": ("data/licenses", "outputs/licenses")}
        for name, (folder, rel) in runs.items():
            d = Path(tmp) / name
            pipeline.run(ROOT / folder, d, offline=True) if name != "licenses" else lic.run(ROOT / folder, d)
            for f in d.iterdir():
                out[f"{rel}/{f.name}"] = f.read_text()
    for src, dst in DOCS_COPIES.values():
        out[f"docs/reports/{dst}"] = out[src]
    bad, verdict = rejection_example()
    out["outputs/examples/rejected_summary.txt"], out["outputs/examples/verifier_output.txt"] = bad + "\n", verdict
    return {k: FONT_URL.sub("url(FONTS/", v) for k, v in out.items()}


DOCS_COPIES = {
    "messy": ("outputs/sample/report.html", "messy.html"),
    "clean": ("outputs/clean/report.html", "clean.html"),
    "licenses": ("outputs/licenses/report.html", "licenses.html"),
    "licenses-actions": ("outputs/licenses/actions.csv", "licenses-actions.csv"),
}


def check(root: Path = ROOT) -> list[str]:
    """Problems if any committed page data, report or CSV differs from a fresh offline run of the engine."""
    fresh = json.loads(json.dumps(build_data()[0]))  # tuples become lists, as in the file
    fails = []
    data, index = root / "docs/site-data.json", root / "docs/index.html"
    if not data.exists() or json.loads(data.read_text()) != fresh:
        fails.append("docs/site-data.json does not match a fresh engine run (run python scripts/make_site.py)")
    m = re.search(r'<script id="site-data" type="application/json">(.*?)</script>', index.read_text(), re.S)
    if not m or json.loads(m.group(1).replace("<\\/", "</")) != fresh:
        fails.append("docs/index.html carries data that does not match a fresh engine run")
    fails += [
        f"{n} has a different test count than the gate (run python scripts/make_site.py)"
        for n in sync_counts(fresh["tests"], write=False, root=root)
    ]
    for path, text in fresh_files().items():
        f = root / path
        if not f.exists() or FONT_URL.sub("url(FONTS/", f.read_text()) != text:
            fails.append(f"{path} does not match a fresh run (run python scripts/make_site.py)")
    return fails


def main() -> None:
    if "--check" in sys.argv:
        problems = check()
        print("\n".join(problems) or "site data matches a fresh run")
        sys.exit(bool(problems))
    data, _ = build_data()
    from engine import licenses as lic

    for folder, out in SCENARIOS.values():  # refresh the committed outputs so the linked reports match the data
        pipeline.run(ROOT / folder, ROOT / out, offline=True)
    lic.run(ROOT / "data/licenses", ROOT / "outputs/licenses")
    (ROOT / "outputs/examples/rejected_summary.txt").write_text(rejection_example()[0] + "\n")
    (ROOT / "outputs/examples/verifier_output.txt").write_text(rejection_example()[1])
    (ROOT / "docs/reports").mkdir(exist_ok=True)
    for src, dst in DOCS_COPIES.values():  # the reports sit one level from the fonts here
        text = (ROOT / src).read_text()
        (ROOT / "docs/reports" / dst).write_text(FONT_URL.sub("url(../fonts/", text) if dst.endswith(".html") else text)
    sync_counts(data["tests"])
    DATA.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    INDEX.write_text(inline(data, INDEX.read_text()))
    print("wrote docs/site-data.json, docs/index.html (data inlined), docs/reports/{messy,clean}.html")


if __name__ == "__main__":
    main()
