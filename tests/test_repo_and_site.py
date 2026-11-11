"""The committed outputs, site and copy match what a fresh run produces and say only what is true."""

import re
import shutil
import zipfile
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
    assert row["figure"] == "sales.csv" and "could not be read" in row["reason"]


def test_check_notices_a_drifted_browser_bundle(tmp_path):
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    shutil.copytree(ROOT / "docs", tmp_path / "docs", ignore=shutil.ignore_patterns("fonts", "*.png"))
    assert make_site.bundle_problems(tmp_path / "docs/engine-bundle.zip") == []
    with zipfile.ZipFile(tmp_path / "docs/engine-bundle.zip", "w") as z:
        z.writestr("engine/pipeline.py", "# edited")
    problems = make_site.bundle_problems(tmp_path / "docs/engine-bundle.zip")
    assert any("engine/pipeline.py" in p for p in problems) and any("data/sample" in p for p in problems)


def test_browser_bundle_holds_the_real_engine_and_committed_figures():
    files = make_site.bundle_files()
    assert files["engine/pipeline.py"] == (ROOT / "engine/pipeline.py").read_bytes()
    assert files["outputs/sample/figures.csv"] == (ROOT / "outputs/sample/figures.csv").read_bytes()
    assert "engine/gate.py" not in files and "data/clean/pnl_2025_h1.xlsx" in files


def test_page_loads_one_pinned_external_script_and_says_what_it_does():
    page = (ROOT / "docs/index.html").read_text()
    assert re.findall(r"https://cdn\.jsdelivr\.net/[^'\" ]*", page) == ["https://cdn.jsdelivr.net/pyodide/v"]
    assert re.search(r"V='\d+\.\d+\.\d+'", page) and "V='314.0.7'" in page
    assert "<script src=" not in page and "Nothing is uploaded" in page and "Drafted by: " in page


def test_no_founder_or_departure_wording():
    banned = ("co-found", "founder", "was there from", "handed off", "left stepup")
    for name in ("README.md", "docs/case-study.md", "docs/index.html"):
        text = (ROOT / name).read_text().lower()
        assert not [b for b in banned if b in text], name


def test_check_notices_a_missing_or_wrong_wheel(tmp_path):
    shutil.copytree(ROOT / "docs/wheels", tmp_path / "docs/wheels")
    assert make_site.wheel_problems(tmp_path) == []
    (tmp_path / "docs/wheels/pypdf-7.0.0-py3-none-any.whl").rename(tmp_path / "docs/wheels/pypdf-6.0.0-py3-none-any.whl")
    (tmp_path / "docs/wheels/et_xmlfile-2.0.0-py3-none-any.whl").unlink()
    problems = make_site.wheel_problems(tmp_path)
    assert any("pypdf" in p for p in problems) and any("et_xmlfile" in p for p in problems) and len(problems) == 2


def test_run_it_live_drives_the_diagram_with_the_shared_data_builder():
    page = (ROOT / "docs/index.html").read_text()
    assert page.count(">Run it live<") == 1 and "Show raw output" in page and 'id="run-it"' not in page and "<iframe" not in page
    assert "from engine import sitedata" in page and "sitedata.one(" in page
    assert "engine/sitedata.py" in make_site.bundle_files()
    assert make_site.one("data/sample")["figures"] == make_site.build_data()[0]["scenarios"]["messy"]["figures"]


def _page() -> str:
    return (ROOT / "docs/index.html").read_text().split("<!--SITE-DATA-->")[0]


def test_sheets_are_numbered_one_to_six_and_the_engineers_sheet_is_gone():
    page = _page()
    assert re.findall(r'<section class="sheet" id="(sheet-\d)"', page) == [f"sheet-{i}" for i in range(1, 7)]
    assert [int(n) for n in re.findall(r"<b class=\"sheetno\">(\d) of 6</b>", page)] == [1, 2, 3, 4, 5, 6]
    assert "of 7" not in page and "sheet-7" not in page and "For engineers: the stack" not in page and "eng-trace" not in page
    index = page.split('aria-label="Drawing index"')[1].split("</nav>")[0]
    assert len(re.findall(r'<span class="sn">', index)) == 6 and index.count("General notes") == 1


def test_license_reconciler_is_tagged_built_for_iem_in_the_index():
    index = _page().split('aria-label="Drawing index"')[1].split("</nav>")[0]
    assert re.search(r'<a href="#sheet-5">AI license and access reconciler <span class="chip tag on">Built for IEM</span></a>', index)


def test_how_to_strip_sits_above_the_company_switch_and_the_old_sentence_is_gone():
    page = _page()
    strip = page.split('<ol class="howto"')[1].split("</ol>")[0]
    assert re.findall(r"<span>([^<]+)</span></li>", strip) == [
        "Press Run it live.",
        "Click any stage to see what it did.",
        "Switch to the clean company to compare.",
    ]
    assert page.index('class="howto"') < page.index('id="switch"') < page.index('id="run-live"')
    assert "select any numbered stage" not in page and "Switch the company, then" not in page


