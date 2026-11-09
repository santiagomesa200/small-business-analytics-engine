"""Write deterministic, synthetic, messy inputs for a fictional company.

make(out, seeded=True) plants three problems on purpose:
  1. the April column is missing from the P&L
  2. May gross profit does not equal revenue minus COGS
  3. the opening cash balance and line of credit exist only in the PDF
make(out, seeded=False) writes a clean version, used by the tests.
"""

from __future__ import annotations

import csv
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

MONTHS = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"]
LABELS = ["Jan-25", "Feb-25", "Mar-25", "Apr-25", "May-25", "Jun-25"]
PRODUCTS = {  # name: (units per month, price Q1, price Q2)
    "Conduit Kit": ([3200, 3100, 3400, 3300, 3450, 3500], 42.00, 44.50),
    "Cable Spool": ([4600, 4500, 4800, 5000, 5200, 5400], 18.00, 18.50),
    "Safety Gear": ([1500, 1450, 1600, 1500, 1550, 1600], 95.00, 93.00),
}
COGS_RATIO = [0.58, 0.585, 0.59, 0.59, 0.595, 0.60]
OPEX_K = {  # $ thousands per month
    "Payroll": [92.0, 92.0, 93.5, 93.5, 95.0, 95.0],
    "Rent": [14.0] * 6,
    "Other Opex": [30.2, 28.9, 31.4, 29.8, 33.1, 30.5],
}
AR_ROWS = [  # customer, current, 1-30, 31-60, 61-90, over 90
    ("Customer 01", 120000, 40000, 12000, 0, 0),
    ("Customer 02", 90000, 35000, 0, 8400, 0),
    ("Customer 03", 60000, 22000, 15000, 0, 6000),
    ("Customer 04", 70000, 18000, 0, 0, 0),
    ("Customer 05", 40000, 16000, 9000, 0, 0),
]
BANK = dict(opening=586000, deposits=1000000, withdrawals=1173700, ending=412300, loc=150000)


def _sales_rows():
    for name, (units, p1, p2) in PRODUCTS.items():
        for i, m in enumerate(MONTHS):
            yield m, name, units[i], p1 if i < 3 else p2


def _write_pdf(path: Path, lines: list[str]) -> None:
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = "BT /F1 11 Tf 50 750 Td 18 TL\n" + "\n".join(f"({esc(x)}) Tj T*" for x in lines) + "\nET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n"
    path.write_bytes(out.encode("latin-1"))


def freeze_zip(path: Path) -> None:
    """openpyxl stamps the saved time and every zip entry with the clock; fix them so a re-run is byte-identical."""
    with zipfile.ZipFile(path) as z:
        parts = [(i.filename, z.read(i)) for i in z.infolist()]
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts:
            if name == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2025-07-01T00:00:00Z", data)
            z.writestr(zipfile.ZipInfo(name, (2025, 7, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)


def make(out: Path, seeded: bool = True) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rev = [0.0] * 6
    for m, _, u, p in _sales_rows():
        rev[MONTHS.index(m)] += u * p
    rev = [round(r) for r in rev]
    cogs = [round(r * c) for r, c in zip(rev, COGS_RATIO, strict=True)]
    opex_k = [round(sum(v[i] for v in OPEX_K.values()), 1) for i in range(6)]
    opex = [round(k * 1000) for k in opex_k]
    gp = [r - c for r, c in zip(rev, cogs, strict=True)]
    ebitda = [g - o for g, o in zip(gp, opex, strict=True)]
    if seeded:
        gp[4] += 9000  # typo in the May subtotal

    keep = [i for i in range(6) if not (seeded and i == 3)]  # seeded: April column absent
    wb = Workbook()
    ws = wb.active
    ws.title = "Monthly P&L"
    ws.append(["Bluebonnet Supply Co. - Monthly P&L (USD)"])
    ws.append([])
    ws.append(["Line Item"] + [LABELS[i] for i in keep])
    paren = lambda v: f"({v:,})"  # negatives shown in parentheses, stored as text
    ws.append(["Net Sales"] + [rev[i] for i in keep])
    ws.append(["Cost of Goods Sold"] + [paren(cogs[i]) for i in keep])
    ws.append(["Gross Profit"] + [gp[i] for i in keep])
    ws.append(["Operating Expenses"] + [paren(opex[i]) for i in keep])
    ws.append(["EBITDA"] + [ebitda[i] for i in keep])
    wd = wb.create_sheet("Opex Detail")
    wd.append(["Operating expenses detail ($ in thousands)"])
    wd.append([])
    wd.append(["Expense"] + LABELS)
    for name, vals in OPEX_K.items():
        wd.append([name] + vals)
    wd.append(["Total Opex"] + opex_k)
    wb.properties.created = datetime(2025, 7, 1)  # fixed, so a re-run is byte-identical
    wb.save(out / "pnl_2025_h1.xlsx")
    freeze_zip(out / "pnl_2025_h1.xlsx")

    assets = dict(cash=BANK["ending"], ar=sum(r[1] + r[2] + r[3] + r[4] + r[5] for r in AR_ROWS), inv=698000, fixed=340000)
    cur = assets["cash"] + assets["ar"] + assets["inv"]
    ta = cur + assets["fixed"]
    liab = 402500 + 210000  # accounts payable + other current liabilities (includes the line of credit)
    rows = [
        ("Cash & Equivalents", assets["cash"]),
        ("Trade Receivables", assets["ar"]),
        ("Inventory", assets["inv"]),
        ("Total Current Assets", cur),
        ("Property & Equipment, net", assets["fixed"]),
        ("Total Assets", ta),
        ("Accounts Payable", 402500),
        ("Other Current Liabilities", 210000),
        ("Total Liabilities", liab),
        ("Owner's Equity", ta - liab),
        ("Total Liabilities & Equity", ta),
    ]
    with open(out / "balance_sheet_2025-06-30.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Account", "As of 2025-06-30"])
        w.writerows((a, f"{v:,}") for a, v in rows)

    with open(out / "ar_aging_2025-06-30.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Customer", "Current", "1-30", "31-60", "61-90", "Over 90", "Total Due"])
        for r in AR_ROWS:
            w.writerow([r[0]] + [f"{v:,}" for v in r[1:]] + [f"{sum(r[1:]):,}"])
        w.writerow(["TOTAL"] + [f"{sum(r[i] for r in AR_ROWS):,}" for i in range(1, 6)] + [f"{assets['ar']:,}"])

    with open(out / "sales_by_product.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Month", "SKU Name", "Units Sold", "Avg Price"])
        w.writerows((m, n, f"{u:,}", f"${p:.2f}") for m, n, u, p in _sales_rows())

    b = BANK
    _write_pdf(
        out / "bank_statement_summary.pdf",
        [
            "Bluebonnet Supply Co. - Bank Statement Summary",
            "Statement period: 2025-04-01 to 2025-06-30",
            f"Opening balance: ${b['opening']:,.2f}",
            f"Total deposits: ${b['deposits']:,.2f}",
            f"Total withdrawals: ${b['withdrawals']:,.2f}",
            f"Ending balance: ${b['ending']:,.2f}",
            f"Line of credit outstanding: ${b['loc']:,.2f}",
        ],
    )


if __name__ == "__main__":
    # python scripts/make_sample_data.py [folder] [--clean]
    args = [a for a in sys.argv[1:] if a != "--clean"]
    dest = Path(args[0]) if args else Path("data/sample")
    make(dest, seeded="--clean" not in sys.argv)
    print(f"wrote synthetic inputs to {dest}")
