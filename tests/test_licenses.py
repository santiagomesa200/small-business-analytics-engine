import csv
import re
import shutil
from datetime import date

import pytest
from openpyxl import load_workbook

import run as run_cli
from engine import licenses as lic
from scripts.make_license_data import make

# planted by scripts/make_license_data.py
LEAVERS, UNUSED, UNAPPROVED, ACTIONS = 6, 10, 3, 21


@pytest.fixture(scope="module")
def res(tmp_path_factory):
    d = tmp_path_factory.mktemp("lic")
    make(d)
    return lic.reconcile(d)


def test_terminated_holders_are_caught(res):
    found = res.of("terminated_holder")
    assert len(found) == LEAVERS and all("left on" in f.detail and f.action == "reclaim" for f in found)


def test_unresolvable_email_is_flagged_not_guessed(res):
    (f,) = res.of("unresolvable")
    assert f.email.lower() == "rob.chen@example.com" and f.action == "investigate" and not f.counted
    assert "bob.chen" not in f.detail  # the nickname lookalike is not offered as a match


def test_duplicate_seat_found_despite_different_casing(res):
    (f,) = res.of("duplicate_seat")
    assert f.email.isupper() and f.action == "reclaim" and f.counted


def test_unused_and_unapproved_counts(res):
    assert len(res.of("unused_seat")) == UNUSED and len(res.of("no_approval")) == UNAPPROVED


def test_savings_exclude_ambiguous_seats(res):
    counted = [f for f in res.findings if f.counted]
    assert all(f.cost is not None and f.category != "unresolvable" for f in counted)
    assert len({f.sources[0] for f in counted}) == len(counted)  # each seat counted once
    assert res.monthly == sum(f.cost for f in counted)
    assert any(f.cost is None for f in res.of("unused_seat"))  # the seat with no cost is listed...
    assert not any(f.cost is None for f in counted)  # ...but not counted


def test_verifier_passes_template_and_rejects_wrong_savings(res):
    good = lic.draft(res)
    assert lic.verify(good, res).ok
    bad = good.replace(f"${res.monthly:,.0f} a month, or", "$900 a month, or")
    v = lic.verify(bad, res)
    assert not v.ok and any("900" in p for p in v.problems)


def test_run_writes_actions_csv(tmp_path):
    make(tmp_path / "in")
    lic.run(tmp_path / "in", tmp_path / "out")
    rows = (tmp_path / "out" / "actions.csv").read_text().splitlines()
    assert len(rows) == 1 + ACTIONS and (tmp_path / "out" / "report.html").exists()


def test_deleting_the_usage_log_does_not_raise_savings(lic_dir, tmp_path):
    base = lic.reconcile(lic_dir)
    shutil.copytree(lic_dir, tmp_path / "x")
    (tmp_path / "x" / "usage_log.csv").unlink()
    res = lic.reconcile(tmp_path / "x")
    assert not res.of("unused_seat") and res.of("usage_unknown")
    assert res.monthly <= base.monthly and all(not f.counted for f in res.of("usage_unknown"))
    assert lic.verify(lic.draft(res), res).ok


def test_unreadable_last_active_date_is_unknown_not_unused(lic_dir, tmp_path):
    shutil.copytree(lic_dir, tmp_path / "x")
    f = tmp_path / "x" / "usage_log.csv"
    victim = lic.reconcile(lic_dir).of("unused_seat")[0].email.lower()
    rows = list(csv.reader(f.open()))
    for row in rows[1:]:
        if row[0].lower() == victim:
            row[2] = "n/a"
    csv.writer(f.open("w", newline="")).writerows(rows)
    res = lic.reconcile(tmp_path / "x")
    assert any(x.email.lower() == victim for x in res.of("usage_unknown"))


def test_assessment_date_comes_from_the_data_and_can_be_passed(lic_dir):
    assert not hasattr(lic, "ASOF")
    assert lic.reconcile(lic_dir).asof == date(2025, 6, 30)  # the roster title
    earlier = lic.reconcile(lic_dir, asof=date(2025, 6, 1))
    assert len(earlier.of("unused_seat")) < len(lic.reconcile(lic_dir).of("unused_seat"))


def test_actions_csv_neutralizes_formulas(tmp_path):
    f = lic.Finding("unresolvable", '=HYPERLINK("http://x")', "T", "P", None, "-1+1", ["a | b | A1"], "investigate")
    r = lic.Result(date(2025, 6, 30), findings=[f])
    lic.write_actions(tmp_path / "a.csv", r)
    cells = [c for row in csv.reader((tmp_path / "a.csv").open()) for c in row]
    assert '\'=HYPERLINK("http://x")' in cells and "'-1+1" in cells and not any(c[:1] in "=+-@" and c for c in cells[11:])


def test_synthetic_emails_use_a_reserved_domain(lic_dir):
    text = " ".join(p.read_text() for p in lic_dir.glob("*.csv"))
    wb = load_workbook(lic_dir / "hr_roster.xlsx")
    text += " ".join(str(c) for row in wb.active.iter_rows(values_only=True) for c in row if c)
    domains = {w.split("@")[1].lower().strip(",.") for w in text.replace(",", " ").split() if "@" in w}
    assert domains == {"example.com"}


