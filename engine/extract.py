"""Pull figures out of each file. Every figure gets a source; gaps become flagged None."""

from __future__ import annotations

import re

from .model import Issue, Ledger
from .normalize import AR_COLS, BS, COST_ITEMS, PNL, SALES_COLS, canon, detect_scale, month_range, parse_month, to_number
from .read import Sheet


def _month_table(ledger: Ledger, sh: Sheet, prefix: str) -> None:
    """A sheet with line items down the side and months across the top."""
    scale = detect_scale(" ".join(str(c) for c in sh.rows[0] if c))
    hdr = next((i for i, r in enumerate(sh.rows) if sum(parse_month(c) is not None for c in r[1:]) >= 2), None)
    if hdr is None:
        ledger.issues.append(Issue("bad_schema", sh.file, f"'{sh.name}' has no row of month headers; its figures were not read"))
        return
    cols = {c: m for c, v in enumerate(sh.rows[hdr]) if c > 0 and (m := parse_month(v))}
    months = month_range(min(cols.values()), max(cols.values()))
    ledger.meta[f"{prefix}_months"] = months
    items = []
    for r in range(hdr + 1, len(sh.rows)):
        row = sh.rows[r]
        item = canon(row[0], PNL) if row else None
        if not item:
            continue
        items.append(item)
        for c, m in cols.items():
            v = to_number(row[c]) if c < len(row) else None
            key = f"{prefix}.{item}.{m}"
            if v is None:
                ledger.flag(key, "missing_value", f"blank cell {sh.src(r, c).split(' | ')[-1]} in '{sh.name}'", sh.src(r, c))
            else:
                v = v * scale
                ledger.put(key, abs(v) if item in COST_ITEMS else v, sh.src(r, c))
    for item in items:
        for m in sorted(set(months) - set(cols.values())):
            ledger.flag(f"{prefix}.{item}.{m}", "missing_period", f"the {m} column is absent from '{sh.name}'", sh.src())


def need_columns(ledger: Ledger, sh: Sheet, cols: dict, needed: list[str]) -> bool:
    """False, with an issue, when a file lacks a column the reader needs. The file is then skipped, not guessed at."""
    missing = [n for n in needed if n not in cols]
    if missing:
        ledger.issues.append(Issue("bad_schema", sh.file, f"{sh.file} is missing column(s) {', '.join(missing)}; the file was not read"))
    return not missing


def pnl(ledger: Ledger, sh: Sheet) -> None:
    _month_table(ledger, sh, "pnl_detail" if "detail" in sh.name.lower() else "pnl")


def balance(ledger: Ledger, sh: Sheet) -> None:
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(sh.rows[0][1])) if sh.rows and len(sh.rows[0]) > 1 else None
    ledger.meta["bs_date"] = m.group(0) if m else None
    for r, row in enumerate(sh.rows[1:], 1):
        item = canon(row[0], BS)
        v = to_number(row[1]) if len(row) > 1 else None
        if item and v is not None:
            ledger.put(f"bs.{item}", v, sh.src(r, 1))
        elif item:
            ledger.flag(f"bs.{item}", "missing_value", f"blank amount in {sh.src(r, 1)}", sh.src(r, 1))


def ar_aging(ledger: Ledger, sh: Sheet) -> None:
    cols = {canon(h, AR_COLS): c for c, h in enumerate(sh.rows[0])} if sh.rows else {}
    if not need_columns(ledger, sh, cols, ["total"]):
        return
    rows = []
    for r, row in enumerate(sh.rows[1:], 1):
        key = "ar.total" if str(row[0]).strip().lower() == "total" else f"ar.row.{r}"
        v = to_number(row[cols["total"]]) if cols["total"] < len(row) else None
        if v is None:
            ledger.flag(key, "missing_value", f"blank or unreadable amount in {sh.src(r, cols['total'])}", sh.src(r, cols["total"]))
        else:
            ledger.put(key, v, sh.src(r, cols["total"]))
        if key != "ar.total":
            rows.append(key)
    ledger.meta["ar_rows"] = rows


