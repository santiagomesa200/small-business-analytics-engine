"""The drafter. It writes a 5-sentence summary; it never checks its own work (see verify.py)."""

from __future__ import annotations

import os

from .analyses import Result, fmt
from .plain import fix, metric_name, why

PROMPT = """Write a 5-sentence executive summary for a business owner, one sentence per analysis below, in this order.
Rules: use numbers exactly as written below, never round or invent any; if an item says NOT COMPUTED, say it was
not computed and state no number for it; end every sentence with its analysis id in square brackets, like [cash_runway],
placed before the full stop; no dates, no extra commentary.

"""


def _facts(results: list[Result]) -> str:
    lines = []
    for r in results:
        body = (
            r.reason.upper()
            if r.status == "blocked"
            else "; ".join(f"{m.label} = {fmt(m) if m.value is not None else 'NOT COMPUTED'}" for m in r.metrics)
        )
        lines.append(f"[{r.id}] {r.title}: {body}")
    return "\n".join(lines)


WORKING_CAPITAL_PHRASE = {
    "DSO": "customers take about {} to pay",
    "DPO": "suppliers are paid in about {}",
    "DIO": "inventory sits for about {}",
    "Cash conversion cycle": "the cash conversion cycle is {}",
}


def template(results: list[Result]) -> str:
    """Plain sentences, one per analysis, each ending with its [analysis id]."""
    out = []
    for r in results:
        if r.status == "blocked":
            title = r.title[0].lower() + r.title[1:]
            out.append(
                f"The {title} is not computed because {why(r.reason)}, so no figures are stated for it; "
                f"{fix(r.reason)} to unblock it [{r.id}]."
            )
            continue
        value = lambda label, r=r: fmt(r.get(label))
        if r.id == "gross_margin":
            months = [m for m in r.metrics if m.label.startswith("Gross margin")]
            good = [m for m in months if m.value is not None]
            bad = [m for m in months if m.value is None]
            if not bad:
                out.append(
                    f"Gross margin went from {fmt(good[0])} to {fmt(good[-1])} over the period, "
                    f"a change of {value('Change, first to last month')} [{r.id}]."
                )
            else:
                names = [metric_name(m.label).split()[0] for m in bad]
                verb = "is" if len(bad) == 1 else "are"
                first, last = (metric_name(m.label).split()[0] for m in (good[0], good[-1]))
                out.append(
                    f"Gross margin was {fmt(good[0])} in {first} and {fmt(good[-1])} in {last}; "
                    f"{' and '.join(names)} {verb} not computed because {' and '.join(why(m.reason or '') for m in bad)}, "
                    f"so the change over the period is not computed either [{r.id}]."
                )
        elif r.id == "price_volume":
            out.append(
                f"Revenue changed by {value('Total change')} between the first and second half of the period: "
                f"price contributed {value('Price effect')} and volume contributed {value('Volume effect')} [{r.id}]."
            )
        elif r.id == "working_capital":
            done = [WORKING_CAPITAL_PHRASE[m.label].format(fmt(m)) for m in r.metrics if m.value is not None]
            todo = [m for m in r.metrics if m.value is None]
            text = done[0] if len(done) == 1 else ", ".join(done[:-1]) + " and " + done[-1]
            if todo:
                names = [("the " if m.label == "Cash conversion cycle" else "") + metric_name(m.label) for m in todo]
                cause = why(next((m for m in todo if m.label != "Cash conversion cycle"), todo[0]).reason or "")
                names_text = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
                text += f"; {names_text} {'is' if len(todo) == 1 else 'are'} not computed because {cause}"
            out.append(text[0].upper() + text[1:] + f" [{r.id}].")
        elif r.id == "cash_runway":
            out.append(
                f"Cash fell from {value('Opening cash')} to {value('Ending cash')}, burning about "
                f"{value('Average monthly net burn')} a month, which leaves about {value('Runway')} of runway "
                f"at that pace [{r.id}]."
            )
        elif r.id == "valuation":
            out.append(
                f"At {value('Multiple (low)')} to {value('Multiple (high)')} annualized EBITDA of "
                f"{value('Annualized EBITDA')}, equity value is {value('Equity value (low)')} to "
                f"{value('Equity value (high)')} [{r.id}]."
            )
    return " ".join(out)


def draft(results: list[Result], offline: bool = False) -> tuple[str, str]:
    """Returns (summary, drafter name). Claude if a key is set, otherwise the deterministic template.
    offline=True always uses the template, which is what the gate and the site build need to be repeatable."""
    if os.getenv("ANTHROPIC_API_KEY") and not offline:
        try:
            import anthropic

            resp = anthropic.Anthropic().messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
                max_tokens=16000,  # thinking is on by default and counts against this; five sentences need far less
                messages=[{"role": "user", "content": PROMPT + _facts(results)}],
            )
            if resp.stop_reason != "end_turn":
                raise RuntimeError(f"reply ended with stop_reason={resp.stop_reason}")
            text = next((b.text for b in resp.content if b.type == "text"), None)  # the first block may be thinking
            if not text or not text.strip():
                raise RuntimeError("reply had no text block")
            return text.strip(), "claude"
        except Exception as e:  # any API or install problem falls back to the template, and the label says why
            return template(results), f"template (Claude unavailable: {type(e).__name__}: {str(e)[:100]})"
    return template(results), "template"
