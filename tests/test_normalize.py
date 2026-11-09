import pytest

from engine.normalize import BS, PNL, canon, detect_scale, month_range, parse_month, to_number


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("(1,234)", -1234.0),
        ("$12.50", 12.5),
        ("412,300", 412300.0),
        (" 7 ", 7.0),
        (None, None),
        ("", None),
        ("-", None),
        ("n/a", None),
        (5, 5.0),
        ("abc", None),
    ],
)
def test_to_number(raw, expected):
    assert to_number(raw) == expected


def test_header_aliases_map_to_one_name():
    assert canon("Net Sales", PNL) == canon("Revenue", PNL) == "revenue"
    assert canon("Trade Receivables", BS) == canon("Accounts Receivable", BS) == "ar"
    assert canon("Something else", PNL) is None


def test_months_and_units():
    assert parse_month("Jan-25") == "2025-01" and parse_month("2025-06") == "2025-06"
    assert parse_month("Line Item") is None
    assert month_range("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]
    assert detect_scale("Opex detail ($ in thousands)") == 1000
    assert detect_scale("Monthly P&L (USD)") == 1


@pytest.mark.parametrize("text", ["nan", "inf", "-inf", "(nan)"])
def test_non_finite_numbers_are_not_figures(text):
    assert to_number(text) is None and to_number(float("nan")) is None
