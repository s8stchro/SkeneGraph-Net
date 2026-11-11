"""Regenerate the demo-play baseline.

Run this after an *intentional* change to `examples/Ar-07-Lys.xml` or to a
metric definition, then read the printed diff before committing:

    python tests/regen_baseline.py

It rewrites `tests/baseline_demo.json` and reports what moved.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
APP_DIR = TESTS_DIR.parent
for path in (str(APP_DIR), str(TESTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from baseline_util import compute_fingerprint  # noqa: E402
from parser import parse_play  # noqa: E402

BASELINE = TESTS_DIR / "baseline_demo.json"
DEMO = APP_DIR / "examples" / "Ar-07-Lys.xml"


def main() -> int:
    old = {}
    if BASELINE.is_file():
        old = json.loads(BASELINE.read_text(encoding="utf-8"))

    new = compute_fingerprint(parse_play(DEMO))

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in set(new) & set(old) if new[k] != old[k])

    BASELINE.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")

    if not old:
        print(f"created {BASELINE.name} with {len(new)} entries")
        return 0

    if not (added or removed or changed):
        print("baseline unchanged")
        return 0

    for key in changed:
        print(f"  changed  {key}: {old[key]!r} -> {new[key]!r}")
    for key in added:
        print(f"  added    {key}: {new[key]!r}")
    for key in removed:
        print(f"  removed  {key}: {old[key]!r}")
    print(f"\nwrote {BASELINE.name} "
          f"({len(changed)} changed, {len(added)} added, {len(removed)} removed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
