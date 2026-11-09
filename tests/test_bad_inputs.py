"""Bad or missing input files are logged and flagged, never a crash or a silent gap."""

import csv
import re
import shutil

import pytest

import run as run_cli
from engine import pipeline
from engine.analyses import gross_margin
from engine.checks import check_all
from engine.extract import extract_all
from engine.model import Ledger, NotComputed
from engine.read import read_folder


def edit_clean(clean_dir, tmp_path, fn):
    d = tmp_path / "in"
    shutil.copytree(clean_dir, d)
    fn(d)
    return d


def build_ledger(d):
    ledger = extract_all(read_folder(d))
    check_all(ledger)
    return ledger


def test_blank_ar_figure_gets_a_reason_and_an_issue(clean_dir, tmp_path):
    def blank(d):
        f = d / "ar_aging_2025-06-30.csv"
        rows = list(csv.reader(f.open()))
        rows[2][-1] = ""
        csv.writer(f.open("w", newline="")).writerows(rows)

    ledger = build_ledger(edit_clean(clean_dir, tmp_path, blank))
    assert all(f.reason for f in ledger.figs.values() if f.value is None) and any(f.value is None for f in ledger.figs.values())
    assert any(i.kind == "missing_value" and i.key.startswith("ar.") for i in ledger.issues)


def test_empty_sales_file_is_flagged_not_a_crash(clean_dir, tmp_path):
    def empty(d):
        f = d / "sales_by_product.csv"
        f.write_text(f.read_text().splitlines()[0] + "\n")

    d = edit_clean(clean_dir, tmp_path, empty)
    out = pipeline.run(d, tmp_path / "out", offline=True)
    assert any(i.kind == "empty_file" for i in out["ledger"].issues)
    assert {r.id: r.status for r in out["results"]}["price_volume"] == "blocked"


def test_sales_file_missing_a_column_is_flagged(clean_dir, tmp_path):
    def drop(d):
        f = d / "sales_by_product.csv"
        rows = [r[:-1] for r in csv.reader(f.open())]  # drops the last column
        csv.writer(f.open("w", newline="")).writerows(rows)

    ledger = build_ledger(edit_clean(clean_dir, tmp_path, drop))
    assert any(i.kind == "bad_schema" for i in ledger.issues)


def test_zero_revenue_is_not_computed_not_a_crash():
    ledger = Ledger()
    ledger.meta["pnl_months"] = ["2025-01"]
    ledger.put("pnl.revenue.2025-01", 0.0, "x | y | B1")
    ledger.put("pnl.gross_profit.2025-01", 0.0, "x | y | B2")
    m = gross_margin(ledger).metrics[0]
    assert m.value is None and "zero" in m.reason


def test_duplicate_figure_is_flagged_not_overwritten():
    ledger = Ledger()
    ledger.put("pnl.revenue.2025-01", 100.0, "a | s | B1")
    ledger.put("pnl.revenue.2025-01", 999.0, "a | s | B9")
    assert ledger.value("pnl.revenue.2025-01") is None and any(i.kind == "duplicate_figure" for i in ledger.issues)
    with pytest.raises(NotComputed):
        ledger.get("pnl.revenue.2025-01")


def test_corrupt_files_of_every_type_are_logged_and_skipped(clean_dir, tmp_path):
    junk = {"pnl_2025_h1.xlsx": b"not a zip", "bank_statement_summary.pdf": b"not a pdf", "sales_by_product.csv": b"\xff\xfe\x00bad\xff"}
    d = tmp_path / "in"
    shutil.copytree(clean_dir, d)
    for name, data in junk.items():
        (d / name).write_bytes(data)
    out = pipeline.run(d, tmp_path / "out", offline=True)
    bad = {i.key for i in out["ledger"].issues if i.kind == "unreadable_file"}
    assert bad == set(junk) and (tmp_path / "out" / "report.md").exists()


