"""Refresh `examples/Ar-07-Lys.xml` from the authoritative corpus copy.

The app ships sample plays so that it runs without the corpus checked out, but
a copy is not a second edition to be maintained: the corpus file is the
text, and this script is the only way the sample should ever change.

    python tests/refresh_example.py            # copy, then regenerate
    python tests/refresh_example.py --dry-run  # report drift, change nothing

It copies the file and then regenerates the baseline, printing what moved in
the fingerprint, so an editorial change to the play is read once rather than
appearing later as an unexplained test failure.

`test_baseline.py::test_example_still_matches_the_corpus` fails when the two
have diverged, so a refresh that is due cannot be forgotten.

The second sample, `examples/Ar-01-Ach.xml`, is copied in the same run.  No
baseline depends on it, so there is nothing to regenerate for it.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_DIR = HERE.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(HERE))

EXAMPLE = APP_DIR / "examples" / "Ar-07-Lys.xml"
CORPUS = (APP_DIR.parent / "01-SkeneGraph-corpus" / "comedy"
          / "Ar-07-Lys.xml")
# Samples that are only copied: no baseline is computed from them.
OTHER_SAMPLES = ("Ar-01-Ach.xml",)


def refresh_other_samples(dry_run: bool) -> None:
    for name in OTHER_SAMPLES:
        source, sample = CORPUS.parent / name, EXAMPLE.parent / name
        if not source.is_file():
            print(f"No corpus copy of {name}; left as it is.", file=sys.stderr)
        elif sample.is_file() and sample.read_bytes() == source.read_bytes():
            print(f"{name} is already the corpus text.")
        elif dry_run:
            print(f"{name} differs from the corpus text.")
        else:
            shutil.copy2(source, sample)
            print(f"Copied {name} -> examples/{name}")


def fingerprint_of(path: Path) -> dict:
    from baseline_util import compute_fingerprint
    from parser import parse_play
    return compute_fingerprint(parse_play(path))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what a refresh would change, and stop")
    args = ap.parse_args()

    if not CORPUS.is_file():
        print(f"No corpus copy at {CORPUS}", file=sys.stderr)
        print("Nothing to refresh from; the sample is left as it is.",
              file=sys.stderr)
        return 1

    refresh_other_samples(args.dry_run)

    before = fingerprint_of(EXAMPLE) if EXAMPLE.is_file() else {}
    after = fingerprint_of(CORPUS)
    moved = {k: (before.get(k), after.get(k))
             for k in sorted(set(before) | set(after))
             if before.get(k) != after.get(k)}

    if not moved and EXAMPLE.is_file() \
            and EXAMPLE.read_bytes() == CORPUS.read_bytes():
        print("The sample is already the corpus text; nothing to do.")
        return 0

    print(f"{len(moved)} of {len(set(before) | set(after))} fingerprint "
          f"quantities differ:")
    for key, (old, new) in list(moved.items())[:40]:
        print(f"  {key:<40} {old!s:>14} -> {new!s:>14}")
    if len(moved) > 40:
        print(f"  ... and {len(moved) - 40} more")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    shutil.copy2(CORPUS, EXAMPLE)
    print(f"\nCopied {CORPUS.name} -> examples/{EXAMPLE.name}")

    import regen_baseline
    regen_baseline.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
