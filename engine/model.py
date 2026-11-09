"""The ledger: every figure carries its source; anything unknown stays None with a reason."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


class NotComputed(Exception):
    """An input is missing or flagged, so the calculation refuses to run."""


@dataclass
class Figure:
    key: str
    value: float | None
    source: str  # "file | sheet | cell"
    reason: str | None = None  # set whenever value is None
    reported: float | None = None  # what the file said, kept for the audit trail when we null it


@dataclass
class Issue:
    kind: str
    key: str
    message: str


@dataclass
class Ledger:
    figs: dict[str, Figure] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    used: set[str] = field(default_factory=set)

    def put(self, key: str, value: float, source: str) -> None:
        old = self.figs.get(key)
        if old is None:
            self.figs[key] = Figure(key, value, source)
        elif old.value is not None:  # two different cells claim the same figure: trust neither
            self.flag(key, "duplicate_figure", f"{key} appears twice ({old.source} and {source}), so neither is used")

    def flag(self, key: str, kind: str, reason: str, source: str = "") -> None:
        """Mark a figure as unusable. The value becomes None; it is never replaced by an estimate."""
        f = self.figs.get(key)
        if f is None:
            f = self.figs[key] = Figure(key, None, source)
        elif f.value is None:
            return
        else:
            f.reported, f.value = f.value, None
        f.reason = reason
        self.issues.append(Issue(kind, key, reason))

    def value(self, key: str) -> float | None:
        f = self.figs.get(key)
        return None if f is None else f.value

    def get_all(self, keys: list[str]) -> dict[str, float]:
        """Return every value, or raise NotComputed naming every figure that is missing or flagged."""
        self.used.update(keys)
        bad, out = [], {}
        for k in keys:
            f = self.figs.get(k)
            if f is None:
                bad.append(f"{k} (not found in any input file)")
            elif f.value is None:
                bad.append(f"{k} ({f.reason})")
            else:
                out[k] = f.value
        if bad:
            raise NotComputed("missing " + "; ".join(bad))
        return out

    def get(self, key: str) -> float:
        return self.get_all([key])[key]

    def need_meta(self, key: str) -> Any:
        if key not in self.meta:
            raise NotComputed(f"missing {key} (no usable input for it)")
        return self.meta[key]

    def source_text(self, keys: Iterable[str], limit: int = 4) -> str:
        """'file | sheet: B4, B6' for the figures behind a result, cells truncated after `limit`."""
        cells_by_place: dict[str, list[str]] = {}
        for k in sorted(keys):
            f = self.figs.get(k)
            if f and f.source:
                parts = f.source.split(" | ")
                cells = cells_by_place.setdefault(" | ".join(parts[:2]), [])
                if len(parts) > 2:
                    cells.append(parts[2])
        out = []
        for place, cells in cells_by_place.items():
            shown = ", ".join(cells[:limit]) + (f" +{len(cells) - limit} more" if len(cells) > limit else "")
            out.append(f"{place}: {shown}" if shown else place)
        return "; ".join(out)
