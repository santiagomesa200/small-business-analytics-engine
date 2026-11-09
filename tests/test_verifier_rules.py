"""The summary checker rejects wrong units, invented numbers, repeats and gaps, and reads numbers however they are written."""

import pytest
from conftest import summary

from engine.verify import scan, verify


def test_number_with_the_wrong_unit_is_rejected(sample):
    res, text = summary(sample)
    v = verify(text.replace("7.1 months of runway", "412,300 months of runway"), res)  # 412,300 is a real dollar figure
    assert not v.ok and any("412,300" in p and "months" in p for p in v.problems)


def test_invented_round_number_is_not_waved_through_as_a_year(sample):
    res, text = summary(sample)
    v = verify(text.replace("price contributed $24,125", "price contributed $2,000"), res)
    assert not v.ok and any("2,000" in p and "price_volume" in p for p in v.problems)


def test_year_must_be_a_period_label(sample):
    res, text = summary(sample)
    bad = text.replace("in June;", "in June in 2031;")
    assert bad != text
    v = verify(bad, res)
    assert not v.ok and any("year 2031" in p for p in v.problems)


def test_repeated_sentences_are_rejected(sample):
    res, text = summary(sample)
    runway = next(s for s in text.split(". ") if "[cash_runway]" in s).rstrip(".") + "."
    v = verify(" ".join([runway] * 5), res)
    assert not v.ok and "a sentence is repeated" in v.problems


def test_every_analysis_must_be_covered_exactly_once(sample):
    res, text = summary(sample)
    v = verify(text.replace("[valuation]", "[cash_runway]"), res)  # five sentences, but the valuation one cites cash_runway
    assert not v.ok and any("'valuation' is cited 0 times" in p for p in v.problems)


def test_a_number_with_no_unit_is_rejected(sample):
    res, text = summary(sample)
    v = verify(text.replace("$57,900 a month", "57,900 a month"), res)
    assert not v.ok and any("number 57,900 has no unit" in p for p in v.problems)


def test_numbers_in_markup_quotes_and_ranges_are_still_checked(sample):
    assert scan("It is **$2,000** now.") == [(2000.0, 0, "$")]
    assert scan('said "412,300" months') == [(412300.0, 0, "months")]
    assert scan("between $2,000-$3,000.") == [(2000.0, 0, "$"), (3000.0, 0, "$")]
    assert scan("-$24,125 and +1.5 pp and 2025-04") == [(-24125.0, 0, "$"), (1.5, 1, "pp")]
    res, text = summary(sample)
    v = verify(text.replace("price contributed $24,125", "price contributed **$2,000**"), res)
    assert not v.ok and any("2,000" in p and "price_volume" in p for p in v.problems)


@pytest.mark.parametrize(
    "text, want",
    [
        (".5%", [(0.5, 1, "%")]),
        ("fell −$24,125 and −5%", [(-24125.0, 0, "$"), (-5.0, 0, "%")]),
        ("between 20%-30%", [(20.0, 0, "%"), (30.0, 0, "%")]),
        ("a loss of (1,200)", [(-1200.0, 0, None)]),
        ("a loss of ($1,200)", [(-1200.0, 0, "$")]),
        ("for 2,000.", [(2000.0, 0, None)]),  # a number with a comma is a count or an amount, never a year
        ("in 2025.", [(2025.0, 0, "year")]),
        ("(45 days)", [(45.0, 0, "days")]),
    ],
)
def test_scan_reads_leading_dots_unicode_minus_ranges_commas_and_parentheses(text, want):
    assert scan(text) == want


def test_verify_blocks_each_of_those_forms(sample):
    res, text = summary(sample)
    for old, new in [("7.1 months", ".5 months"), ("$57,900", "−$57,900"), ("$57,900", "(57,900)"), ("$57,900", "2,000.")]:
        assert not verify(text.replace(old, new), res).ok, new


def test_a_year_in_brackets_is_a_year_and_a_bracketed_amount_is_negative(sample):
    assert scan("Q1 (2025)") == [(2025.0, 0, "year")] and scan("a loss of (1,200)") == [(-1200.0, 0, None)]
    res, text = summary(sample)
    assert verify(text.replace("in June;", "in June (2025);"), res).ok
