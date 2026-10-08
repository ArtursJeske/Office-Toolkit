"""
Batch-rename files with a list of rules, applied from top to bottom.

Rules work on the name WITHOUT the extension (".pdf" stays untouched).
Renaming is done in two steps (name -> temporary name -> new name), so
swaps like A->B and B->A, or case-only changes on Windows, work safely.
"""

from __future__ import annotations

import fnmatch
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# key: (menu label, first field label, second field label, uses "match case")
OPERATIONS: dict[str, tuple[str, str | None, str | None, bool]] = {
    "add_prefix":    ("Add prefix",                     "Text",   None,           False),
    "add_suffix":    ("Add suffix (before extension)",  "Text",   None,           False),
    "remove_prefix": ("Remove prefix",                  "Text",   None,           True),
    "remove_suffix": ("Remove suffix",                  "Text",   None,           True),
    "insert_before": ("Insert text before…",            "Before", "Insert",       True),
    "insert_after":  ("Insert text after…",             "After",  "Insert",       True),
    "remove_before": ("Remove everything before…",      "Text",   None,           True),
    "remove_after":  ("Remove everything after…",       "Text",   None,           True),
    "replace":       ("Replace text",                   "Find",   "Replace with", True),
    "remove_text":   ("Remove text",                    "Text",   None,           True),
    "remove_first":  ("Remove first N characters",      "N",      None,           False),
    "remove_last":   ("Remove last N characters",       "N",      None,           False),
    "trim":          ("Clean up spaces",                None,     None,           False),
    "upper":         ("To UPPERCASE",                   None,     None,           False),
    "lower":         ("To lowercase",                   None,     None,           False),
}
NUMERIC_OPS = {"remove_first", "remove_last"}


# ====================================================================== rules

