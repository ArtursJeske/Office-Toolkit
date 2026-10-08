"""Split PDFs into single-page PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pypdf import PdfWriter

from .common import open_pdf, safe_name, unique_path

DEFAULT_PATTERN = "{name}_page_{page}"
PATTERN_HELP = "{name} = original file name, {page} = page number, {total} = page count"


@dataclass
class SplitOptions:
    output_dir: Path | None = None   # None = same folder as the original PDF
    subfolder: bool = True           # put each PDF's pages in its own subfolder
    pattern: str = DEFAULT_PATTERN   # output file name pattern (without .pdf)
    overwrite: bool = False          # False = add " (2)", " (3)"... if file exists


def validate_pattern(pattern: str) -> str | None:
    """Return an error message, or None if the pattern is usable."""
    if not pattern.strip():
        return "File name pattern is empty."
    if "{page}" not in pattern:
        return "File name pattern must contain {page}, otherwise all pages get the same name."
    try:
        pattern.format(name="x", page="001", total=1)
    except (KeyError, IndexError, ValueError) as e:
        return f"Invalid file name pattern: {e}. Allowed fields: {PATTERN_HELP}"
    return None


def make_filename(pattern: str, name: str, page: int, total: int) -> str:
    digits = max(3, len(str(total)))
    stem = pattern.format(name=name, page=str(page).zfill(digits), total=total)
    return safe_name(stem, f"page_{page}") + ".pdf"


def split_pdf(
    pdf_path: Path | str,
    options: SplitOptions,
    on_page: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[Path, int]:
    """Save every page as its own PDF. Returns (output folder, pages written)."""
    pdf_path = Path(pdf_path)
    reader = open_pdf(pdf_path)
    total = len(reader.pages)

    base = options.output_dir or pdf_path.parent
    out_dir = base / pdf_path.stem if options.subfolder else base
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for i, page in enumerate(reader.pages, start=1):
        if should_stop and should_stop():
            break
        writer = PdfWriter()
        writer.add_page(page)
        target = out_dir / make_filename(options.pattern, pdf_path.stem, i, total)
        if not options.overwrite:
            target = unique_path(target)
        with open(target, "wb") as f:
            writer.write(f)
        written += 1
        if on_page:
            on_page(i, total)

    return out_dir, written
