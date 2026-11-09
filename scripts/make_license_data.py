"""Write deterministic, synthetic inputs for the AI license and access reconciler: data/licenses/.

Company: the fictional Bluebonnet Supply Co., ~120 employees, three fictional AI tools. Planted on purpose:
  6 seats held by terminated employees        10 seats with no use for 30+ days (one has no cost on file)
  3 people with a seat but no approval        1 seat whose email matches nobody (rob.chen, not bob.chen)
  1 duplicate seat for one person (typed in a different case)
Also messy on purpose: email casing differs between files, one employee goes by a nickname, dates use two formats.
"""

from __future__ import annotations

import csv
import random
import re
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

ASOF = date(2025, 6, 30)
FIRST = [
    "Maya",
    "Luis",
    "Ana",
    "Jordan",
    "Priya",
    "Marcus",
    "Elena",
    "Tom",
    "Grace",
    "Omar",
    "Rosa",
    "Sam",
    "Carla",
    "Dev",
    "Hannah",
    "Victor",
    "Lena",
    "Ravi",
    "Isla",
    "Diego",
    "Tara",
    "Kofi",
    "June",
    "Mateo",
]
LAST = ["Ortiz", "Nguyen", "Patel", "Brooks", "Silva", "Kim", "Hughes", "Reyes", "Foster", "Okafor"]
DEPTS = ["Sales", "Operations", "Finance", "Warehouse", "Customer Service", "IT"]
TOOLS = {"ChatPilot": ("Team", 30), "CodeAssist": ("Business", 19), "DocuMind": ("Pro", 45)}  # plan, $ per month
FILES = {"ChatPilot": "seats_chatpilot.csv", "CodeAssist": "seats_codeassist.csv", "DocuMind": "seats_documind.csv"}


def freeze_zip(path: Path) -> None:
    """openpyxl stamps the saved time and every zip entry with the clock; fix them so a re-run is byte-identical."""
    with zipfile.ZipFile(path) as z:
        parts = [(i.filename, z.read(i)) for i in z.infolist()]
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts:
            if name == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2025-07-01T00:00:00Z", data)
            z.writestr(zipfile.ZipInfo(name, (2025, 7, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)


def make(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    r = random.Random(7)  # noqa: S311  # nosec B311
    people = []  # (id, name, email, dept, status, term_date)
    combos = [(first, last) for last in LAST for first in FIRST]
    r.shuffle(combos)
    for i, (first, last) in enumerate(combos[:120]):
        people.append([f"E{1001 + i}", f"{first} {last}", f"{first}.{last}@example.com".lower(), r.choice(DEPTS), "active", None])
    people[0][1:3] = ["Robert Chen", "bob.chen@example.com"]  # goes by a nickname, so the email is not rob.chen
    for p in r.sample(people[8:], 8):  # 8 people have left; 6 of them hold seats
        p[4], p[5] = "terminated", ASOF - timedelta(days=r.randint(20, 150))
    active = [p for p in people if p[4] == "active"]
    gone = [p for p in people if p[4] == "terminated"]

    seats = []  # (email as typed, tool, assigned date, cost or None, person)

    def add(p, tool, email=None, cost="keep"):
        d = ASOF - timedelta(days=r.randint(60, 400))
        seats.append([email or p[2], tool, d, TOOLS[tool][1] if cost == "keep" else cost, p])

    for p in gone[:6]:
        add(p, r.choice(list(TOOLS)))
    users = r.sample([p for p in active if p[0] != "E1001"], 74)
    for p in users:
        add(p, r.choice(list(TOOLS)))
    maya = users[0]
    add(maya, seats[6][1], email=maya[2].upper())  # duplicate seat, same tool, typed in capitals
    add(people[0], "DocuMind", email="rob.chen@example.com")  # unresolvable: nobody has this email
    add(people[0], "CodeAssist")  # bob.chen resolves through the roster email

    # usage: most seats are in use, ten are not
    idle = [s for s in seats[6:] if s[4] not in (maya, people[0])][:10]
    idle_ids = {id(s) for s in idle}
    idle[3][3] = None  # one idle seat has no cost on file
    usage = []
    for s in seats:
        if s[0] == "rob.chen@example.com":
            continue
        if s[4][4] == "terminated":
            last, n = s[4][5] - timedelta(days=r.randint(1, 10)), 0
        elif id(s) in idle_ids:
            last, n = ASOF - timedelta(days=r.randint(35, 120)), 0
        else:
            last, n = ASOF - timedelta(days=r.randint(0, 14)), r.randint(4, 60)
        usage.append([s[0].lower(), s[1], last.isoformat(), n])
    first_row = {}  # the duplicate seat shares its owner's usage row, so keep one row per (email, tool)
    for u in usage:
        first_row.setdefault((u[0], u[1]), u)
    usage = list(first_row.values())

    # approvals: everyone has one except three active people in use
    no_appr = [s for s in seats[10:] if id(s) not in idle_ids and s[4] not in (maya, people[0])][:3]
    skip = {(s[0].lower(), s[1]) for s in no_appr}
    appr = sorted({(s[0].lower(), s[1]) for s in seats if s[0] != "rob.chen@example.com"} - skip)

    for tool, name in FILES.items():
        with open(out / name, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Seat Email", "Tool", "Plan", "Monthly Cost", "Assigned Date"])
            for i, s in enumerate(x for x in seats if x[1] == tool):
                d = s[2].strftime("%m/%d/%Y") if i % 4 == 0 else s[2].isoformat()  # two date formats
                w.writerow(
                    [
                        s[0] if i % 5 else s[0].title() if "@" in s[0] and s[0].islower() else s[0],
                        tool,
                        TOOLS[tool][0],
                        "" if s[3] is None else f"${s[3]:.2f}",
                        d,
                    ]
                )
    with open(out / "usage_log.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Email", "Tool", "Last Active", "Sessions (30d)"])
        w.writerows(usage)
    with open(out / "access_approvals.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Email", "Tool", "Approved By", "Approved Date"])
        for e, t in appr:
            w.writerow([e, t, "J. Rivera (IT)", "2024-11-04"])
    wb = Workbook()
    ws = wb.active
    ws.title = "Roster"
    ws.append(["Bluebonnet Supply Co. - HR roster as of 2025-06-30"])
    ws.append([])
    ws.append(["Employee ID", "Name", "Email", "Department", "Status", "Termination Date"])
    for i, p in enumerate(people):
        ws.append([p[0], p[1], p[2].title() if i % 7 == 0 else p[2], p[3], p[4].title() if i % 3 == 0 else p[4], p[5]])
    wb.properties.created = datetime(2025, 7, 1)  # fixed, so a re-run is byte-identical
    wb.save(out / "hr_roster.xlsx")
    freeze_zip(out / "hr_roster.xlsx")


if __name__ == "__main__":
    make(Path(sys.argv[1] if len(sys.argv) > 1 else "data/licenses"))
    print("wrote synthetic license data")
