#!/usr/bin/env python3
"""
Command-line splitter (same engine as the app).

    python split_pdf.py file.pdf
    python split_pdf.py C:\\Certificates -o C:\\Split
    python split_pdf.py folder --no-subfolder --pattern "{name}-{page}"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import split
from core.common import collect_pdfs


def main() -> None:
    p = argparse.ArgumentParser(description="Split PDFs into single-page PDFs.")
    p.add_argument("inputs", nargs="+", help="PDF files and/or folders")
    p.add_argument("-o", "--output", help="Output folder (default: next to each PDF)")
    p.add_argument("--no-subfolder", action="store_true", help="Don't create a subfolder per PDF")
    p.add_argument("--pattern", default=split.DEFAULT_PATTERN, help=split.PATTERN_HELP)
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    p.add_argument("-r", "--recursive", action="store_true", help="Include subfolders")
    args = p.parse_args()

    if error := split.validate_pattern(args.pattern):
        sys.exit(error)

    options = split.SplitOptions(
        output_dir=Path(args.output) if args.output else None,
        subfolder=not args.no_subfolder,
        pattern=args.pattern,
        overwrite=args.overwrite,
    )
    pdfs = collect_pdfs(args.inputs, recursive=args.recursive)
    if not pdfs:
        sys.exit("No PDF files found.")

    total = 0
    for pdf in pdfs:
        try:
            out_dir, n = split.split_pdf(pdf, options)
            total += n
            print(f"{pdf.name}: {n} pages -> {out_dir}")
        except Exception as e:
            print(f"ERROR with {pdf.name}: {e}", file=sys.stderr)
    print(f"Done: {len(pdfs)} file(s), {total} page(s) exported.")


if __name__ == "__main__":
    main()
