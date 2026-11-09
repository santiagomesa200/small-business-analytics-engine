"""Builds docs/before-after.png with headless Chrome (set CHROME to its path if not the macOS default)."""

import html
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.read import read_folder

ROOT = Path(__file__).resolve().parent.parent
CHROME = os.getenv("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
AMBER = "background:#ffe0a3;outline:2px solid #e09a1a"


def raw_table() -> str:
    sheet = next(s for s in read_folder(ROOT / "data/sample") if s.name == "Monthly P&L")
    head, body = sheet.rows[2], sheet.rows[3:]
    th = "".join(f"<th>{html.escape(str(c))}</th>" for c in head[:4]) + f'<th style="{AMBER}">Apr-25<br>(column missing)</th>'
    th += "".join(f"<th>{html.escape(str(c))}</th>" for c in head[4:])
    rows = ""
    for r in body:
        cells = []
        for i, c in enumerate(r):
            style = ""
            if isinstance(c, str) and c.startswith("("):
                style = AMBER  # negatives stored as text in parentheses
            if r[0] == "Gross Profit" and i == 4:
                style = AMBER  # May subtotal that does not add up
            cells.append(f'<td style="{style}">{html.escape(f"{c:,}" if isinstance(c, (int, float)) else str(c))}</td>')
            if i == 3:
                cells.append(f'<td style="{AMBER}">&nbsp;</td>')
        rows += "<tr>" + "".join(cells) + "</tr>"
    return f"<table><tr>{th}</tr>{rows}</table>"


PAGE = """<!doctype html><meta charset="utf-8"><style>
body{margin:0;font:15px/1.4 system-ui,sans-serif;color:#1d2330;display:flex;height:800px;overflow:hidden}
.half{width:800px;box-sizing:border-box;padding:22px 26px;overflow:hidden}.after{background:#f6f8fb;border-left:2px solid #1f4e79}
h2{margin:0 0 4px;font-size:26px}h2 span{color:#1f4e79}p.sub{margin:0 0 14px;color:#5b6475}
table{border-collapse:collapse;font-size:13px;width:100%}th,td{border:1px solid #d5d9e0;padding:5px 6px;text-align:right}th:first-child,td:first-child{text-align:left}
th{background:#eef0f4}ul.n{margin:14px 0 0;padding-left:18px;font-size:13px}ul.n li{margin:6px 0}
b.k{display:inline-block;width:14px;height:14px;background:#ffe0a3;outline:2px solid #e09a1a;vertical-align:-2px;margin-right:6px}
iframe{width:1000px;height:900px;border:1px solid #d5d9e0;border-radius:8px;transform:scale(.72);transform-origin:0 0;background:#fff}
.clip{width:735px;height:660px;overflow:hidden}
</style>
<div class="half"><h2>Before</h2><p class="sub">The raw Monthly P&amp;L as the owner sent it</p>@@TABLE@@
<ul class="n"><li><b class="k"></b>April: the whole column is missing</li>
<li><b class="k"></b>Costs are text in parentheses, not numbers</li>
<li><b class="k"></b>May gross profit says 168,519; revenue minus costs is 159,519</li>
<li>Plus: units in thousands on another sheet, commas inside numbers, one figure only in a PDF</li></ul></div>
<div class="half after"><h2><span>After</span></h2><p class="sub">One command, one report: every number traced, gaps flagged</p>
<div class="clip"><iframe src="../outputs/sample/report.html"></iframe></div></div>"""


def shot(url: str, png: Path, size: str) -> None:
    if not Path(CHROME).exists():
        sys.exit(f"Chrome not found at {CHROME}. Set the CHROME environment variable to the Chrome executable.")
    subprocess.run(  # noqa: S603 - fixed arguments and a local file URL
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars", f"--screenshot={png}", f"--window-size={size}", url],
        check=True,
        capture_output=True,
    )


if __name__ == "__main__":
    page = ROOT / "docs/before-after.html"  # a scratch page: its iframe needs the docs/ folder, and it is deleted after the shot
    page.write_text(PAGE.replace("@@TABLE@@", raw_table()))
    try:
        shot(page.as_uri(), ROOT / "docs/before-after.png", "1600,800")
    finally:
        page.unlink()
    print("wrote docs/before-after.png")
