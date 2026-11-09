"""Release gate: `python -m engine.gate` runs the tests plus contract checks. Exit 1 on any failure."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import pipeline  # noqa: E402
from scripts.make_sample_data import make  # noqa: E402

# Calls that would mean a missing number was being invented. gate.py itself is skipped when scanning.
IMPUTATION_CALLS = ["fillna", "interpolate", "ffill", "bfill", "SimpleImputer"]


def contracts() -> list[str]:
    fails = []
    with tempfile.TemporaryDirectory() as d:
        make(Path(d) / "in")
        a = pipeline.run(Path(d) / "in", Path(d) / "out1", offline=True)
        pipeline.run(Path(d) / "in", Path(d) / "out2", offline=True)
        md = (Path(d) / "out1" / "report.md").read_text()
        html = (Path(d) / "out1" / "report.html").read_text()
        same = md == (Path(d) / "out2" / "report.md").read_text()
    ledger = a["ledger"]
    if any(not f.source for f in ledger.figs.values()):
        fails.append("a figure has no provenance")
    if any(f.value is None and not f.reason for f in ledger.figs.values()):
        fails.append("a missing figure has no named reason")
    if any(f.key not in md for f in ledger.figs.values() if f.value is None):
        fails.append("a flagged figure is not listed under Needs attention")
    if any("not computed" not in r.reason for r in a["results"] if r.status == "blocked"):
        fails.append("a blocked analysis does not say 'not computed'")
    if not a["verdict"].ok:
        fails.append("verifier rejected the template summary: " + "; ".join(a["verdict"].problems))
    if "Needs attention" not in html:
        fails.append("report.html is missing the Needs attention box")
    if not same:
        fails.append("two runs on the same input gave different reports")
    from engine import licenses as lic
    from scripts.make_license_data import make as make_lic

    with tempfile.TemporaryDirectory() as d:
        make_lic(Path(d) / "lic")
        r1, r2 = lic.reconcile(Path(d) / "lic"), lic.reconcile(Path(d) / "lic")
    if not lic.verify(lic.draft(r1), r1).ok:
        fails.append("license verifier rejected the template summary")
    if any(not f.sources for f in r1.findings):
        fails.append("a license finding has no provenance")
    if any(f.counted and (f.cost is None or f.category == "unresolvable") for f in r1.findings):
        fails.append("license savings count an ambiguous seat")
    if lic.draft(r1) != lic.draft(r2):
        fails.append("two license runs gave different summaries")
    from scripts.make_site import check as site_check

    fails += site_check()
    for p in (ROOT / "engine").glob("*.py"):
        if p.name != "gate.py" and any(w in p.read_text() for w in IMPUTATION_CALLS):
            fails.append(f"{p.name} contains an imputation call")
    return fails


def main() -> int:
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # the gate never calls a model
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--cov=engine", "--cov-report=term:skip-covered"], cwd=ROOT, env=env
    ).returncode
    fails = contracts()
    for f in fails:
        print(f"CONTRACT FAIL: {f}")
    ok = tests == 0 and not fails
    print(f"\nGATE {'PASSED' if ok else 'FAILED'}: tests {'ok' if tests == 0 else 'failed'}, {len(fails)} contract failure(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
