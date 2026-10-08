"""Helpers shared by all tools (no UI code here)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def open_pdf(path: Path | str) -> PdfReader:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")  # works for PDFs that only have an owner password
    return reader


def page_count(path: Path | str) -> int:
    return len(open_pdf(path).pages)


def is_pdf(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() == ".pdf"


def collect_pdfs(paths: Iterable[str | Path], recursive: bool = False) -> list[Path]:
    """Turn a mix of files and folders into a list of unique PDF files."""
    result: list[Path] = []
    seen: set[str] = set()
    for item in paths:
        p = Path(item)
        if p.is_dir():
            found = sorted(x for x in (p.rglob("*") if recursive else p.iterdir()) if is_pdf(x))
        elif is_pdf(p):
            found = [p]
        else:
            found = []
        for f in found:
            key = str(f.resolve()).lower()
            if key not in seen:
                seen.add(key)
                result.append(f)
    return result


def safe_name(stem: str, fallback: str = "file") -> str:
    return _INVALID_CHARS.sub("_", stem).strip(" .") or fallback


def unique_path(path: Path) -> Path:
    """path, or path with ' (2)', ' (3)'... if it already exists."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1
