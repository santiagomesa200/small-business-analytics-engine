import re

from conftest import results_by_id

from engine.pipeline import run
from engine.summarize import template
from engine.verify import verify


def good(ledger):
    res = list(results_by_id(ledger).values())
    return res, template(res)


def test_template_summary_passes(sample, clean):
    for ledger in (sample, clean):
        res, text = good(ledger)
        assert verify(text, res).ok, verify(text, res).problems


def test_fabricated_number_is_caught(sample):
    res, text = good(sample)
    bad = text.replace("$57,900", "$61,000")
    v = verify(bad, res)
    assert not v.ok and any("61,000" in p for p in v.problems)


def test_flagged_analysis_stated_as_fact_is_caught(sample):
    res, text = good(sample)
    bad = re.sub(r"The valuation range[^\[]*\[valuation\]", "The business is worth $2,000,000 [valuation]", text)
    v = verify(bad, res)
    assert not v.ok and any("blocked analysis 'valuation'" in p for p in v.problems)


def test_blocked_metric_stated_without_hedge_is_caught(sample):
    res, text = good(sample)
    bad = text.replace(
        "supplier payment days, inventory days and the cash conversion cycle are not computed because April's figures are missing",
        "DPO looks healthy",
    )
    assert bad != text
    v = verify(bad, res)
    assert not v.ok and any("flagged metric 'DPO'" in p for p in v.problems)


def test_runway_value_swapped_for_dso_value_is_rejected(sample):
    res, text = good(sample)
    bad = text.replace("7.1 months of runway", "44.8 days of runway")  # 44.8 is real, but it belongs to working_capital
    v = verify(bad, res)
    assert not v.ok and any("number 44.8 days" in p and "cash_runway" in p for p in v.problems)


def test_missing_citation_is_caught(sample):
    res, text = good(sample)
    v = verify(text.replace("[cash_runway]", ""), res)
    assert not v.ok and any("no valid analysis citation" in p for p in v.problems)


def test_wrong_sentence_count_is_caught(sample):
    res, text = good(sample)
    v = verify(text + " Everything looks fine [cash_runway].", res)
    assert not v.ok and any("expected 5 sentences, found 6" in p for p in v.problems)


def test_pipeline_writes_report_with_attention_box(sample_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = run(sample_dir, tmp_path)
    md, html = (tmp_path / "report.md").read_text(), (tmp_path / "report.html").read_text()
    assert out["verdict"].ok and "Needs attention (2 items)" in md and "need attention: 2" in md
    assert "Fix: send the April column" in md and "pnl.gross_profit.2025-05" in html and (tmp_path / "figures.csv").exists()


def test_markdown_table_rows_keep_every_cell(sample_dir, tmp_path, monkeypatch):
    """The Source column holds 'file | sheet: cells'. A raw pipe there adds a cell and GitHub drops the sheet and cells."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run(sample_dir, tmp_path)
    md = (tmp_path / "report.md").read_text()
    rows = [ln for ln in md.splitlines() if ln.startswith("|")]
    assert rows and {len(re.split(r"(?<!\\)\|", ln)) for ln in rows} == {5}  # 3 cells between the outer pipes
    assert "| pnl_2025_h1.xlsx \\| Monthly P&L: B6, B4 |" in md
    assert "analyses fully computed: 2 of 5 (2 partial, 1 blocked)" in md and "verifier: PASS" in md


def test_failed_verification_blocks_the_summary(sample_dir, tmp_path, monkeypatch):
    import engine.pipeline as pl

    bad = "Profit is $9,999,999 [cash_runway]. One. Two. Three. Four."
    monkeypatch.setattr(pl, "draft", lambda res, offline=False: (bad, "test"))
    out = run(sample_dir, tmp_path)
    md = (tmp_path / "report.md").read_text()
    assert not out["verdict"].ok and "Summary blocked" in md and bad not in md


def test_committed_ai_draft_gets_its_committed_verdict(sample):
    """docs/ai-draft-example/ holds a real Claude draft and the verdict it got. Re-run the verifier so they cannot drift."""
    from pathlib import Path

    folder = Path(__file__).resolve().parent.parent / "docs/ai-draft-example"
    v = verify((folder / "draft.txt").read_text().strip(), list(results_by_id(sample).values()))
    text = "Verifier result: " + ("PASS" if v.ok else "FAIL - summary blocked") + "\n" + "".join(f"- {p}\n" for p in v.problems)
    assert text == (folder / "verdict.txt").read_text()