def test_conflicting_roster_and_usage_rows_are_flagged_not_overwritten(lic_dir, tmp_path):
    d = tmp_path / "x"
    shutil.copytree(lic_dir, d)
    base = lic.reconcile(d)
    holder = next(f for f in base.of("unused_seat") if f.counted)
    wb = load_workbook(d / "hr_roster.xlsx")
    ws = wb.active
    row = next(r for r in ws.iter_rows(min_row=4, values_only=True) if str(r[2]).lower() == holder.email.lower())
    ws.append([row[0], row[1], row[2], row[3], "Terminated", date(2025, 6, 1)])  # same person, now a leaver
    wb.save(d / "hr_roster.xlsx")
    with open(d / "usage_log.csv", "a", newline="") as fh:
        csv.writer(fh).writerow([row[2], holder.tool, "2025-06-29", 3])  # second usage row, different date
    res = lic.reconcile(d)
    assert {i.kind for i in res.issues} == {"conflicting_roster", "conflicting_usage"}
    assert not any(f.counted for f in res.findings if f.email.lower() == holder.email.lower())


def test_license_verifier_rejects_a_repeated_sentence_and_a_missing_group(lic_dir):
    res = lic.reconcile(lic_dir)
    s = lic.draft(res).split(". ")
    assert lic.verify(". ".join(s), res).ok
    v = lic.verify(". ".join([*s[:2], s[0], *s[3:]]), res)
    assert not v.ok and "a sentence is repeated" in v.problems
    assert any("cited 0 times" in p for p in v.problems)


def test_license_summary_agrees_with_the_count():
    f = lambda cat, cost=30.0: lic.Finding(cat, "a@example.com", "T", "P", cost, "d", ["s"], lic.ACTION[cat], cost is not None)
    cats = ["terminated_holder", "unused_seat", "duplicate_seat", "no_approval", "unresolvable"]
    one = lic.Result(date(2025, 6, 30), [f(c, None if c == "unused_seat" else 30.0) for c in cats], seats=5, people=5)
    many = lic.Result(date(2025, 6, 30), [f(c, None if c == "unused_seat" else 30.0) for c in cats for _ in range(2)], seats=10, people=5)
    t1, t2 = lic.draft(one), lic.draft(many)
    for want in (
        "1 seat is held by an employee who has left",
        "it has no cost on file and is not counted",
        "1 person has access",
        "1 seat matches no employee",
    ):
        assert want in t1
    for want in (
        "2 seats are held by employees who have left",
        "2 of them have no cost",
        "2 people have access",
        "2 seats match no employee",
    ):
        assert want in t2
    assert lic.verify(t1, one).ok and lic.verify(t2, many).ok and not re.search(r"\b1 seats\b|\b1 people\b", t1)


def test_license_mode_logs_bad_inputs_and_finishes(lic_dir, tmp_path):
    d = tmp_path / "x"
    shutil.copytree(lic_dir, d)
    (d / "hr_roster.xlsx").write_bytes(b"not a zip")  # corrupt
    (d / "access_approvals.csv").unlink()  # missing
    (d / "seats_chatpilot.csv").write_text("a,b\n1,2\n")  # no usable header
    out = lic.run(d, tmp_path / "out")
    kinds = {i.kind for i in out["result"].issues}
    assert {"unreadable_file", "missing_input", "bad_schema"} <= kinds
    assert out["verdict"].ok and (tmp_path / "out" / "report.md").exists()
    assert "Data problems" in (tmp_path / "out" / "report.md").read_text()


def test_license_summary_does_not_report_zero_when_an_input_is_missing(lic_dir, tmp_path):
    def without(name):
        d = tmp_path / name
        shutil.copytree(lic_dir, d)
        (d / name).unlink()
        return lic.run(d, tmp_path / ("out-" + name))

    out = without("access_approvals.csv")
    assert (
        out["verdict"].ok
        and "The count of people with no approval on file is not computed because the approvals file is missing" in out["summary"]
    )
    assert "0 people" not in out["summary"] and "$522" in out["summary"]  # the rest is still stated
    out = without("hr_roster.xlsx")
    text = out["summary"]
    assert out["verdict"].ok and "is not computed because the HR roster has no readable rows" in text
    assert "0 seats are held" not in text and "$0" not in text and "0 people" not in text
    md = (tmp_path / "out-hr_roster.xlsx" / "report.md").read_text()
    assert md.index("Data problems") < md.index("Executive summary") and "Savings not computed" in md


def test_each_single_missing_license_input_is_not_computed_everywhere(lic_dir, tmp_path, capsys):
    def without(name, cat):
        d = tmp_path / name
        shutil.copytree(lic_dir, d)
        (d / name).unlink()
        run_cli.licenses(str(d), str(tmp_path / ("out-" + name)))
        cli = capsys.readouterr().out
        rows = list(csv.DictReader(open(tmp_path / ("out-" + name) / "actions.csv")))
        md = (tmp_path / ("out-" + name) / "report.md").read_text()
        assert f"- {cat:<18} not computed" in cli
        assert f"{lic.TITLES[cat]} (not computed)" in md and f"{lic.TITLES[cat]} (0)" not in md
        return rows, md

    rows, md = without("access_approvals.csv", "no_approval")
    assert not any("no approval is on file" in r["reason"] for r in rows) and "83 flagged" not in md and "flagged: 83" not in md
    assert any(r["action"] == "reclaim" for r in rows)  # the groups that can be computed are still listed
    rows, md = without("hr_roster.xlsx", "terminated_holder")
    assert rows == [] and "None" not in md and "flagged: 83" not in md
