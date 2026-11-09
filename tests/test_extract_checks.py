from engine.checks import check_all
from engine.model import Ledger

SAMPLE_FIGURES = 95  # the five synthetic files, as the README run log reports


def test_every_figure_has_provenance(sample):
    assert len(sample.figs) == SAMPLE_FIGURES
    assert all(f.source for f in sample.figs.values())
    assert "pnl_2025_h1.xlsx | Monthly P&L | B4" == sample.figs["pnl.revenue.2025-01"].source


def test_units_and_signs_are_normalized(sample):
    assert sample.value("pnl_detail.opex.2025-01") == 136200.0  # file said 136.2 in thousands
    assert sample.value("pnl.cogs.2025-01") > 0  # file said (…) in parentheses
    assert sample.value("bs.cash") == 412300.0  # file said "412,300"
    assert sample.value("sales.price.Conduit Kit.2025-04") == 44.5  # file said "$44.50"


def test_pdf_only_figure_is_extracted_with_page_source(sample):
    assert sample.value("bank.loc") == 150000.0
    assert sample.figs["bank.loc"].source.startswith("bank_statement_summary.pdf | page 1")
    assert not any(k.startswith("bs.loc") for k in sample.figs)


def test_missing_month_is_flagged_not_filled(sample):
    f = sample.figs["pnl.revenue.2025-04"]
    assert f.value is None and "2025-04" in f.reason
    assert sample.value("pnl.revenue.2025-05") is not None


def test_bad_subtotal_is_nulled_and_original_kept(sample):
    f = sample.figs["pnl.gross_profit.2025-05"]
    assert f.value is None and f.reported is not None and "parts give" in f.reason


def test_clean_data_raises_no_flags(clean):
    assert clean.issues == []


def test_balance_sheet_imbalance_is_caught(clean):
    clean.figs["bs.equity"].value += 500  # liabilities + equity now exceeds assets
    clean.figs["bs.total_le"].value += 500
    check_all(clean)
    assert any(i.kind == "balance_sheet_imbalance" for i in clean.issues)


def test_cross_file_disagreement_is_caught(clean):
    clean.figs["pnl_detail.opex.2025-02"].value += 1000
    check_all(clean)
    kinds = {(i.kind, i.key) for i in clean.issues}
    assert ("cross_file_mismatch", "pnl.opex.2025-02") in kinds
    assert ("cross_file_mismatch", "pnl_detail.opex.2025-02") in kinds


def test_flag_never_overwrites_with_an_estimate():
    ledger = Ledger()
    ledger.put("x", 10.0, "f | s | A1")
    ledger.flag("x", "subtotal_mismatch", "bad")
    ledger.flag("x", "subtotal_mismatch", "bad again")
    assert ledger.value("x") is None and len(ledger.issues) == 1
