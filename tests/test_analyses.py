import pytest
from conftest import results_by_id

from engine.model import NotComputed


def test_margin_computes_clean_months_and_flags_only_bad_ones(sample):
    r = results_by_id(sample)["gross_margin"]
    assert r.status == "partial"
    assert r.get("Gross margin 2025-01").value is not None and r.get("Gross margin 2025-06").value is not None
    assert r.get("Gross margin 2025-04").value is None and "pnl.revenue.2025-04" in r.get("Gross margin 2025-04").reason
    assert "pnl.gross_profit.2025-05" in r.get("Gross margin 2025-05").reason
    assert r.get("Change, first to last month").value is None


def test_valuation_refuses_on_missing_ebitda(sample):
    assert results_by_id(sample)["valuation"].status == "blocked"


def test_price_and_volume_add_up_to_total_change(sample):
    r = results_by_id(sample)["price_volume"]
    assert r.status == "computed"
    total = r.get("Total change").value
    assert r.get("Price effect").value + r.get("Volume effect").value == pytest.approx(total)
    assert total == pytest.approx(r.get("Revenue, current period").value - r.get("Revenue, base period").value)


def test_working_capital_is_partial_where_data_is_missing(sample):
    r = results_by_id(sample)["working_capital"]
    assert r.status == "partial"
    assert r.get("DSO").value == pytest.approx(561400 / 2267025 * 181, rel=1e-6)
    assert r.get("DPO").value is None and "pnl.cogs.2025-04" in r.get("DPO").reason


def test_runway_uses_the_pdf_only_opening_balance(sample):
    r = results_by_id(sample)["cash_runway"]
    assert r.get("Average monthly net burn").value == pytest.approx((586000 - 412300) / 3)
    assert r.get("Runway").value == pytest.approx(412300 / 57900)


def test_all_five_compute_on_clean_data(clean):
    res = results_by_id(clean)
    assert len(res) == 5 and {k: v.status for k, v in res.items()} == dict.fromkeys(res, "computed")
    v = res["valuation"]
    assert v.get("Equity value (low)").value < v.get("Equity value (high)").value


def test_one_flagged_input_blocks_only_what_depends_on_it(clean):
    clean.flag("bs.ap", "manual", "test flag")
    res = results_by_id(clean)
    assert res["working_capital"].get("DPO").value is None
    assert res["working_capital"].get("DSO").value is not None
    assert res["cash_runway"].status == "computed"


def test_runway_refuses_when_cash_did_not_decline(clean):
    clean.figs["bank.opening"].value = 100.0
    assert "did not decline" in results_by_id(clean)["cash_runway"].reason


def test_need_meta_raises_when_a_file_is_absent():
    from engine.model import Ledger

    with pytest.raises(NotComputed):
        Ledger().need_meta("sales_months")
