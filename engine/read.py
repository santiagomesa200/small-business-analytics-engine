"""Read every file into plain rows. No interpretation yet."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from pypdf import PdfReader


@dataclass
class Sheet:
    file: str
    name: str
    rows: list[list]
    error: str = ""  # set when the file could not be read; rows is then empty

    def src(self, r: int | None = None, c: int | None = None) -> str:
        if r is None:
            return f"{self.file} | {self.name}"
        if self.file.endswith(".pdf"):
            return f"{self.file} | {self.name} | line {r + 1}"
        return f"{self.file} | {self.name} | {get_column_letter((c or 0) + 1)}{r + 1}"


def read_folder(folder: str | Path) -> list[Sheet]:
    sheets: list[Sheet] = []
    for p in sorted(Path(folder).iterdir()):
        try:
            sheets += _read_file(p)
        except Exception as e:  # any parser failure on a bad file: keep the name and the reason, skip the content
            sheets.append(Sheet(p.name, "unreadable", [], error=type(e).__name__))
    return sheets


def _read_file(p: Path) -> list[Sheet]:
    ext = p.suffix.lower()
    if ext == ".xlsx":
        return [Sheet(p.name, ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in load_workbook(p, data_only=True)]
    if ext == ".csv":
        with open(p, newline="") as f:
            return [Sheet(p.name, "table", [r for r in csv.reader(f)])]
    if ext == ".pdf":
        pages = PdfReader(p).pages
        lines = lambda page: [ln.strip() for ln in (page.extract_text() or "").splitlines() if ln.strip()]
        return [Sheet(p.name, f"page {i + 1}", [[ln] for ln in lines(page)]) for i, page in enumerate(pages)]
    return []
