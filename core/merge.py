"""
Merge English + Latvian PDF pairs.

    4014-12x50.pdf  +  4014-12x50_LV.pdf   ->   4014-12x50_ENG_LV.pdf

Files are matched by name (case-insensitive). The LV file is recognised by its
suffix (default "_LV"). Files that already end with the output suffix
(default "_ENG_LV") are ignored, so earlier results are never merged again.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfWriter

from .common import open_pdf, safe_name, unique_path

DEFAULT_LV_SUFFIX = "_LV"
DEFAULT_OUT_SUFFIX = "_ENG_LV"


@dataclass
class Pair:
    name: str                 # common name, e.g. "4014-12x50"
    eng: Path | None = None
    lv: Path | None = None
    problem: str = ""         # empty = ready to merge

    @property
    def ok(self) -> bool:
        return self.eng is not None and self.lv is not None and not self.problem


@dataclass
class MergeOptions:
    output_dir: Path | None = None    # None = same folder as the ENG file
    out_suffix: str = DEFAULT_OUT_SUFFIX
    lv_first: bool = False            # False = ENG pages first, then LV
    overwrite: bool = False


def _ends_with(stem: str, suffix: str) -> bool:
    return bool(suffix) and stem.lower().endswith(suffix.lower()) and len(stem) > len(suffix)


def find_pairs(pdfs: list[Path], lv_suffix: str = DEFAULT_LV_SUFFIX,
               out_suffix: str = DEFAULT_OUT_SUFFIX) -> list[Pair]:
    """Group PDFs into ENG/LV pairs. Unmatched files are returned with a problem text."""
    eng: dict[str, list[Path]] = {}
    lv: dict[str, list[Path]] = {}
    names: dict[str, str] = {}

    for p in pdfs:
        stem = p.stem
        if _ends_with(stem, out_suffix):
            continue  # already merged earlier
        if _ends_with(stem, lv_suffix):
            base = stem[: -len(lv_suffix)].strip()
            lv.setdefault(base.lower(), []).append(p)
            names.setdefault(base.lower(), base)
        else:
            eng.setdefault(stem.strip().lower(), []).append(p)
            names[stem.strip().lower()] = stem.strip()  # prefer the ENG spelling

    pairs: list[Pair] = []
    for key in sorted(names, key=str.lower):
        e, l = eng.get(key, []), lv.get(key, [])
        pair = Pair(name=names[key], eng=e[0] if e else None, lv=l[0] if l else None)
        if len(e) > 1:
            pair.problem = f"{len(e)} ENG files with this name"
        elif len(l) > 1:
            pair.problem = f"{len(l)} LV files with this name"
        elif not e:
            pair.problem = "No ENG file"
        elif not l:
            pair.problem = "No LV file"
        pairs.append(pair)
    return pairs


def output_path(pair: Pair, options: MergeOptions) -> Path:
    out_dir = options.output_dir or pair.eng.parent
    return out_dir / (safe_name(pair.eng.stem + options.out_suffix) + ".pdf")


def merge_pair(pair: Pair, options: MergeOptions) -> Path:
    """Merge one pair and return the written file."""
    if not pair.ok:
        raise ValueError(pair.problem or "Incomplete pair")
    target = output_path(pair, options)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not options.overwrite:
        target = unique_path(target)

    order = [pair.lv, pair.eng] if options.lv_first else [pair.eng, pair.lv]
    writer = PdfWriter()
    for src in order:
        writer.append(open_pdf(src))
    with open(target, "wb") as f:
        writer.write(f)
    return target
