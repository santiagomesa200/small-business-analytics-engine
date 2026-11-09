"""Plain-English wording shared by the summary and the report."""

from __future__ import annotations

import re

COMPANY = "Bluebonnet Supply Co."  # the synthetic sample company
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MEASURES = {
    "DSO": "customer payment days",
    "DPO": "supplier payment days",
    "DIO": "inventory days",
    "Cash conversion cycle": "cash conversion cycle",
}


def month_name(year_month: str) -> str:
    return MONTHS[int(year_month[5:7]) - 1]


def first_month(text: str) -> str | None:
    found = re.search(r"\d{4}-\d{2}", text)
    return month_name(found.group(0)) if found else None


def dates_to_words(text: str) -> str:
    return re.sub(r"\d{4}-\d{2}", lambda m: month_name(m.group(0)), text)


def why(reason: str) -> str:
    """The cause, in words, taken from a 'not computed' reason."""
    month = first_month(reason)
    if "column is absent" in reason and month:
        return f"{month}'s figures are missing"
    if "parts give" in reason:
        return f"{month}'s subtotal does not add up" if month else "a subtotal does not add up"
    if "did not decline" in reason:
        return "cash did not decline over the period"
    if "not positive" in reason:
        return "EBITDA is not positive"
    if "needs DSO" in reason:
        return "one of the measures above is missing"
    if "at least one month" in reason:
        return "a month in the range is flagged"
    if "not found in any input file" in reason or "no usable input" in reason:
        return "an input file is missing or could not be read"
    return "an input is flagged"


def fix(reason: str) -> str:
    month = first_month(reason)
    if "column is absent" in reason and month:
        return f"send the {month} column"
    if "not found in any input file" in reason or "no usable input" in reason:
        return "send the missing file (see Needs attention)"
    return "confirm the right figure with whoever prepared the file"


def metric_name(label: str) -> str:
    """'Gross margin 2025-04' -> 'April gross margin'; 'DPO' -> 'supplier payment days'."""
    found = re.match(r"Gross margin (\d{4}-\d{2})", label)
    if found:
        return f"{month_name(found.group(1))} gross margin"
    return MEASURES.get(label, label.lower())


def pretty(label: str) -> str:
    found = re.match(r"Gross margin (\d{4}-\d{2})", label)
    return f"Gross margin, {month_name(found.group(1))}" if found else label
