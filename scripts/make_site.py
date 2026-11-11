"""Builds the GitHub Pages site: docs/site-data.json (from real engine runs), docs/index.html (data inlined),
and docs/reports/ (the HTML reports and the actions CSV). `python scripts/make_site.py`, or `--check` to compare without writing."""

from __future__ import annotations

import difflib
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import pipeline, sitedata
from engine import verify as verify_mod
from scripts.make_rejection_example import build as rejection_example

one = lambda folder: sitedata.one(folder, ROOT)
flag_rows = sitedata.flag_rows
SCENARIOS = {"messy": ("data/sample", "outputs/sample"), "clean": ("data/clean", "outputs/clean")}
INDEX = ROOT / "docs/index.html"
DATA = ROOT / "docs/site-data.json"
BUNDLE = ROOT / "docs/engine-bundle.zip"
MARK = re.compile(r"(<!--SITE-DATA-->).*?(<!--/SITE-DATA-->)", re.S)


def rejection(good: str) -> dict:
    bad, verdict = rejection_example()
    out = verdict.strip().splitlines()
    a, b = bad.split(), good.split()
    parts = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        parts.append(dict(t=" ".join(a[i1:i2]), bad=op != "equal", good=" ".join(b[j1:j2]) if op != "equal" else ""))
    rules = [re.sub(r"^\s*\d\.\s*", "", ln) for ln in (verify_mod.__doc__ or "").splitlines() if re.match(r"\s*\d\. ", ln)]
    return dict(parts=parts, verdict=out[0], problems=[ln[2:] for ln in out[1:]], rules=rules)


def licenses_data() -> dict:
    """The AI license and access reconciler run on data/licenses, shaped for the page."""
    from engine import licenses as lic

    res = lic.reconcile(ROOT / "data/licenses")
    summary = lic.draft(res)
    verdict = lic.verify(summary, res)
    cats = [
        dict(
            id=c,
            title=lic.TITLES[c],
            action=lic.ACTION[c],
            count=len(res.of(c)),
            monthly=res.saved(c),
            findings=[
                dict(
                    email=f.email,
                    tool=f.tool,
                    plan=f.plan,
                    cost=f.cost,
                    detail=f.detail,
                    action=f.action,
                    counted=f.counted,
                    sources=f.sources,
                )
                for f in res.of(c)
            ],
        )
        for c in lic.ORDER
    ]
    nums = sum(len(verify_mod.numbers(x)) for x in re.split(r"(?<=[.!?])\s+", summary))
    return dict(
        asof=str(res.asof),
        files=len(list((ROOT / "data/licenses").iterdir())),
        actions=len(res.findings),
        seats=res.seats,
        people=res.people,
        flagged=len({f.sources[0] for f in res.findings}),
        categories=cats,
        monthly=res.monthly,
        annual=res.annual,
        counted=sum(f.counted for f in res.findings),
        summary=summary,
        verifier=dict(ok=verdict.ok, problems=verdict.problems, numbers_checked=nums),
    )


def tests_collected() -> int:
    p = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True)
    return int(re.search(r"(\d+) tests? collected", p.stdout).group(1))


def build_data() -> tuple[dict, dict]:
    """(data for the page, html of each report). Deterministic: no timestamps, no runtimes."""
    sc = {k: one(f) for k, (f, _) in SCENARIOS.items()}
    reports = {k: v.pop("_report_html") for k, v in sc.items()}
    n = tests_collected()
    return dict(
        scenarios=sc,
        rejection=rejection(sc["messy"]["summary"]),
        licenses=licenses_data(),
        tests=n,
    ), reports


def inline(data: dict, text: str) -> str:
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return MARK.sub(lambda m: f'{m.group(1)}<script id="site-data" type="application/json">{blob}</script>{m.group(2)}', text)


def sync_counts(n: int, write: bool = True, root: Path = ROOT) -> list[str]:
    """Put the gate's real test count into README.md. Returns the files that were out of date."""
    stale = []
    f = root / "README.md"
    old = f.read_text()
    new = re.sub(r"\b\d+ tests\b", f"{n} tests", old)
    if new != old:
        stale.append(f.name)
        if write:
            f.write_text(new)
    return stale


FONT_URL = re.compile(r"url\([^)]*?fonts/")  # the font path depends on where a report is written


def fresh_files() -> dict[str, str]:
    """Every committed report and CSV as a fresh offline run writes it, keyed by repo path. Font URLs are normalized."""
    from engine import licenses as lic

    out: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        runs = {**{k: (f, rel) for k, (f, rel) in SCENARIOS.items()}, "licenses": ("data/licenses", "outputs/licenses")}
        for name, (folder, rel) in runs.items():
            d = Path(tmp) / name
            pipeline.run(ROOT / folder, d, offline=True) if name != "licenses" else lic.run(ROOT / folder, d)
            for f in d.iterdir():
                out[f"{rel}/{f.name}"] = f.read_text()
    for src, dst in DOCS_COPIES.values():
        out[f"docs/reports/{dst}"] = out[src]
    bad, verdict = rejection_example()
    out["outputs/examples/rejected_summary.txt"], out["outputs/examples/verifier_output.txt"] = bad + "\n", verdict
    return {k: FONT_URL.sub("url(FONTS/", v) for k, v in out.items()}


