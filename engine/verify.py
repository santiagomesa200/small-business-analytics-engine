"""The independent checker. It sees only the summary text and the computed results, never the drafter.

Rules, in plain words:
  1. The summary has one sentence per analysis, and no sentence is repeated.
  2. Every sentence ends with a citation like [cash_runway] naming a real analysis, and each analysis is cited exactly once.
  3. Every number must equal a figure computed by the analysis that sentence cites, and carry the same unit ($, %, days, months, pp, x).
  4. A blocked analysis may not have any number stated for it, and must be described as "not computed".
  5. A metric that was not computed may not be mentioned without saying "not computed".
  6. A bare four-digit year is allowed only if it appears in that analysis's period labels.
This checks the value and unit of the numbers it finds. It does not check numbers written as words, numbers joined to letters
such as Q1 or FY2026, month labels like 2025-04, which figure a number belongs to, or whether a sentence says up or down.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .analyses import Result


@dataclass
class Verdict:
    ok: bool
    problems: list[str]


def citations(sentence: str) -> list[str]:
    """Words like '[cash_runway]' -> 'cash_runway'."""
    found = []
    for word in sentence.split():
        word = word.rstrip(".,;")
        if word.startswith("[") and word.endswith("]"):
            found.append(word[1:-1])
    return found


UNIT_WORDS = {"days": "days", "day": "days", "months": "months", "month": "months", "pp": "pp"}
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
DATE = re.compile(r"\b\d{4}-(?:0[1-9]|1[0-2])\b")  # 2025-04: the only date form that is not a number
NUMBER = re.compile(r"(?<![\w.])(\(?)([-+\u2212]?)(\$?)(\.\d+|\d+(?:,\d{3})*(?:\.\d+)?)(\)?)")
UNIT_WORD = re.compile(r"[\"'*)]*\s*(days?|months?|pp)\b", re.I)


def scan(sentence: str) -> list[tuple[float, int, str | None]]:
    """(value, decimals shown, unit) for each number: '$57,900' -> (57900, 0, '$'), '7.1 months' -> (7.1, 1, 'months').
    Numbers are found by pattern, so quotes, bold markers, '.5', a Unicode minus, '(1,200)' and ranges such as '$2,000-$3,000'
    or '20%-30%' do not hide them. Numbers written as words ("seven months") are not numerals and are not found."""
    text = DATE.sub(" ", re.sub(r"\[[^\]]*\]", " ", sentence))  # citations and dates are not figures
    found = []
    for m in NUMBER.finditer(text):
        opened, sign, dollar, digits, closed = m.groups()
        if sign and text[max(m.start() - 1, 0) : m.start()] in ("%", "$"):  # "20%-30%": a dash after a figure is a range, not a minus
            sign = ""
        after = text[m.end() :]
        word = UNIT_WORD.match(after)
        unit = "$" if dollar else "%" if after.startswith("%") else "x" if re.match(r"x(?!\w)", after) else None
        unit = unit or (UNIT_WORDS[word.group(1).lower()] if word else None)
        value = float(digits.replace(",", ""))
        if "." not in digits and "," not in digits and unit is None and 1900 <= value <= 2100:
            unit = "year"
        negative = sign in ("-", "\u2212") or bool(opened and closed and unit != "year")  # "(1,200)" is negative, as in normalize.py
        found.append((-value if negative else value, len(digits.split(".")[1]) if "." in digits else 0, unit))
    return found


def show(value: float, decimals: int, unit: str | None) -> str:
    """A number as the summary writes it: $31,000, 44.8 days, 12.5%."""
    n, sign = f"{abs(value):,.{decimals}f}", "-" if value < 0 else ""
    if unit == "$":
        return f"{sign}${n}"
    return f"{sign}{n}{unit}" if unit in ("%", "x") else f"{sign}{n} {unit}" if unit else f"{sign}{n}"


def numbers(sentence: str) -> list[tuple[float, int]]:
    return [(v, d) for v, d, _ in scan(sentence)]


def coverage_problems(sentences: list[str], ids: list[str]) -> list[str]:
    """No sentence repeated, and every id in `ids` cited exactly once. Shared with engine/licenses.py."""
    problems = []
    if len({s.lower() for s in sentences}) != len(sentences):
        problems.append("a sentence is repeated")
    cited_all = [c for s in sentences for c in citations(s)]
    for rid in ids:
        if cited_all.count(rid) != 1:
            problems.append(f"analysis '{rid}' is cited {cited_all.count(rid)} times, expected exactly once")
    return problems


def verify(summary: str, results: list[Result]) -> Verdict:
    problems = []
    by_id = {r.id: r for r in results}
    sentences = re.split(r"(?<=[.!?])\s+", summary.strip().replace(". [", " ["))
    if len(sentences) != len(by_id):
        problems.append(f"expected {len(by_id)} sentences, found {len(sentences)}")
    problems += coverage_problems(sentences, list(by_id))
    for sentence in sentences:
        short = sentence[:60] + ("..." if len(sentence) > 60 else "")
        cited = citations(sentence)
        if not cited or any(c not in by_id for c in cited):
            problems.append(f"no valid analysis citation: '{short}'")
            continue
        figures = [(m.unit, m.value) for c in cited for m in by_id[c].metrics if m.value is not None]
        years = {int(y) for c in cited for t in [*by_id[c].assumptions, *(m.label for m in by_id[c].metrics)] for y in YEAR.findall(t)}
        nums = scan(sentence)
        for value, decimals, unit in nums:  # rules 3 and 6
            if unit == "year":
                if int(value) not in years:
                    problems.append(f"year {int(value)} is not a period of {', '.join(cited)}: '{short}'")
            elif unit is None:
                problems.append(f"number {show(value, decimals, None)} has no unit: '{short}'")
            elif not any(u == unit and round(a, decimals) == value for u, a in figures):
                problems.append(f"number {show(value, decimals, unit)} is not a figure of {', '.join(cited)}: '{short}'")
        for c in cited:
            result = by_id[c]
            said_not_computed = "not computed" in sentence.lower()
            if result.status == "blocked" and any(u != "year" for _, _, u in nums):  # rule 4
                problems.append(f"states numbers for blocked analysis '{c}': '{short}'")
            if result.status == "blocked" and not said_not_computed:
                problems.append(f"blocked analysis '{c}' is not described as not computed: '{short}'")
            for m in result.metrics:  # rule 5
                if m.value is None and m.label in sentence and not said_not_computed:
                    problems.append(f"flagged metric '{m.label}' is not described as not computed: '{short}'")
    return Verdict(not problems, problems)
