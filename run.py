"""Usage: python run.py data/sample [output_folder]    or    python run.py data/licenses --mode licenses [output_folder]"""

import argparse
from pathlib import Path

from engine.pipeline import run


def analyze(folder: str, out_dir: str = "outputs/sample") -> None:
    out = run(folder, out_dir)
    ledger, results = out["ledger"], out["results"]
    n_ok = sum(f.value is not None for f in ledger.figs.values())

    def count(status: str) -> int:
        return sum(x.status == status for x in results)

    print(f"Files read:         {len(out['files'])} ({', '.join(out['files'])})")
    print(f"Figures extracted:  {len(ledger.figs)} ({n_ok} usable, {len(ledger.figs) - n_ok} flagged)")
    print(f"Issues flagged:     {len(ledger.issues)}")
    print(f"Analyses:           {count('computed')} computed, {count('partial')} partial, {count('blocked')} blocked")
    for x in results:
        print(f"  - {x.id:<16} {x.status}")
    print(f"Verifier:           {'PASS' if out['verdict'].ok else 'FAIL - summary blocked'} (drafter: {out['drafter']})")
    print(f"Runtime:            {out['seconds']:.2f}s")
    print(f"Wrote {out_dir}/report.md, report.html, figures.csv")


def licenses(folder: str, out_dir: str = "outputs/licenses") -> None:
    from engine import licenses as lic

    r = lic.run(folder, out_dir)
    res = r["result"]
    print(f"Seats read:         {res.seats} ({res.people} people on the roster)")
    off = lic.not_computed(res)
    for c in lic.ORDER:
        print(f"  - {c:<18} {'not computed' if c in off else len(res.of(c))}")
    print(
        f"Savings if reclaimed: not computed because {off['savings']}"
        if "savings" in off
        else f"Savings if reclaimed: ${res.monthly:,.0f} a month, ${res.annual:,.0f} a year"
    )
    print(f"Verifier:           {'PASS' if r['verdict'].ok else 'FAIL - summary blocked'}")
    print(f"Wrote {out_dir}/report.md, report.html, actions.csv")


def cli(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="run.py", description="Run the analysis engine, or the AI license and access reconciler with --mode licenses."
    )
    ap.add_argument("folder", nargs="?", help="input folder (default: data/sample, or data/licenses with --mode licenses)")
    ap.add_argument("out_dir", nargs="?", help="output folder (default: outputs/sample, or outputs/licenses with --mode licenses)")
    ap.add_argument("--mode", choices=["licenses"], help="run the AI license and access reconciler instead")
    a = ap.parse_args(argv)
    folder = a.folder or ("data/licenses" if a.mode == "licenses" else "data/sample")
    if not Path(folder).is_dir():
        ap.error(f"{folder} is not a folder")
    if a.mode == "licenses":
        licenses(folder, a.out_dir or "outputs/licenses")
    else:
        analyze(folder, a.out_dir or "outputs/sample")


if __name__ == "__main__":
    cli()