DOCS_COPIES = {
    "messy": ("outputs/sample/report.html", "messy.html"),
    "clean": ("outputs/clean/report.html", "clean.html"),
    "licenses": ("outputs/licenses/report.html", "licenses.html"),
    "licenses-actions": ("outputs/licenses/actions.csv", "licenses-actions.csv"),
}


def bundle_files() -> dict[str, bytes]:
    """What the in-browser "Run it" button runs: the engine, run.py, the sample inputs and the committed figures.csv to compare with."""
    paths = [ROOT / "run.py", *sorted((ROOT / "engine").glob("*.py")), ROOT / "engine/report.css"]
    paths = [p for p in paths if p.name != "gate.py"]  # the release gate runs pytest in a subprocess; the browser never needs it
    for folder, out in SCENARIOS.values():
        paths += sorted(p for p in (ROOT / folder).iterdir() if p.is_file()) + [ROOT / out / "figures.csv"]
    return {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in paths}


def bundle_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in bundle_files().items():
            z.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data, zipfile.ZIP_DEFLATED)
    return buf.getvalue()


WHEELS = [
    "et_xmlfile",
    "openpyxl",
    "pypdf",
]  # pure-Python wheels the browser installs from docs/wheels/, versions pinned in requirements.txt


def wheel_problems(root: Path = ROOT) -> list[str]:
    pins = dict(re.findall(r"^([A-Za-z_.-]+)==(\S+)", (ROOT / "requirements.txt").read_text(), re.M))
    out = []
    for name in WHEELS:
        have = sorted((root / "docs/wheels").glob(f"{name}-*.whl"))
        want = pins[name]
        if [w.name.split("-")[1] for w in have] != [want] or not have[0].name.endswith("-none-any.whl"):
            out.append(f"docs/wheels must hold exactly the pure-Python {name}-{want} wheel (requirements.txt pin)")
    return out


def bundle_problems(path: Path) -> list[str]:
    """Problems if the zip on disk holds different files, or different bytes, than the repo's own sources (compared by content, not zip bytes)."""
    if not path.exists():
        return ["docs/engine-bundle.zip is missing (run python scripts/make_site.py)"]
    with zipfile.ZipFile(path) as z:
        have = {n: z.read(n) for n in z.namelist()}
    want = bundle_files()
    return [
        f"docs/engine-bundle.zip: {n} does not match the repo (run python scripts/make_site.py)"
        for n in sorted(set(have) | set(want))
        if have.get(n) != want.get(n)
    ]


def check(root: Path = ROOT) -> list[str]:
    """Problems if any committed page data, report or CSV differs from a fresh offline run of the engine."""
    fresh = json.loads(json.dumps(build_data()[0]))  # tuples become lists, as in the file
    fails = []
    data, index = root / "docs/site-data.json", root / "docs/index.html"
    if not data.exists() or json.loads(data.read_text()) != fresh:
        fails.append("docs/site-data.json does not match a fresh engine run (run python scripts/make_site.py)")
    m = re.search(r'<script id="site-data" type="application/json">(.*?)</script>', index.read_text(), re.S)
    if not m or json.loads(m.group(1).replace("<\\/", "</")) != fresh:
        fails.append("docs/index.html carries data that does not match a fresh engine run")
    fails += bundle_problems(root / "docs/engine-bundle.zip") + wheel_problems(root)
    fails += [
        f"{n} has a different test count than the gate (run python scripts/make_site.py)"
        for n in sync_counts(fresh["tests"], write=False, root=root)
    ]
    for path, text in fresh_files().items():
        f = root / path
        if not f.exists() or FONT_URL.sub("url(FONTS/", f.read_text()) != text:
            fails.append(f"{path} does not match a fresh run (run python scripts/make_site.py)")
    return fails


def main() -> None:
    if "--check" in sys.argv:
        problems = check()
        print("\n".join(problems) or "site data matches a fresh run")
        sys.exit(bool(problems))
    data, _ = build_data()
    from engine import licenses as lic

    for folder, out in SCENARIOS.values():  # refresh the committed outputs so the linked reports match the data
        pipeline.run(ROOT / folder, ROOT / out, offline=True)
    lic.run(ROOT / "data/licenses", ROOT / "outputs/licenses")
    (ROOT / "outputs/examples/rejected_summary.txt").write_text(rejection_example()[0] + "\n")
    (ROOT / "outputs/examples/verifier_output.txt").write_text(rejection_example()[1])
    (ROOT / "docs/reports").mkdir(exist_ok=True)
    for src, dst in DOCS_COPIES.values():  # the reports sit one level from the fonts here
        text = (ROOT / src).read_text()
        (ROOT / "docs/reports" / dst).write_text(FONT_URL.sub("url(../fonts/", text) if dst.endswith(".html") else text)
    sync_counts(data["tests"])
    BUNDLE.write_bytes(bundle_zip())
    DATA.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    INDEX.write_text(inline(data, INDEX.read_text()))
    print("wrote docs/site-data.json, docs/index.html (data inlined), docs/reports/{messy,clean}.html, docs/engine-bundle.zip")


if __name__ == "__main__":
    main()
