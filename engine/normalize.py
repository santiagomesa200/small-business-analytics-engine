"""Turn messy labels, units and number formats into one convention."""

from __future__ import annotations

import math
import re
from datetime import date, datetime

PNL = {
    "revenue": {"revenue", "net sales", "sales", "total revenue", "total sales"},
    "cogs": {"cogs", "cost of goods sold", "cost of sales"},
    "gross_profit": {"gross profit", "gross margin"},
    "opex": {"operating expenses", "opex", "total opex", "total operating expenses"},
    "ebitda": {"ebitda"},
}
COST_ITEMS = {"cogs", "opex"}  # stored as positive amounts, whatever sign the file used
BS = {
    "cash": {"cash", "cash & equivalents", "cash and cash equivalents"},
    "ar": {"accounts receivable", "trade receivables", "a/r"},
    "inventory": {"inventory", "inventories"},
    "current_assets": {"total current assets"},
    "fixed_assets": {"property & equipment, net", "pp&e, net", "fixed assets"},
    "total_assets": {"total assets"},
    "ap": {"accounts payable", "a/p", "trade payables"},
    "other_cl": {"other current liabilities"},
    "total_liabilities": {"total liabilities"},
    "equity": {"owner's equity", "equity", "total equity"},
    "total_le": {"total liabilities & equity", "total liabilities and equity"},
}
AR_COLS = {"customer": {"customer", "cust", "client"}, "total": {"total due", "total", "balance"}}
SALES_COLS = {
    "month": {"month", "mo", "period"},
    "product": {"product", "sku name", "item"},
    "units": {"units sold", "units", "qty"},
    "price": {"avg price", "avg unit price", "unit price", "price"},
}


def canon(label, table: dict) -> str | None:
    s = re.sub(r"\s+", " ", str(label or "").strip().lower())
    return next((k for k, names in table.items() if s in names), None)


def to_number(x) -> float | None:
    """'(1,234)' -> -1234.0, '$12.50' -> 12.5, blanks and dashes -> None."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x) if math.isfinite(x) else None
    s = str(x).strip().replace("$", "").replace(",", "").replace(" ", "")
    if s in ("", "-", "n/a", "N/A", "NA"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()"))
    except ValueError:
        return None
    if not math.isfinite(v):  # "nan" and "inf" parse as floats but are not figures
        return None
    return -v if neg else v


def parse_month(x) -> str | None:
    if isinstance(x, (datetime, date)):
        return f"{x.year}-{x.month:02d}"
    s = str(x).strip()
    for fmt in ("%b-%y", "%Y-%m", "%b %Y", "%b-%Y"):
        try:
            d = datetime.strptime(s, fmt)
            return f"{d.year}-{d.month:02d}"
        except ValueError:
            pass
    return None


def month_range(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:])
    out = []
    while f"{y}-{m:02d}" <= last:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def detect_scale(title: str) -> int:
    return 1000 if re.search(r"in thousands|\$000|\(000", title, re.I) else 1
