"""The drafter: an offline run never calls a model, and a bad or partial Claude reply falls back to the template and says so."""

import sys
import types

from conftest import summary

from engine import pipeline
from engine.summarize import draft, template
from engine.verify import verify


def test_offline_run_never_calls_a_model(sample_dir, tmp_path, monkeypatch):
    called = []
    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda: called.append(1) or (_ for _ in ()).throw(AssertionError("model called"))
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    out = pipeline.run(sample_dir, tmp_path, offline=True)
    assert out["drafter"] == "template" and not called


def fake_claude(monkeypatch, content, stop_reason="end_turn"):
    """Install a fake `anthropic` whose reply has the given content blocks; returns the kwargs the engine sent."""
    seen = {}
    fake = types.ModuleType("anthropic")
    msg = types.SimpleNamespace(content=content, stop_reason=stop_reason)
    fake.Anthropic = lambda: types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **kw: seen.update(kw) or msg))
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    return seen


def test_model_id_is_current(monkeypatch):
    seen = fake_claude(monkeypatch, [types.SimpleNamespace(type="text", text="x")])
    draft([])
    assert seen["model"] == "claude-sonnet-5-5"


def test_claude_reply_that_starts_with_a_thinking_block_still_gives_the_text(monkeypatch):
    seen = fake_claude(
        monkeypatch, [types.SimpleNamespace(type="thinking", thinking="hmm"), types.SimpleNamespace(type="text", text=" Hello. ")]
    )
    assert draft([]) == ("Hello.", "claude")
    assert seen["max_tokens"] >= 16000  # room for thinking plus the five sentences


def test_claude_reply_that_stopped_early_or_has_no_text_falls_back_and_says_so(monkeypatch):
    fake_claude(monkeypatch, [types.SimpleNamespace(type="text", text="cut off")], stop_reason="max_tokens")
    text, drafter = draft([])
    assert drafter.startswith("template (Claude unavailable") and "max_tokens" in drafter and text == template([])
    fake_claude(monkeypatch, [types.SimpleNamespace(type="thinking", thinking="only thoughts")])
    assert "no text" in draft([])[1]
    fake_claude(monkeypatch, [types.SimpleNamespace(type="text", text="  \n ")])  # a block of only whitespace is not a draft
    text, drafter = draft([])
    assert drafter.startswith("template (Claude unavailable") and "no text" in drafter and text == template([])


def test_gross_margin_sentence_says_the_change_is_not_computed_when_a_month_is_flagged(sample, clean):
    flagged = next(s for s in summary(sample)[1].split(". ") if "[gross_margin]" in s)
    assert "went from" not in flagged and "a change of" not in flagged
    assert "42.0% in January and 40.0% in June" in flagged and "the change over the period is not computed" in flagged
    assert "a change of" in summary(clean)[1]  # when every month computes, the change is stated as before
    res, text = summary(sample)
    assert verify(text, res).ok


def test_clean_working_capital_sentence_is_one_list_not_a_run_on(clean):
    text = summary(clean)[1]
    assert ", the cash" not in text and "we pay" not in text
    assert "suppliers are paid in about 54.4 days, inventory sits for about 94.4 days and the cash conversion cycle is 84.8 days" in text