def sales(ledger: Ledger, sh: Sheet) -> None:
    cols = {canon(h, SALES_COLS): c for c, h in enumerate(sh.rows[0])} if sh.rows else {}
    if not need_columns(ledger, sh, cols, ["month", "product", "units", "price"]):
        return
    months, products = set(), []
    for r, row in enumerate(sh.rows[1:], 1):
        m, p = parse_month(row[cols["month"]]), str(row[cols["product"]]).strip()
        if m is None or not p:
            ledger.issues.append(Issue("bad_row", sh.src(r), f"row {r + 1} of {sh.file} has no readable month or product; it was skipped"))
            continue
        months.add(m)
        if p not in products:
            products.append(p)
        for what in ("units", "price"):
            v = to_number(row[cols[what]])
            key = f"sales.{what}.{p}.{m}"
            if v is None:
                ledger.flag(key, "missing_value", f"blank {what} in {sh.src(r, cols[what])}", sh.src(r, cols[what]))
            else:
                ledger.put(key, v, sh.src(r, cols[what]))
    if not months:
        ledger.issues.append(Issue("empty_file", sh.file, f"{sh.file} has no sales rows, so nothing was read from it"))
        return
    ledger.meta["sales_months"] = month_range(min(months), max(months))
    ledger.meta["products"] = products


BANK_LABELS = {
    "opening balance": "opening",
    "total deposits": "deposits",
    "total withdrawals": "withdrawals",
    "ending balance": "ending",
    "line of credit outstanding": "loc",
}


def bank(ledger: Ledger, sh: Sheet) -> None:
    for r, (line,) in enumerate(sh.rows):
        m = re.match(r"(.+?):\s*\$?\s*([\d,]+\.?\d*)\s*$", line)
        if m and m.group(1).strip().lower() in BANK_LABELS:
            key, v = f"bank.{BANK_LABELS[m.group(1).strip().lower()]}", to_number(m.group(2))
            if v is None:
                ledger.flag(key, "missing_value", f"unreadable amount on {sh.src(r)}", sh.src(r))
            else:
                ledger.put(key, v, sh.src(r))
        p = re.search(r"period:\s*(\d{4})-(\d{2})-\d{2}\s+to\s+(\d{4})-(\d{2})-\d{2}", line, re.I)
        if p:
            y1, m1, y2, m2 = map(int, p.groups())
            ledger.put("bank.months", (y2 - y1) * 12 + m2 - m1 + 1, sh.src(r))
    for key in [*BANK_LABELS.values(), "months"]:
        if f"bank.{key}" not in ledger.figs:
            ledger.flag(f"bank.{key}", "missing_value", f"'{key}' not found on {sh.name}", sh.src())


PLAIN = {
    "pnl": "profit and loss",
    "balance": "balance sheet",
    "ar_aging": "accounts receivable aging",
    "sales": "sales by product",
    "bank": "bank statement",
}
LABELS = {
    "pnl": "Monthly P&L",
    "balance": "Balance sheet",
    "ar_aging": "Customer aging report",
    "sales": "Sales by product",
    "bank": "Bank statement",
}
KINDS = {"xlsx": "Excel", "xls": "Excel", "csv": "CSV", "pdf": "PDF"}


def file_label(name: str) -> str:
    """A file in plain words and its type, such as 'Monthly P&L (Excel)'. Which file is which comes from the same name rule the readers use."""
    prefix = next((p for p in HANDLERS if name.lower().startswith(p)), None)
    kind = KINDS.get(name.rsplit(".", 1)[-1].lower())
    return f"{LABELS[prefix]} ({kind})" if prefix and kind else name


HANDLERS = {"pnl": pnl, "balance": balance, "ar_aging": ar_aging, "sales": sales, "bank": bank}


def extract_all(sheets: list[Sheet]) -> Ledger:
    ledger = Ledger()
    for sh in sheets:
        if sh.error:
            ledger.issues.append(Issue("unreadable_file", sh.file, f"{sh.file} could not be read ({sh.error}); skipped"))
            continue
        handler = next((h for p, h in HANDLERS.items() if sh.file.lower().startswith(p)), None)
        if handler:
            before = (len(ledger.figs), len(ledger.issues))
            try:
                handler(ledger, sh)
                if before == (len(ledger.figs), len(ledger.issues)):  # read without error, yet it gave no figure and no issue
                    ledger.issues.append(Issue("empty_file", sh.file, f"{sh.file} has no readable figures, so nothing was read from it"))
            except (KeyError, IndexError, ValueError, AttributeError, TypeError) as e:
                ledger.issues.append(Issue("unreadable_file", sh.file, f"{sh.file} could not be read ({type(e).__name__}); skipped"))
        else:
            ledger.issues.append(Issue("unrecognized_file", sh.file, f"no reader for {sh.file}; ignored"))
    for prefix in HANDLERS:  # one issue per expected input that was not provided at all
        if not any(sh.file.lower().startswith(prefix) for sh in sheets):
            ledger.issues.append(
                Issue("missing_input", prefix, f"No {PLAIN[prefix]} file was provided, so the analyses that need it are not computed")
            )
    return ledger
