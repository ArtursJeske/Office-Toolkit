# Changelog

All notable changes to this project are documented here.

## [2.2] — 2026-10-08

### Changed
- Project renamed from **PDF Tools** to **Office Toolkit**.
- Settings from the previous version are carried over automatically on first start.

## [2.1] — 2026-10-07

### Added
- **File Renamer** — rule-based batch renaming with live preview, conflict detection and undo.
- Shared file list now accepts any file type (used by the renamer).

## [2.0] — 2026-10-07

### Added
- Sidebar navigation; each tool opens on its own page.
- **PDF Merger (ENG + LV)** — matches English and Latvian files by name and merges each pair into `<name>_ENG_LV.pdf`.
- Command-line merger `merge_pdf.py`.

### Changed
- Code split into `core/` (logic) and `ui/` (interface) to make adding tools easier.

## [1.0] — 2026-10-07

### Added
- **PDF Splitter** — splits PDFs into single-page files, with drag & drop, custom output folder and file name pattern.
- Command-line splitter `split_pdf.py`.
