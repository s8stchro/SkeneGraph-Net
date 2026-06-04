#!/usr/bin/env python3
"""Migrate <move> elements from @subtype to @ana.

Rewrites every

    <move ... subtype="x y z" ...>

to

    <move ... ana="#x #y #z" ...>

in TEI files.  Uses regex substitution rather than an XML round-trip so
that formatting (indentation, comments, whitespace between attributes)
is preserved exactly.  Writes a .bak file alongside each modified file.

If a <move> already has both @ana and @subtype, the tokens are merged
into the existing @ana value (de-duplicated, # prefix added).

Usage
-----
    python migrate_subtype_to_ana.py <path>

`<path>` is either a single TEI file or a directory tree (recursive,
*.xml).  Use --dry-run to preview the changes without writing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Tuple


# A <move> element, with its full attribute list, including possible
# self-closing slash.  Greedy `.*?` plus `re.DOTALL` lets the element
# span multiple lines (rare but legal).
_MOVE_RE = re.compile(r'<move\b([^>]*?)(/?)>', flags=re.DOTALL)

# Capture an attribute value, allowing for either single or double quotes.
_SUBTYPE_RE = re.compile(r'''\bsubtype\s*=\s*(?:"([^"]*)"|'([^']*)')''')
_ANA_RE     = re.compile(r'''\bana\s*=\s*(?:"([^"]*)"|'([^']*)')''')


def _tokenise(raw: str) -> list:
    """Split a space-separated attribute value into bare tokens
    (leading `#` stripped if present)."""
    return [t.lstrip("#") for t in raw.split() if t.strip()]


def _rewrite_move(attr_str: str) -> Tuple[str, bool]:
    """Return (new_attr_str, changed?) for one <move>'s attribute list.

    Merges @subtype tokens into @ana with `#`-prefixes; removes @subtype.
    If neither attribute is present, returns the input unchanged.
    """
    sub_m = _SUBTYPE_RE.search(attr_str)
    if not sub_m:
        return attr_str, False
    sub_raw = sub_m.group(1) if sub_m.group(1) is not None else sub_m.group(2)
    sub_toks = _tokenise(sub_raw)
    if not sub_toks:
        # Empty subtype: just drop it.
        new = _SUBTYPE_RE.sub("", attr_str)
        return _clean_spaces(new), True

    ana_m = _ANA_RE.search(attr_str)
    if ana_m:
        ana_raw = ana_m.group(1) if ana_m.group(1) is not None else ana_m.group(2)
        ana_toks = _tokenise(ana_raw)
    else:
        ana_toks = []

    # Merge, preserving insertion order: existing @ana first, then new
    # tokens from @subtype that weren't already present.
    seen = set(ana_toks)
    for t in sub_toks:
        if t not in seen:
            ana_toks.append(t)
            seen.add(t)
    new_ana_val = " ".join("#" + t for t in ana_toks)

    if ana_m:
        # Replace existing @ana value, then drop @subtype.
        new = _ANA_RE.sub(f'ana="{new_ana_val}"', attr_str, count=1)
        new = _SUBTYPE_RE.sub("", new, count=1)
    else:
        # Replace @subtype with @ana in place (so the new attribute lands
        # where the old one was -- preserves the file's attribute order).
        new = _SUBTYPE_RE.sub(f'ana="{new_ana_val}"', attr_str, count=1)
    return _clean_spaces(new), True


def _clean_spaces(s: str) -> str:
    """Collapse runs of whitespace introduced by removing an attribute
    in the middle of the attribute list (e.g. ` subtype="x" ` -> `  `)."""
    return re.sub(r"\s{2,}", " ", s)


def _process_text(text: str) -> Tuple[str, int]:
    """Apply the rewrite across every <move> in the file.  Returns
    (new_text, count_of_moves_changed)."""
    changes = [0]
    def repl(m):
        attr_str, slash = m.group(1), m.group(2)
        new_attr, changed = _rewrite_move(attr_str)
        if changed:
            changes[0] += 1
        return f"<move{new_attr}{slash}>"
    new_text = _MOVE_RE.sub(repl, text)
    return new_text, changes[0]


def migrate_file(path: Path, dry_run: bool = False) -> int:
    """Migrate one file in place (with .bak backup).  Returns the number
    of <move> elements changed."""
    text = path.read_text(encoding="utf-8")
    new_text, n = _process_text(text)
    if n and not dry_run:
        path.with_suffix(path.suffix + ".bak").write_text(text, encoding="utf-8")
        path.write_text(new_text, encoding="utf-8")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="TEI file or directory (recursive *.xml)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report changes without writing files")
    args = ap.parse_args(argv)

    p = Path(args.path)
    if p.is_file():
        files = [p]
    else:
        files = sorted(p.rglob("*.xml"))
    if not files:
        print(f"No XML files under {p}", file=sys.stderr)
        return 1

    total_moves = 0
    total_files = 0
    for f in files:
        n = migrate_file(f, dry_run=args.dry_run)
        if n:
            total_files += 1
            print(f"{f}: {n} <move> elements migrated")
        total_moves += n
    print(f"\nTotal: {total_moves} moves migrated across {total_files} files"
          f"{' (dry-run, nothing written)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
