"""read -> normalize/extract -> checks -> analyses -> draft -> verify -> report."""

from __future__ import annotations

import time
from pathlib import Path

from . import report
from .analyses import run_analyses
from .checks import check_all
from .extract import extract_all
from .read import read_folder
from .summarize import draft
from .verify import verify


def run(folder: str | Path, out_dir: str | Path = "outputs/sample", offline: bool = False) -> dict:
    t0 = time.time()
    sheets = read_folder(folder)
    ledger = extract_all(sheets)
    check_all(ledger)
    results = run_analyses(ledger)
    summary, drafter = draft(results, offline)
    verdict = verify(summary, results)
    report.write(Path(out_dir), ledger, results, summary, drafter, verdict)
    return dict(
        files=sorted({s.file for s in sheets}),
        ledger=ledger,
        results=results,
        summary=summary,
        drafter=drafter,
        verdict=verdict,
        seconds=time.time() - t0,
    )
