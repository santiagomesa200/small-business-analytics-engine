"""AI license and access reconciler: the same read -> normalize -> flag-not-guess -> verify pattern, pointed at seats.

Inputs (data/licenses): seats_*.csv per tool, hr_roster.xlsx, access_approvals.csv, and usage_log.csv (optional).
Rules kept from the main engine: a seat that cannot be matched to a person is listed for investigation, never matched
by guesswork, and never counted in savings. Missing usage is "usage unknown", not "unused". Savings only come from
seats with a known cost.

Flow: reconcile() reads and matches the files, draft() writes the summary from a template, verify() checks it,
blocks() lays out the report, run() writes report.md, report.html and actions.csv.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .model import Issue
from .normalize import canon, to_number
from .plain import COMPANY
from .read import Sheet, read_folder
from .verify import Verdict, citations, coverage_problems, scan, show

IDLE_DAYS = 30  # a seat is unused when its last activity is at least this many days before the assessment date
COLS = {
    "seats": {
        "email": {"seat email", "email", "user"},
        "tool": {"tool"},
        "plan": {"plan"},
        "cost": {"monthly cost", "cost", "price"},
        "assigned": {"assigned date", "assigned"},
    },
    "roster": {
        "id": {"employee id", "id"},
        "name": {"name"},
        "email": {"email"},
        "dept": {"department", "dept"},
        "status": {"status"},
        "term": {"termination date", "terminated"},
    },
    "usage": {"email": {"email"}, "tool": {"tool"}, "last": {"last active"}, "sessions": {"sessions (30d)", "sessions"}},
    "approvals": {"email": {"email"}, "tool": {"tool"}, "by": {"approved by"}, "date": {"approved date"}},
}
REQUIRED = {"seats": ["email", "tool"], "roster": ["email", "status"], "usage": ["email", "tool", "last"], "approvals": ["email", "tool"]}
PLAIN_INPUT = {"seats_": "seat export", "hr_roster": "HR roster", "access_approvals": "approvals list"}
ACTION = {
    "terminated_holder": "reclaim",
    "duplicate_seat": "reclaim",
    "unused_seat": "confirm with manager",
    "no_approval": "request approval",
    "usage_unknown": "investigate",
    "unresolvable": "investigate",
}
TITLES = {
    "terminated_holder": "Seats held by employees who have left",
    "unused_seat": "Seats with no use for 30+ days",
    "duplicate_seat": "Duplicate seats",
    "no_approval": "Access with no approval on file",
    "usage_unknown": "Seats with no usable usage data",
    "unresolvable": "Seats that match no employee",
}
OWNER = {"reclaim": "IT admin", "confirm with manager": "Department manager", "request approval": "Approver", "investigate": "IT admin"}
ORDER = ["terminated_holder", "duplicate_seat", "unused_seat", "no_approval", "usage_unknown", "unresolvable"]
SAVING = ["terminated_holder", "duplicate_seat", "unused_seat"]  # the only groups that can be counted in savings


@dataclass
class Finding:
    category: str
    email: str  # as typed in the seat file
    tool: str
    plan: str
    cost: float | None
    detail: str
    sources: list[str]  # file | sheet | cell for every file that proves it
    action: str = ""
    counted: bool = False  # in savings?


@dataclass
class Result:
    asof: date | None  # None when the data does not say; unused seats then cannot be told apart
    findings: list[Finding] = field(default_factory=list)
    seats: int = 0
    people: int = 0
    monthly: float = 0.0
    issues: list[Issue] = field(default_factory=list)  # data conflicts found while reading; nothing was guessed

    @property
    def annual(self) -> float:
        return self.monthly * 12

    def of(self, cat: str) -> list[Finding]:
        return [f for f in self.findings if f.category == cat]

    def saved(self, cat: str) -> float:
        return sum(f.cost or 0.0 for f in self.of(cat) if f.counted)

    def figures(self, cid: str) -> list[tuple[str | None, float]]:
        """Every (unit, value) a sentence citing `cid` may state. Counts have no unit; money is '$'."""
        if cid == "savings":
            return [("$", self.monthly), ("$", self.annual), (None, sum(f.counted for f in self.findings))]
        return [
            (None, len(self.of(cid))),
            ("$", self.saved(cid)),
            ("$", self.saved(cid) * 12),
            (None, sum(f.cost is None for f in self.of(cid))),
        ]


def norm_email(x) -> str:
    return str(x or "").strip().lower()


def to_date(x) -> date | None:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(x).strip(), fmt).date()
        except ValueError:
            pass
    return None


def table(sh: Sheet, kind: str, issues: list[Issue]):
    """(row index, {field: value}, sheet) for each data row. A sheet with no usable header is logged and yields nothing."""
    found = next(
        (
            (h, {i: canon(c, COLS[kind]) for i, c in enumerate(header)})
            for h, header in enumerate(sh.rows)
            if all(n in [canon(c, COLS[kind]) for c in header] for n in REQUIRED[kind])
        ),
        None,
    )
    if found is None:
        issues.append(Issue("bad_schema", sh.file, f"{sh.file}: no header row with column(s) {', '.join(REQUIRED[kind])}; skipped"))
        return
    h, cols = found
    for i, row in enumerate(sh.rows[h + 1 :], start=h + 1):
        if any(c not in (None, "") for c in row):  # a short row leaves its missing required fields empty
            fields: dict = dict.fromkeys(REQUIRED[kind], "")
            fields.update({cols[j]: v for j, v in enumerate(row) if cols.get(j)})
            yield i, fields, sh


def find_asof(sheets: list[Sheet], roster: list[dict]) -> date | None:
    """The assessment date: the 'as of' date in the HR roster title, else the latest date anywhere in the data."""
    for sh in sheets:
        if sh.file.startswith("hr_roster") and sh.rows:
            m = re.search(r"\d{4}-\d{2}-\d{2}", " ".join(str(c) for c in sh.rows[0] if c))
            if m:
                return date.fromisoformat(m.group(0))
    dates = [d for r in roster for d in (to_date(r.get("term")),) if d]
    return max(dates) if dates else None


def agreed(rows: list, key, kind: str, issues: list[Issue]) -> dict:
    """key -> (row, source) for each key whose rows all say the same. Rows that disagree are logged and the key is left out,
    so the seat falls back to 'unresolvable' or 'usage unknown' instead of one row silently winning."""
    groups: dict = {}
    for i, r, sh in rows:
        groups.setdefault(key(r), []).append((r, sh.src(i)))
    out = {}
    for k, g in groups.items():
        same = {tuple(sorted((f, norm_email(v)) for f, v in r.items())) for r, _ in g}
        if len(same) == 1:
            out[k] = g[0]
        else:
            name = k if isinstance(k, str) else " / ".join(k)
            issues.append(
                Issue(f"conflicting_{kind}", name, f"{kind} rows for {name} disagree ({'; '.join(s for _, s in g)}); none was used")
            )
    return out


def reconcile(folder: str | Path, asof: date | None = None) -> Result:
    all_sheets = read_folder(folder)
    issues: list[Issue] = []
    for prefix in ("seats_", "hr_roster", "access_approvals"):
        if not any(s.file.startswith(prefix) for s in all_sheets):
            issues.append(Issue("missing_input", prefix, f"No {PLAIN_INPUT[prefix]} was provided, so it could not be used"))
    for s in all_sheets:
        if s.error:
            issues.append(Issue("unreadable_file", s.file, f"{s.file} could not be read ({s.error}); skipped"))
    sheets = [s for s in all_sheets if not s.error]
    files = lambda prefix: [s for s in sheets if s.file.startswith(prefix)]
    roster_rows = [(i, r, sh) for s in files("hr_roster") for i, r, sh in table(s, "roster", issues)]
    roster = agreed(roster_rows, lambda r: norm_email(r["email"]), "roster", issues)
    usage_rows = [(i, r, sh) for s in files("usage_log") for i, r, sh in table(s, "usage", issues)]
    usage = agreed(usage_rows, lambda r: (norm_email(r["email"]), r["tool"]), "usage", issues)
    approved = {(norm_email(r["email"]), r["tool"]) for s in files("access_approvals") for _, r, _ in table(s, "approvals", issues)}
    asof = asof or find_asof(sheets, [r for _, r, _ in roster_rows])
    if asof is None:
        issues.append(
            Issue(
                "no_asof", "asof", "no assessment date in the roster title and no dates to infer it from; unused seats are not told apart"
            )
        )
    res = Result(asof, people=len({norm_email(r["email"]) for _, r, _ in roster_rows}), issues=issues)
    seen: dict[tuple, str] = {}  # (email, tool) -> source of the first seat, to find duplicates
    seats = [(i, r, sh) for s in files("seats_") for i, r, sh in table(s, "seats", issues)]
    res.seats = len(seats)
    for i, r, sh in sorted(seats, key=lambda t: to_date(t[1].get("assigned")) or date.max):
        key = (norm_email(r["email"]), r["tool"])
        cost = to_number(r.get("cost"))

        def found(cat, detail, *extra, r=r, i=i, sh=sh, cost=cost):
            res.findings.append(Finding(cat, str(r["email"]).strip(), r["tool"], r.get("plan", ""), cost, detail, [sh.src(i), *extra]))

        person = roster.get(key[0])
        if person is None:  # never guess who it might be
            why = "has conflicting rows in the HR roster" if key[0] in {i.key for i in issues} else "is not in the HR roster"
            found("unresolvable", f"this email {why}; no match was assumed")
            continue
        who, who_src = person
        left = str(who["status"]).strip().lower() == "terminated"
        if left:
            found("terminated_holder", f"{who.get('name')} left on {to_date(who.get('term'))}", who_src)
        if key in seen:
            found("duplicate_seat", f"{who.get('name')} already holds a {r['tool']} seat", seen[key])
        seen.setdefault(key, sh.src(i))
        if left:
            continue
        u = usage.get(key)
        last = to_date(u[0].get("last")) if u else None
        if asof is None or u is None or last is None or last > asof:  # no record, unreadable date or a date in the future: we cannot tell
            found("usage_unknown", "no usable usage record for this seat" + (f" ({u[1]})" if u else ""))
        elif (asof - last).days >= IDLE_DAYS:
            found("unused_seat", f"last active {last}, {(asof - last).days} days before {asof}", u[1])
        if key not in approved:
            found("no_approval", f"{who.get('name')} has this seat but no approval is on file")
    off = not_computed(res)  # a group whose input is missing is not computed: it gets no findings, not zero findings
    res.findings = [f for f in res.findings if f.category not in off]
    for f in res.findings:
        f.action = ACTION[f.category]
    counted: set[str] = set()  # savings: each seat once, in priority order, only with a known cost
    for cat in SAVING:
        for f in res.of(cat):
            if f.cost is not None and f.sources[0] not in counted:
                f.counted = True
                counted.add(f.sources[0])
    res.monthly = sum(f.cost or 0.0 for f in res.findings if f.counted)
    return res


def not_computed(res: Result) -> dict[str, str]:
    """Group (or 'savings') -> why it cannot be stated, when an input is missing or unreadable. Empty on a complete run."""
    bad = lambda prefix: any(i.key.startswith(prefix) for i in res.issues if i.kind in ("missing_input", "unreadable_file", "bad_schema"))
    base = "no seat file could be read" if res.seats == 0 else "the HR roster has no readable rows" if res.people == 0 else ""
    approvals = base or ("the approvals file is missing or unreadable" if bad("access_approvals") else "")
    out = {c: base for c in [*ORDER, "savings"]}  # without seats or a roster nothing can be matched, so no group is true or false
    out["no_approval"] = approvals
    return {c: why for c, why in out.items() if why}


def money(x: float) -> str:
    return f"${x:,.0f}"


def draft(res: Result) -> str:
    """The summary is always written by this template. Only the main engine can call a model.
    A group whose input is missing is said to be not computed; it is never reported as zero."""
    n = lambda c: len(res.of(c))
    one = lambda k, a, b: a if k == 1 else b  # singular or plural, to agree with the count k
    off = not_computed(res)
    skip = lambda c, what: f"{what} is not computed because {off[c]} [{c}]"
    nocost = sum(f.cost is None for f in res.of("unused_seat"))
    nu = n("usage_unknown")
    unknown = (
        f", and {nu} more {one(nu, 'has', 'have')} no usable usage data and {one(nu, 'is', 'are')} not counted [usage_unknown]"
        if nu
        else ""
    )
    who = "it" if nocost == n("unused_seat") == 1 else f"{nocost} of them"
    nc = f"; {who} {one(nocost, 'has', 'have')} no cost on file and {one(nocost, 'is', 'are')} not counted" if nocost else ""
    t, u, dup, na, un = n("terminated_holder"), n("unused_seat"), n("duplicate_seat"), n("no_approval"), n("unresolvable")
    first = (
        skip("terminated_holder", "The count of seats held by employees who have left")
        if "terminated_holder" in off
        else f"{t} {one(t, 'seat is held by an employee who has', 'seats are held by employees who have')} left; "
        f"reclaiming {one(t, 'it', 'them')} frees {money(res.saved('terminated_holder'))} a month [terminated_holder]"
    )
    second = (
        skip("unused_seat", "The count of unused seats")
        if "unused_seat" in off
        else f"{u} {one(u, 'seat has', 'seats have')} not been used for a month or more, and {money(res.saved('unused_seat'))} a month is recoverable "
        f"if the {one(u, 'manager agrees', 'managers agree')}{nc} [unused_seat]{unknown}"
    )
    third = (
        skip("duplicate_seat", "The count of second seats")
        if "duplicate_seat" in off
        else f"{dup} {one(dup, 'person holds a second seat', 'seats are second seats')} for the same tool, worth {money(res.saved('duplicate_seat'))} a month [duplicate_seat]"
    )
    approval = (
        skip("no_approval", "The count of people with no approval on file")
        if "no_approval" in off
        else f"{na} {one(na, 'person has', 'people have')} access with no approval on file, so approval should be requested [no_approval]"
    )
    unmatched = (
        skip("unresolvable", "the count of seats that match no employee")
        if "unresolvable" in off
        else f"{un} {one(un, 'seat matches', 'seats match')} no employee, so {one(un, 'it is', 'they are')} listed for investigation and not counted [unresolvable]"
    )
    total = (
        skip("savings", "The saving")
        if "savings" in off
        else f"Reclaiming every counted seat would save {money(res.monthly)} a month, or {money(res.annual)} a year [savings]"
    )
    return f"{first}. {second}. {third}. {approval}, and {unmatched}. {total}."


def verify(summary: str, res: Result) -> Verdict:
    """Same pattern as engine/verify.py: 5 sentences, none repeated, each group cited exactly once, each sentence cites a
    finding group, and every number must be a figure of a cited group with the same unit (money is '$', counts have none)."""
    problems = []
    sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
    if len(sentences) != 5:
        problems.append(f"expected 5 sentences, found {len(sentences)}")
    expected = [c for c in ORDER if c != "usage_unknown" or res.of(c)] + ["savings"]  # usage_unknown is only said when it exists
    problems += coverage_problems(sentences, expected)
    for s in sentences:
        cited = citations(s)
        short = s[:60] + "..."
        if not cited or any(c not in TITLES and c != "savings" for c in cited):
            problems.append(f"sentence does not cite a real finding group: '{short}'")
            continue
        allowed = [x for c in cited for x in res.figures(c)]
        for value, dec, unit in scan(s):
            if not any(u == unit and round(v, dec) == round(value, dec) for u, v in allowed):
                problems.append(f"number {show(value, dec, unit)} is not a figure of {', '.join(cited)}: '{short}'")
    return Verdict(not problems, problems)


def safe_cell(v):
    """Spreadsheets run a cell that starts with = + - @ as a formula; a leading quote makes it plain text."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def write_actions(path: Path, res: Result) -> None:
    rows = sorted(res.findings, key=lambda f: ORDER.index(f.category))
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "priority",
                "action",
                "owner",
                "seat_email",
                "tool",
                "plan",
                "monthly_cost",
                "counted_in_savings",
                "reason",
                "evidence",
                "done",
            ]
        )
        for n, f in enumerate(rows, 1):
            w.writerow(
                [
                    safe_cell(v)
                    for v in [
                        n,
                        f.action,
                        OWNER[f.action],
                        f.email,
                        f.tool,
                        f.plan,
                        "" if f.cost is None else f"{f.cost:.2f}",
                        "yes" if f.counted else "no",
                        f.detail,
                        "; ".join(f.sources),
                        "",
                    ]
                ]
            )


