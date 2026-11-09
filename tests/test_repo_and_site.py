"""The committed outputs, site and copy match what a fresh run produces and say only what is true."""

import shutil
from pathlib import Path

from engine.model import Issue, Ledger
from scripts import make_site

ROOT = Path(__file__).resolve().parent.parent


def test_check_notices_a_changed_committed_csv(tmp_path):
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    shutil.copytree(ROOT / "docs", tmp_path / "docs", ignore=shutil.ignore_patterns("fonts", "*.png"))
    shutil.copytree(ROOT / "outputs", tmp_path / "outputs")
    f = tmp_path / "outputs" / "clean" / "figures.csv"
    f.write_text(f.read_text().replace("359700", "359701", 1))
    assert any("outputs/clean/figures.csv" in p for p in make_site.check(tmp_path))


def test_requirements_are_pinned_and_check_target_exists():
    lines = [x for x in (ROOT / "requirements.txt").read_text().splitlines() if x.strip() and not x.startswith("#")]
    assert lines and all("==" in x for x in lines)
    assert "check:" in (ROOT / "Makefile").read_text()


def test_trace_follows_one_real_figure():
    steps = make_site.one(str(ROOT / "data/sample"))["trace"]
    assert [s["stage"] for s in steps] == ["READ", "NORMALIZE", "EXTRACT", "CHECK", "ANALYZE", "DRAFT", "VERIFY", "REPORT"]
    text = " ".join(s["text"] for s in steps)
    assert "E6" in text and "168,519" in text and "159,519" in text and "Verdict: PASS" in text


def test_copy_is_exact():
    page = (ROOT / "docs/index.html").read_text().split("<!--SITE-DATA-->")[0]
    assert "written by a template, not a model" in page and "AI only drafts" not in page
    for name in ("README.md", "docs/case-study.md"):
        assert "self-reported from my own project records" in (ROOT / name).read_text()
    assert page.lower().count("independent verifier") == 1 and page.count("never guessed") == 0


def test_site_flag_rows_accept_issues_keyed_by_filename():
    ledger = Ledger()
    ledger.issues.append(Issue("unreadable_file", "sales.csv", "sales.csv could not be read (ValueError); skipped"))
    (row,) = make_site.flag_rows(ledger, [])
    assert row["key"] == "sales.csv" and "could not be read" in row["reason"]
