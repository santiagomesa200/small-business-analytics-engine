"""Five analyses. Each one refuses to run if any figure it needs is missing or flagged."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field

from .model import Ledger, NotComputed

MULTIPLES = (4.0, 5.0, 6.0)  # illustrative EBITDA multiples, not a market comparison


@dataclass
class Metric:
    label: str
    value: float | None
    unit: str  # $ days months % pp x
    reason: str | None = None  # set when value is None
    source: str = ""  # where the inputs came from: "file | sheet: cells"


@dataclass
class Result:
    id: str
    title: str
    metrics: list[Metric] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    blocked: str | None = None

    @property
    def status(self) -> str:
        done = [m for m in self.metrics if m.value is not None]
        if self.blocked or not done:
            return "blocked"
        return "computed" if len(done) == len(self.metrics) else "partial"

    @property
    def reason(self) -> str:
        return self.blocked or next((m.reason for m in self.metrics if m.reason), "")

    def get(self, label: str) -> Metric:
        return next(m for m in self.metrics if m.label == label)


def fmt(m: Metric) -> str:
    v, u = m.value, m.unit
    if v is None:
        raise ValueError(f"{m.label} has no value to format")
    if u == "$":
        return f"{'-' if v < 0 else ''}${abs(v):,.0f}"
    return {"days": f"{v:.1f} days", "months": f"{v:.1f} months", "%": f"{v:.1f}%", "pp": f"{v:+.1f} pp", "x": f"{v:.1f}x"}[u]


def _days(months: list[str]) -> int:
    return sum(calendar.monthrange(int(m[:4]), int(m[5:]))[1] for m in months)


def _metric(ledger: Ledger, label: str, unit: str, fn) -> Metric:
    """Run one calculation and remember which figures it touched."""
    before = set(ledger.used)
    ledger.used.clear()
    try:
        value, reason = fn(), None
    except NotComputed as e:
        value, reason = None, f"not computed: {e}"
    source = ledger.source_text(ledger.used)
    ledger.used.update(before)
    return Metric(label, value, unit, reason, source)


def gross_margin(ledger: Ledger) -> Result:
    months = ledger.need_meta("pnl_months")
    metrics = []
    for m in months:  # each month stands alone: a bad month is flagged, the good months still compute

        def one_month(m=m):
            v = ledger.get_all([f"pnl.revenue.{m}", f"pnl.gross_profit.{m}"])
            if v[f"pnl.revenue.{m}"] == 0:
                raise NotComputed(f"revenue for {m} is zero, so a margin is undefined")
            return v[f"pnl.gross_profit.{m}"] / v[f"pnl.revenue.{m}"] * 100

        metrics.append(_metric(ledger, f"Gross margin {m}", "%", one_month))
    margins = [x.value for x in metrics if x.value is not None]
    if len(margins) == len(metrics):
        metrics.append(Metric("Change, first to last month", margins[-1] - margins[0], "pp"))
    else:
        metrics.append(Metric("Change, first to last month", None, "pp", "not computed: at least one month is flagged"))
    return Result("gross_margin", TITLES["gross_margin"], metrics, ["Gross margin = gross profit / revenue, per month."])


def price_volume(ledger: Ledger) -> Result:
    ms, prods = ledger.need_meta("sales_months"), ledger.need_meta("products")
    v = ledger.get_all([f"sales.{w}.{p}.{m}" for p in prods for m in ms for w in ("units", "price")])
    base, cur = ms[: len(ms) // 2], ms[len(ms) // 2 :]

    def units(p, period):
        return sum(v[f"sales.units.{p}.{m}"] for m in period)

    def revenue(p, period):
        return sum(v[f"sales.units.{p}.{m}"] * v[f"sales.price.{p}.{m}"] for m in period)

    r0 = r1 = price_t = vol_t = 0.0
    per_product = []
    for p in prods:
        units_base, units_cur = units(p, base), units(p, cur)
        revenue_base, revenue_cur = revenue(p, base), revenue(p, cur)
        if units_base == 0 or units_cur == 0:
            raise NotComputed(f"{p} has zero units in one period, so its price effect is undefined")
        price_base, price_cur = revenue_base / units_base, revenue_cur / units_cur
        price_effect = (price_cur - price_base) * units_cur
        volume_effect = (units_cur - units_base) * price_base
        r0, r1 = r0 + revenue_base, r1 + revenue_cur
        price_t, vol_t = price_t + price_effect, vol_t + volume_effect
        per_product += [Metric(f"Price effect: {p}", price_effect, "$"), Metric(f"Volume effect: {p}", volume_effect, "$")]
    metrics = [
        Metric("Revenue, base period", r0, "$"),
        Metric("Revenue, current period", r1, "$"),
        Metric("Total change", r1 - r0, "$"),
        Metric("Price effect", price_t, "$"),
        Metric("Volume effect", vol_t, "$"),
    ] + per_product
    notes = [
        f"Base period {base[0]} to {base[-1]}; current period {cur[0]} to {cur[-1]}.",
        "Price effect = change in average price x current units. Volume effect = change in units x base price. "
        "Product mix shows up inside the volume effect.",
        "Revenue here is units x price from the sales file, not the P&L.",
    ]
    return Result("price_volume", TITLES["price_volume"], metrics, notes)


def working_capital(ledger: Ledger) -> Result:
    sm, pm = ledger.need_meta("sales_months"), ledger.need_meta("pnl_months")
    prods = ledger.need_meta("products")

    def dso():
        v = ledger.get_all(["bs.ar"] + [f"sales.{w}.{p}.{m}" for p in prods for m in sm for w in ("units", "price")])
        rev = sum(v[f"sales.units.{p}.{m}"] * v[f"sales.price.{p}.{m}"] for p in prods for m in sm)
        if rev == 0:
            raise NotComputed("sales revenue is zero, so DSO is undefined")
        return v["bs.ar"] / rev * _days(sm)

    def vs_cogs(key):
        def f():
            v = ledger.get_all([key] + [f"pnl.cogs.{m}" for m in pm])
            cogs = sum(v[f"pnl.cogs.{m}"] for m in pm)
            if cogs == 0:
                raise NotComputed("COGS is zero, so days of cost are undefined")
            return v[key] / cogs * _days(pm)

        return f

    dso_m, dpo_m, dio_m = (
        _metric(ledger, "DSO", "days", dso),
        _metric(ledger, "DPO", "days", vs_cogs("bs.ap")),
        _metric(ledger, "DIO", "days", vs_cogs("bs.inventory")),
    )
    parts = [dso_m, dpo_m, dio_m]
    if dso_m.value is not None and dpo_m.value is not None and dio_m.value is not None:
        ccc = Metric("Cash conversion cycle", dso_m.value + dio_m.value - dpo_m.value, "days")
    else:
        ccc = Metric("Cash conversion cycle", None, "days", "not computed: needs DSO, DPO and DIO")
    notes = [
        "DSO = receivables / revenue x days in the sales period. DPO = payables / COGS x days. "
        "DIO = inventory / COGS x days. Balance sheet figures are at period end.",
        "Cash conversion cycle = DSO + DIO - DPO.",
    ]
    return Result("working_capital", TITLES["working_capital"], [*parts, ccc], notes)


def cash_runway(ledger: Ledger) -> Result:
    v = ledger.get_all(["bank.opening", "bank.ending", "bank.months"])
    if v["bank.months"] <= 0:
        raise NotComputed("the statement period is not a positive number of months")
    burn = (v["bank.opening"] - v["bank.ending"]) / v["bank.months"]
    if burn <= 0:
        raise NotComputed("cash did not decline over the statement period, so runway is undefined")
    metrics = [
        Metric("Opening cash", v["bank.opening"], "$"),
        Metric("Ending cash", v["bank.ending"], "$"),
        Metric("Average monthly net burn", burn, "$"),
        Metric("Runway", v["bank.ending"] / burn, "months"),
    ]
    return Result(
        "cash_runway",
        TITLES["cash_runway"],
        metrics,
        ["Burn = (opening - ending cash) / months in the statement. It is assumed to continue unchanged."],
    )


def valuation(ledger: Ledger) -> Result:
    months = ledger.need_meta("pnl_months")
    v = ledger.get_all([f"pnl.ebitda.{m}" for m in months] + ["bs.cash", "bank.loc"])
    annual = sum(v[f"pnl.ebitda.{m}"] for m in months) * 12 / len(months)
    if annual <= 0:
        raise NotComputed("EBITDA is not positive, so a multiple-based range is not meaningful")
    net_debt = v["bank.loc"] - v["bs.cash"]
    lo, mid, hi = (annual * x - net_debt for x in MULTIPLES)
    metrics = [
        Metric("Annualized EBITDA", annual, "$"),
        Metric("Multiple (low)", MULTIPLES[0], "x"),
        Metric("Multiple (high)", MULTIPLES[2], "x"),
        Metric("Net debt", net_debt, "$"),
        Metric("Equity value (low)", lo, "$"),
        Metric("Equity value (mid)", mid, "$"),
        Metric("Equity value (high)", hi, "$"),
    ]
    notes = [
        f"EBITDA multiples of {MULTIPLES[0]}x, {MULTIPLES[1]}x and {MULTIPLES[2]}x are illustrative assumptions, not market comparables.",
        f"Annualized EBITDA = the {len(months)} months in the P&L scaled to 12 months. Seasonality is not adjusted.",
        "Net debt = line of credit (bank statement PDF) minus cash (balance sheet). Equity = multiple x EBITDA - net debt.",
    ]
    return Result("valuation", TITLES["valuation"], metrics, notes)


TITLES = {
    "gross_margin": "Gross margin trend",
    "price_volume": "Price vs volume effect on revenue",
    "working_capital": "Working capital (DSO, DPO, DIO)",
    "cash_runway": "Cash runway",
    "valuation": "Valuation range from an EBITDA multiple",
}
ANALYSES = [gross_margin, price_volume, working_capital, cash_runway, valuation]


def run_analyses(ledger: Ledger) -> list[Result]:
    out = []
    for fn in ANALYSES:
        ledger.used.clear()
        try:
            r = fn(ledger)
        except NotComputed as e:
            r = Result(fn.__name__, TITLES[fn.__name__], blocked=f"not computed: {e}")
        default_source = ledger.source_text(ledger.used)
        for m in r.metrics:
            m.source = m.source or default_source
        out.append(r)
    return out