def test_missing_expected_inputs_each_get_an_issue_and_the_report_does_not_say_nothing_flagged(clean_dir, tmp_path):
    d = tmp_path / "in"
    shutil.copytree(clean_dir, d)
    (d / "sales_by_product.csv").unlink()
    (d / "bank_statement_summary.pdf").unlink()
    out = pipeline.run(d, tmp_path / "out", offline=True)
    assert sorted(i.key for i in out["ledger"].issues if i.kind == "missing_input") == ["bank", "sales"]
    assert "Nothing flagged." not in (tmp_path / "out" / "report.md").read_text()


def test_run_without_a_mode_value_is_a_usage_error_not_a_traceback(capsys):
    with pytest.raises(SystemExit) as e:
        run_cli.cli(["--mode"])
    assert e.value.code == 2 and "usage" in capsys.readouterr().err.lower()


def test_empty_balance_sheet_file_is_logged_and_the_report_says_so(clean_dir, tmp_path):
    d = edit_clean(clean_dir, tmp_path, lambda d: (d / "balance_sheet_2025-06-30.csv").write_text(""))
    out = pipeline.run(d, tmp_path / "out", offline=True)
    assert [i.key for i in out["ledger"].issues if i.kind == "empty_file"] == ["balance_sheet_2025-06-30.csv"]
    md = (tmp_path / "out" / "report.md").read_text()
    assert "balance_sheet_2025-06-30.csv" in md and "Fix: send a file with data in it" in md


def test_missing_input_message_uses_plain_names(clean_dir, tmp_path):
    d = edit_clean(clean_dir, tmp_path, lambda d: (d / "pnl_2025_h1.xlsx").unlink())
    ledger = build_ledger(d)
    assert next(i.message for i in ledger.issues if i.kind == "missing_input").startswith("No profit and loss file was provided")


def test_a_missing_input_folder_is_a_usage_error_not_a_traceback(capsys, tmp_path):
    for argv in (["nope"], ["nope", "--mode", "licenses"]):
        with pytest.raises(SystemExit) as e:
            run_cli.cli([str(tmp_path / argv[0]), *argv[1:]])
        assert e.value.code == 2 and "not a folder" in capsys.readouterr().err


def test_the_report_gives_file_level_problems_file_level_advice(clean_dir, tmp_path):
    def break_inputs(d):
        (d / "balance_sheet_2025-06-30.csv").write_text("")
        (d / "sales_by_product.csv").write_text("a,b\n1,2\n")
        (d / "pnl_2025_h1.xlsx").write_bytes(b"not a zip")

    pipeline.run(edit_clean(clean_dir, tmp_path, break_inputs), tmp_path / "out", offline=True)
    md = (tmp_path / "out" / "report.md").read_text()
    n = len(re.findall(r"^- .*Fix: ", md, re.M))
    assert f"Needs attention ({n} items)" in md and f"need attention: {n}" in md
    attn = md.split("## Needs attention")[1].split("\n## ")[0]
    assert "confirm the right figure" not in attn and "balance_sheet_2025-06-30.csv has no readable" in attn  # file advice, real file name
    assert "send the file again" in md and "send a file with data in it" in md and "check the file has these columns" in md


def test_blocked_analysis_from_a_missing_file_says_the_file_is_missing(tmp_path):
    (tmp_path / "in").mkdir()
    out = pipeline.run(tmp_path / "in", tmp_path / "out", offline=True)
    assert "an input file is missing or could not be read" in out["summary"] and "send the missing file" in out["summary"]
    assert "confirm the right figure" not in out["summary"]


def test_attention_items_start_with_a_capital_and_a_pdf_is_not_told_to_become_xlsx(clean_dir, tmp_path):
    d = edit_clean(clean_dir, tmp_path, lambda d: (d / "bank_statement_summary.pdf").write_bytes(b"not a pdf"))
    (d / "sales_by_product.csv").unlink()
    pipeline.run(d, tmp_path / "out", offline=True)
    md = (tmp_path / "out" / "report.md").read_text()
    assert "- No sales by product file was provided" in md
    pdf_item = next(line for line in md.splitlines() if "bank_statement_summary.pdf" in line and "Fix:" in line)
    assert "Fix: send the file again." in pdf_item and ".xlsx" not in pdf_item
