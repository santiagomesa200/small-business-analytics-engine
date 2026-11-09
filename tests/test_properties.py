"""Property tests: random input must never get past the verifier or the number parser unless it is genuinely valid."""

import math
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from engine.analyses import run_analyses
from engine.checks import check_all
from engine.extract import extract_all
from engine.normalize import to_number
from engine.read import read_folder
from engine.summarize import template
from engine.verify import verify
from scripts.make_sample_data import make

with tempfile.TemporaryDirectory() as _d:
    make(Path(_d))
    _L = extract_all(read_folder(_d))
    check_all(_L)
    RESULTS = run_analyses(_L)
TEXT = template(RESULTS)
RUNWAY = next(r for r in RESULTS if r.id == "cash_runway")
UNITS = ["$", "%", "x", "days", "months", "pp", ""]


def write(value: float, decimals: int, unit: str) -> str:
    n = f"{value:,.{decimals}f}"
    return {"$": f"${n}", "%": f"{n}%", "x": f"{n}x", "days": f"{n} days", "months": f"{n} months", "pp": f"{n} pp", "": n}[unit]


@settings(max_examples=300, deadline=None)
@given(st.floats(0, 5_000_000, allow_nan=False), st.integers(0, 2), st.sampled_from(UNITS))
def test_a_random_number_passes_only_if_it_is_a_cash_runway_figure_in_that_unit(value, decimals, unit):
    bad = TEXT.replace("7.1 months", write(value, decimals, unit))
    if not verify(bad, RESULTS).ok:
        return
    shown = float(f"{value:.{decimals}f}")
    assert any(m.value is not None and m.unit == unit and round(m.value, decimals) == shown for m in RUNWAY.metrics)


@settings(max_examples=100, deadline=None)
@given(st.integers(1900, 2100))
def test_a_bare_year_never_passes_unless_it_is_a_period_label(year):
    bad = TEXT.replace("in June;", f"in June in {year};")
    assert bad != TEXT
    assert verify(bad, RESULTS).ok == (year == 2025)  # 2025 is in the gross margin period labels, no other year is


@settings(max_examples=300, deadline=None)
@given(st.integers(0, 10**12))
def test_thousands_separators_and_dollar_signs_parse_to_the_same_number(n):
    assert to_number(f"{n:,}") == n and to_number(f"${n:,}") == n and to_number(f"$ {n:,}") == n


@settings(max_examples=300, deadline=None)
@given(st.integers(0, 10**12), st.integers(0, 99))
def test_parentheses_mean_negative(n, cents):
    text = f"{n:,}.{cents:02d}"
    assert math.isclose(to_number(f"({text})"), -float(f"{n}.{cents:02d}")) and math.isclose(to_number(text), float(f"{n}.{cents:02d}"))


@settings(max_examples=500, deadline=None)
@given(st.text(max_size=20))
def test_any_text_gives_a_finite_number_or_none_and_never_raises(text):
    v = to_number(text)
    assert v is None or math.isfinite(v)
