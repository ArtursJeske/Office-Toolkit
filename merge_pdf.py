#!/usr/bin/env python3
"""
Command-line ENG + LV merger (same engine as the app).

    python merge_pdf.py C:\\ENG C:\\LV                  # results next to the ENG files
    python merge_pdf.py C:\\Certs -o C:\\Merged          # one folder with both languages
    python merge_pdf.py C:\\ENG C:\\LV --dry-run         # only show what would be merged
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import merge
from core.common import collect_pdfs


def main() -> None:
    p = argparse.ArgumentParser(description="Merge ENG + LV PDF pairs into <name>_ENG_LV.pdf")
    p.add_argument("inputs", nargs="+", help="Folders and/or PDF files")
    p.add_argument("-o", "--output", help="Output folder (default: next to the ENG file)")
    p.add_argument("--lv-suffix", default=merge.DEFAULT_LV_SUFFIX)
    p.add_argument("--out-suffix", default=merge.DEFAULT_OUT_SUFFIX)
    p.add_argument("--lv-first", action="store_true", help="Put LV pages before ENG pages")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("-r", "--recursive", action="store_true", help="Include subfolders")
    p.add_argument("--dry-run", action="store_true", help="Only list the pairs")
    args = p.parse_args()

    pdfs = collect_pdfs(args.inputs, recursive=args.recursive)
    pairs = merge.find_pairs(pdfs, args.lv_suffix, args.out_suffix)
    options = merge.MergeOptions(
        output_dir=Path(args.output) if args.output else None,
        out_suffix=args.out_suffix, lv_first=args.lv_first, overwrite=args.overwrite,
    )

    done = 0
    for pair in pairs:
        if not pair.ok:
            print(f"SKIP  {pair.name}: {pair.problem}")
        elif args.dry_run:
            print(f"PAIR  {pair.eng.name} + {pair.lv.name}")
        else:
            try:
                print(f"OK    {merge.merge_pair(pair, options)}")
                done += 1
            except Exception as e:
                print(f"ERROR {pair.name}: {e}", file=sys.stderr)
    ready = sum(x.ok for x in pairs)
    print(f"\n{ready} pair(s) found, {done} merged, {len(pairs) - ready} skipped.")


if __name__ == "__main__":
    main()