def test_every_pressable_stage_shows_it_opens_and_the_other_diagrams_do_not():
    page = _page()
    stages = re.findall(r'<g class="stage" data-stage="(\w+)"', page)
    assert len(stages) == 14 and sorted(set(stages)) == sorted(["read", "norm", "ext", "check", "ana", "ver", "rep"])
    assert page.count('class="tile"') == 14 and page.count('class="cue cue-o"') == 14 and page.count('class="cue cue-c"') == 14
    assert 'class="hit"' not in page and 'id="leader"' not in page
    assert page.count("Click any stage to see what it did.") == 1  # the how-to strip only
    licenses = page.split('id="lic-wrap"')[1].split("</svg>")[0]
    assert "tile" not in licenses and 'role="button"' not in licenses


def test_what_ran_panel_sits_between_the_diagram_and_the_legend_and_is_drawn_from_one_function():
    page = (ROOT / "docs/index.html").read_text()  # the whole file: the script after the data block is part of this check
    assert page.index('id="svg-v"') < page.index('id="ran"') < page.index('aria-label="Symbol legend"')
    panel = page.split('id="ran"')[1].split("</section>")[0]
    assert "What the engine did with these files" in panel and "Open the full report" in panel and "See what was held back" in panel
    assert page.count("function ranHTML(") == 1 and page.count("ranHTML(") == 2  # defined once, used once, for saved and live data alike
    assert "const D=()=>live&&live.co===co?live.data:DATA.scenarios[co]" in page
    assert "openStage(r.data.figures.flagged" not in page and "What the engine just did, in your browser" in page
    assert (
        page.index('id="callout"') < page.index('id="ran"') < page.index('class="lede ran-note"') < page.index('aria-label="Symbol legend"')
    )


def test_readme_carries_the_engineers_content_that_left_the_page():
    readme = (ROOT / "README.md").read_text()
    section = readme.split("## For engineers")[1].split("\n## ")[0]
    trace = make_site.one("data/sample")["trace"]
    assert "**Data model:**" in section and "**One figure, traced:**" in section and "**Stack:**" in section
    assert all(Path(t["file"]).name in section for t in trace)  # every stage file the real run names
    assert "168,519" in section and "159,519" in section and "Sheet 6" not in readme
    assert "Click any stage" in readme


def test_panel_names_files_and_analyses_in_plain_words_from_the_engine():
    from engine.extract import file_label

    d = make_site.one("data/sample")
    assert [x["label"] for x in d["file_labels"]] == [
        "Customer aging report (CSV)",
        "Balance sheet (CSV)",
        "Bank statement (PDF)",
        "Monthly P&L (Excel)",
        "Sales by product (CSV)",
    ]
    assert [x["file"] for x in d["file_labels"]] == d["files"] and file_label("notes.txt") == "notes.txt"
    names = [a["name"] for a in d["analyses"]]
    assert "Working capital" in names and "Valuation range" in names and not any("(" in n or "EBITDA" in n for n in names)
    page = (ROOT / "docs/index.html").read_text()
    assert "It read these '+d.read.files+' files.</p>" in page and "d.file_labels.map" in page and "e(a.name)" in page


def test_the_why_not_an_llm_note_left_the_hero_and_keeps_its_words():
    page = _page()
    assert page.count("Why not just give the files to an AI model?") == 1
    assert page.index('id="ran"') < page.index("Why not just give the files to an AI model?")
    assert "Client work needs every figure traced to its source and every gap flagged" in page


def test_sheet_five_shows_plain_findings_and_hides_where_they_came_from():
    page = (ROOT / "docs/index.html").read_text()
    sheet = page.split('id="sheet-5"')[1].split("<!-- SHEET 6 -->")[0]
    assert "Source cells" not in sheet and 'class="s"' not in sheet and "tag(L.summary)" not in page
    assert re.search(r'<details class="raw" id="lic-src"><summary>Show where each finding came from</summary>', sheet)
    assert "follows fixed rules, so it is code I can test" in sheet and "is deterministic" not in page


def test_general_notes_send_engineers_to_the_readme_instead_of_showing_commands():
    page = _page()
    notes = page.split('id="sheet-6"')[1]
    for gone in ("python -m engine.gate", "contract checks", "imputation", "Run it yourself", "make check"):
        assert gone not in notes, gone
    assert 'github.com/santiagomesa200/small-business-analytics-engine#readme">README</a> on GitHub' in notes


def test_live_tag_panel_rows_captions_and_stage_scroll_use_the_agreed_wording():
    page = (ROOT / "docs/index.html").read_text()
    assert "Ran live in your browser just now. '+(ok?'Same result as the saved run.':'Different from the saved run.')" in page
    assert "secs" not in page.split("async function runLive")[1]
    assert "'ver.l':v.numbers_checked+' CHECKED'" in page and "<dt>Figures</dt>" in page and "Pulled out" not in page
    assert "filter(x=>x[0]).map(x=>x[0]+' '+x[1])" in page and 'data-b="ana.leg1"' not in page
    assert "function bringIntoView(" in page and "async function rows()" in page
    assert "one write path" not in page and "an LLM" not in page


def test_check_details_group_held_figures_in_plain_text_and_the_bolt_returns_to_rest():
    page = (ROOT / "docs/index.html").read_text()
    flags = make_site.one("data/sample")["flags"]
    assert {f["where"] for f in flags if f["kind"] == "subtotal_mismatch"} == {"Monthly P&L, cell E6"}
    assert all("where" in f for f in flags)
    assert "function heldLine(" in page and "'Missing for '" in page and 'class="chip trip"' not in page
    assert "addEventListener('animationend'" in page and "<small>(" in page and ".ft .n{text-align:right;white-space:nowrap}" in page
