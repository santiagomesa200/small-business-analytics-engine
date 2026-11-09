"""Consistency checks. A failed check turns the figure into None; it is never corrected."""

from __future__ import annotations

from .model import Ledger

TOL = 1.0  # dollars; the sample files round to whole dollars


def _sum_check(ledger: Ledger, total: str, parts: list[tuple[str, int]], kind: str, label: str) -> None:
    t, found = ledger.value(total), [ledger.value(k) for k, _ in parts]
    vals = [v for v in found if v is not None]
    if t is None or len(vals) != len(parts):
        return
    expected = sum(s * v for (_, s), v in zip(parts, vals, strict=True))
    if abs(t - expected) > TOL:
        ledger.flag(total, kind, f"{label}: file says {t:,.0f} but its parts give {expected:,.0f}")


def _pair(ledger: Ledger, a: str, b: str, kind: str, label: str, extra: tuple[str, ...] = ()) -> None:
    x, y = ledger.value(a), ledger.value(b)
    if x is None or y is None or abs(x - y) <= TOL:
        return
    for k in (a, b, *extra):  # we cannot know which side is right, so neither is trusted
        ledger.flag(k, kind, f"{label}: {a} is {x:,.0f} but {b} is {y:,.0f}")


def check_all(ledger: Ledger) -> None:
    for m in ledger.meta.get("pnl_months", []):
        rev, cogs, opex = (f"pnl.{i}.{m}" for i in ("revenue", "cogs", "opex"))
        _sum_check(ledger, f"pnl.gross_profit.{m}", [(rev, 1), (cogs, -1)], "subtotal_mismatch", f"Gross profit {m}")
        _sum_check(ledger, f"pnl.ebitda.{m}", [(rev, 1), (cogs, -1), (opex, -1)], "subtotal_mismatch", f"EBITDA {m}")
        _pair(ledger, opex, f"pnl_detail.opex.{m}", "cross_file_mismatch", f"Opex {m}")
        pnl_rev = ledger.value(rev)
        if m in ledger.meta.get("sales_months", []) and pnl_rev is not None:
            keys = [f"sales.{w}.{p}.{m}" for p in ledger.meta["products"] for w in ("units", "price")]
            vals = [v for v in (ledger.value(k) for k in keys) if v is not None]
            if len(vals) == len(keys):  # keys alternate units, price, units, price, ...
                sales_rev = sum(u * p for u, p in zip(vals[0::2], vals[1::2], strict=True))
                if abs(sales_rev - pnl_rev) > TOL:
                    for k in (rev, *keys):
                        ledger.flag(k, "cross_file_mismatch", f"Revenue {m}: P&L says {pnl_rev:,.0f}, sales file gives {sales_rev:,.0f}")
    bs = [
        ("bs.current_assets", ["bs.cash", "bs.ar", "bs.inventory"]),
        ("bs.total_assets", ["bs.current_assets", "bs.fixed_assets"]),
        ("bs.total_liabilities", ["bs.ap", "bs.other_cl"]),
        ("bs.total_le", ["bs.total_liabilities", "bs.equity"]),
    ]
    for total, parts in bs:
        _sum_check(ledger, total, [(p, 1) for p in parts], "subtotal_mismatch", "Balance sheet")
    _pair(ledger, "bs.total_assets", "bs.total_le", "balance_sheet_imbalance", "Balance sheet does not balance")
    _sum_check(ledger, "ar.total", [(k, 1) for k in ledger.meta.get("ar_rows", [])], "subtotal_mismatch", "AR aging")
    _pair(ledger, "bs.ar", "ar.total", "cross_file_mismatch", "Receivables")
    _sum_check(
        ledger, "bank.ending", [("bank.opening", 1), ("bank.deposits", 1), ("bank.withdrawals", -1)], "subtotal_mismatch", "Bank statement"
    )
    _pair(ledger, "bs.cash", "bank.ending", "cross_file_mismatch", "Cash")
