"""Writes outputs/examples/: a summary the verifier rejects, and the verifier's output."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.analyses import run_analyses
from engine.checks import check_all
from engine.extract import extract_all
from engine.read import read_folder
from engine.summarize import template
from engine.verify import verify


def swap(text: str, old: str, new: str) -> str:
    """text.replace, but loud when the template wording has changed and nothing would be replaced."""
    if old not in text:
        raise ValueError(f"{old!r} is not in the summary, so the rejection example would not be rejected")
    return text.replace(old, new)


def build() -> tuple[str, str]:
    """(the rejected summary, the verifier's printed result)."""
    ledger = extract_all(read_folder(ROOT / "data/sample"))
    check_all(ledger)
    results = run_analyses(ledger)
    bad = swap(template(results), "7.1 months of runway", "44.8 days of runway")  # 44.8 is DSO, cited under cash_runway
    bad = swap(bad, "$24,125", "$31,000")  # fabricated price effect
    verdict = verify(bad, results)
    text = (
        "Verifier result: "
        + ("PASS" if verdict.ok else "FAIL - summary blocked")
        + "\n"
        + "\n".join(f"- {p}" for p in verdict.problems)
        + "\n"
    )
    return bad, text


if __name__ == "__main__":
    out = ROOT / "outputs/examples"
    out.mkdir(parents=True, exist_ok=True)
    bad, text = build()
    (out / "rejected_summary.txt").write_text(bad + "\n")
    (out / "verifier_output.txt").write_text(text)
    print(text)