@dataclass
class Rule:
    op: str
    a: str = ""            # first field (text / anchor / N)
    b: str = ""            # second field (text to insert / replacement)
    case: bool = False     # match case
    enabled: bool = True

    def describe(self) -> str:
        a, b = self.a, self.b
        text = {
            "add_prefix":    f"Add prefix “{a}”",
            "add_suffix":    f"Add suffix “{a}”",
            "remove_prefix": f"Remove prefix “{a}”",
            "remove_suffix": f"Remove suffix “{a}”",
            "insert_before": f"Insert “{b}” before “{a}”",
            "insert_after":  f"Insert “{b}” after “{a}”",
            "remove_before": f"Remove everything before “{a}”",
            "remove_after":  f"Remove everything after “{a}”",
            "replace":       f"Replace “{a}” with “{b}”",
            "remove_text":   f"Remove “{a}”",
            "remove_first":  f"Remove first {a} character(s)",
            "remove_last":   f"Remove last {a} character(s)",
        }.get(self.op, OPERATIONS[self.op][0])
        if OPERATIONS[self.op][3] and self.case:
            text += "  (match case)"
        return text

    def validate(self) -> str | None:
        if self.op not in OPERATIONS:
            return f"Unknown operation: {self.op}"
        _label, fa, fb, _ = OPERATIONS[self.op]
        if self.op in NUMERIC_OPS:
            if not self.a.isdigit() or int(self.a) <= 0:
                return "N must be a whole number greater than 0."
        elif fa and self.a == "":
            return f"“{fa}” must not be empty."
        if self.op in ("insert_before", "insert_after") and self.b == "":
            return "“Insert” must not be empty."
        return None

    def to_dict(self) -> dict:
        return {"op": self.op, "a": self.a, "b": self.b, "case": self.case, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        return cls(op=d["op"], a=d.get("a", ""), b=d.get("b", ""),
                   case=bool(d.get("case", False)), enabled=bool(d.get("enabled", True)))


def _starts(s: str, t: str, case: bool) -> bool:
    return s.startswith(t) if case else s.lower().startswith(t.lower())


def _ends(s: str, t: str, case: bool) -> bool:
    return s.endswith(t) if case else s.lower().endswith(t.lower())


def apply_rule(stem: str, r: Rule) -> str:
    """Apply one rule to a file name without extension."""
    a, b, op = r.a, r.b, r.op
    flags = 0 if r.case else re.IGNORECASE
    match = re.search(re.escape(a), stem, flags) if a else None

    if op == "add_prefix":
        return a + stem
    if op == "add_suffix":
        return stem + a
    if op == "remove_prefix":
        return stem[len(a):] if a and _starts(stem, a, r.case) else stem
    if op == "remove_suffix":
        return stem[: -len(a)] if a and _ends(stem, a, r.case) else stem
    if op == "insert_before":
        return stem[: match.start()] + b + stem[match.start():] if match else stem
    if op == "insert_after":
        return stem[: match.end()] + b + stem[match.end():] if match else stem
    if op == "remove_before":
        return stem[match.start():] if match else stem
    if op == "remove_after":
        return stem[: match.end()] if match else stem
    if op in ("replace", "remove_text"):
        new = b if op == "replace" else ""
        return re.sub(re.escape(a), lambda _m: new, stem, flags=flags) if a else stem
    if op == "remove_first":
        return stem[int(a or 0):]
    if op == "remove_last":
        n = int(a or 0)
        return stem[:-n] if n else stem
    if op == "trim":
        return " ".join(stem.split())
    if op == "upper":
        return stem.upper()
    if op == "lower":
        return stem.lower()
    return stem


def split_name(name: str) -> tuple[str, str]:
    ext = Path(name).suffix
    return (name[: -len(ext)], ext) if ext else (name, "")


def new_name(path: Path, rules: Iterable[Rule]) -> str:
    stem, ext = split_name(path.name)
    for r in rules:
        if r.enabled:
            stem = apply_rule(stem, r)
    return stem + ext


# ====================================================================== files

def list_files(paths: Iterable[str | Path], patterns: str = "*", recursive: bool = False) -> list[Path]:
    """Files inside the given folders that match patterns like "*.pdf; *.docx".
    Files that were added one by one are always included."""
    pats = [p.lower() for p in re.split(r"[;,\s]+", patterns or "") if p] or ["*"]
    result: dict[str, Path] = {}
    for item in paths:
        p = Path(item)
        if p.is_dir():
            for f in (p.rglob("*") if recursive else p.iterdir()):
                if f.is_file() and any(fnmatch.fnmatch(f.name.lower(), pat) for pat in pats):
                    result.setdefault(str(f).lower(), f)
        elif p.is_file():
            result.setdefault(str(p).lower(), p)
    return sorted(result.values(), key=lambda f: (str(f.parent).lower(), f.name.lower()))


# ====================================================================== plan

STATUS_TEXT = {
    "rename":    "→ Will be renamed",
    "same":      "Unchanged",
    "duplicate": "⚠ Same new name as another file",
    "exists":    "⚠ A file with this name already exists",
    "invalid":   "⚠ Invalid file name",
}


@dataclass
class Plan:
    src: Path
    new_name: str
    status: str

    @property
    def target(self) -> Path:
        return self.src.with_name(self.new_name)

    @property
    def ok(self) -> bool:
        return self.status == "rename"


def _invalid(name: str) -> bool:
    stem, _ext = split_name(name)
    return (not stem.strip() or bool(_INVALID.search(name))
            or name.endswith((" ", ".")) or name.startswith(" "))


def plan_renames(files: list[Path], rules: list[Rule]) -> list[Plan]:
    plans: list[Plan] = []
    for f in files:
        nn = new_name(f, rules)
        if nn == f.name:
            status = "same"
        elif _invalid(nn):
            status = "invalid"
        else:
            status = "rename"
        plans.append(Plan(f, nn, status))

    key = lambda p: str(p).lower()  # Windows: names are case-insensitive
    sources = {key(p.src) for p in plans}

    # where every file ends up; two files must not end up in the same place
    final_count: dict[str, int] = {}
    for p in plans:
        k = key(p.target if p.ok else p.src)
        final_count[k] = final_count.get(k, 0) + 1
    for p in plans:
        if p.ok and final_count[key(p.target)] > 1:
            p.status = "duplicate"

    # a file outside this batch already has the new name
    for p in plans:
        if p.ok and p.target.exists() and key(p.target) not in sources:
            p.status = "exists"
    return plans


# ====================================================================== execute

def rename_many(
    moves: list[tuple[Path, Path]],
    on_step: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[list[tuple[Path, Path]], list[str]]:
    """Rename (src, dst) pairs safely. Returns (done pairs, error messages)."""
    done: list[tuple[Path, Path]] = []
    errors: list[str] = []

    # step 1: move everything to temporary names
    temps: list[tuple[Path, Path, Path]] = []
    for src, dst in moves:
        if should_stop and should_stop():
            break  # nothing after this point has been touched
        tmp = src.with_name(f"~rn{uuid.uuid4().hex[:10]}{src.suffix}")
        try:
            src.rename(tmp)
            temps.append((src, tmp, dst))
        except OSError as e:
            errors.append(f"{src.name}: {e.strerror or e}")

    # step 2: temporary -> final name (always completed, never cancelled halfway)
    for i, (src, tmp, dst) in enumerate(temps, start=1):
        try:
            if dst.exists():
                raise FileExistsError(f"“{dst.name}” already exists")
            tmp.rename(dst)
            done.append((src, dst))
        except OSError as e:
            errors.append(f"{src.name}: {getattr(e, 'strerror', None) or e}")
            try:
                tmp.rename(src)
            except OSError:
                errors.append(f"{src.name} was left as {tmp.name} — please rename it by hand")
        if on_step:
            on_step(i, len(temps))
    return done, errors