def blocks(res: Result, summary: str, verdict: Verdict) -> list:
    flagged = len({f.sources[0] for f in res.findings})
    off = not_computed(res)
    problems = [("h2", f"Data problems ({len(res.issues)})"), ("ul", [i.message for i in res.issues])] if res.issues else []
    b = [
        ("h1", f"{COMPANY} – AI license and access report"),
        (
            "p",
            f"Synthetic data, assessed as of {res.asof or 'an unknown date'}. Seats are matched to people by normalized email; a seat that matches nobody is listed, with no match assumed.",
        ),
        (
            "strip",
            [
                (str(res.seats), "seats read"),
                ("not computed" if all(c in off for c in ORDER) else str(flagged), "flagged"),
                ("not computed" if "savings" in off else money(res.monthly), "a month if reclaimed"),
                ("PASS" if verdict.ok else "FAIL", "verifier"),
            ],
        ),
        *problems,  # what could not be read comes before anything computed from it
        ("h2", "Executive summary"),
    ]
    b += (
        [("summary", summary), ("small", "Written by a template. Checked by a separate verifier before it appears here.")]
        if verdict.ok
        else [("p", "Summary blocked: the verifier rejected the draft."), ("ul", verdict.problems)]
    )
    if "savings" in off:
        b.append(("h2", "Savings not computed"))
        b.append(("p", f"No saving is stated because {off['savings']}."))
    else:
        b.append(("h2", f"Savings if reclaimed: {money(res.monthly)} a month, {money(res.annual)} a year"))
        b.append(
            (
                "table",
                [
                    (TITLES[c], f"{money(res.saved(c))} a month", f"{sum(f.counted for f in res.of(c))} of {len(res.of(c))} seats counted")
                    for c in SAVING
                ],
            )
        )
        b.append(
            ("small", "Not counted: seats with no cost on file, seats with no usable usage data, and every seat that matches no employee.")
        )
    for c in ORDER:
        fs = res.of(c)
        if not fs and c == "usage_unknown":
            continue
        if c in off:
            b += [("h2", f"{TITLES[c]} (not computed)"), ("p", f"Not computed because {off[c]}.")]
            continue
        b.append(("h2", f"{TITLES[c]} ({len(fs)})"))
        b.append(
            (
                "table",
                [
                    (
                        f"{f.email} ({f.tool})",
                        f"{f.action}" + (f", {money(f.cost or 0)} a month" if f.counted else ", not counted"),
                        f"{f.detail}. Source: {'; '.join(f.sources)}",
                    )
                    for f in fs
                ]
                or [("None", "", "")],
            )
        )
    return b


def run(folder: str | Path, out_dir: str | Path = "outputs/licenses", asof: date | None = None) -> dict:
    from . import report

    res = reconcile(folder, asof)
    summary = draft(res)
    verdict = verify(summary, res)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bl = blocks(res, summary, verdict)
    (out / "report.md").write_text(report.to_md(bl))
    (out / "report.html").write_text(report.to_html(bl, fonts=report.fonts_rel(out)))
    write_actions(out / "actions.csv", res)
    return dict(result=res, summary=summary, verdict=verdict)
