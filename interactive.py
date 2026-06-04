"""Interactive guided mode for the SkeneGraph-Net.

Launched when the user runs `python app.py` with no subcommand: prompts
for the basic two-axis choice (single play vs corpus) and the input
path, then defers to the existing `analyze_one` / `cmd_corpus` pipeline.

Kept deliberately minimal -- all methodological toggles (mute mode,
partOf aggregation, segmentation tab) are exposed in the dashboard
itself, so the prompt only collects what the pipeline needs to start:
the input path and an optional output directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Tiny prompt primitives
# ---------------------------------------------------------------------------

def _ask(prompt: str, options: List[Tuple[str, str]], default: int = 0) -> str:
    """Numbered-choice prompt.  Returns the chosen option's value string."""
    print(f"\n  {prompt}")
    for i, (_, desc) in enumerate(options):
        marker = " *" if i == default else "  "
        print(f"  {marker} [{i + 1}] {desc}")
    while True:
        choice = input(f"  Choice [{default + 1}]: ").strip()
        if choice == "":
            return options[default][0]
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(options)}")


def _ask_text(prompt: str, default: str = "") -> str:
    """Free-text prompt with optional default."""
    if default:
        val = input(f"  {prompt} [{default}]: ").strip()
        return val if val else default
    while True:
        val = input(f"  {prompt}: ").strip()
        if val:
            return val
        print("  This field is required.")


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    val = input(f"  {prompt} {suffix}: ").strip().lower()
    if val == "":
        return default
    return val in ("y", "yes")


def _print_header() -> None:
    print()
    print("=" * 60)
    print("  SkeneGraph-Net  --  Interactive Mode")
    print("  DraCor-style network analysis for Greek drama")
    print("=" * 60)
    print("\n  All methodological toggles (mute mode, partOf aggregation,")
    print("  segmentation, edge rule) are exposed in the generated dashboard.")
    print("  This prompt only collects the input path.")


# ---------------------------------------------------------------------------
# The two flows
# ---------------------------------------------------------------------------

def _interactive_analyze() -> Optional[dict]:
    """Collect args for `analyze_one` on a single TEI file."""
    print("\n  --- Single play analysis ---")
    filepath = _ask_text("Path to TEI XML file")
    if not os.path.isfile(filepath):
        print(f"\n  Warning: file not found: {filepath}")
        if not _ask_yes_no("Continue anyway?", default=False):
            return None
    output_dir = _ask_text("Output directory", default="output")
    return {"file": filepath, "out": output_dir}


def _interactive_corpus() -> Optional[dict]:
    """Collect args for `cmd_corpus` on one or more paths.

    Each path may be a directory of TEI XML files or a single XML file;
    paths are entered one per prompt and the user signals completion by
    pressing Enter on an empty line.  This keeps the simple single-
    directory case ergonomic (one path + Enter twice) while supporting
    arbitrary multi-path corpora (a directory + named files, two
    directories, three individual plays, etc.).  All resolution and
    deduplication happens later in `_resolve_corpus_paths` in app.py.
    """
    print("\n  --- Corpus analysis ---")
    print("  Enter paths one at a time.  Each may be a directory of TEI XML")
    print("  files or a single XML file.  Press Enter on an empty line when done.")

    paths: List[str] = []
    total_xml = 0
    while True:
        idx = len(paths) + 1
        # Prompt without using the required-field path of _ask_text: an
        # empty entry is the signal for "done", except on the very first
        # path where we still require at least one entry.
        raw = input(f"  Path {idx}{' (Enter to finish)' if paths else ''}: ").strip()
        # Strip enclosing quotes that some terminals add when pasting paths.
        if raw and ((raw.startswith('"') and raw.endswith('"'))
                    or (raw.startswith("'") and raw.endswith("'"))):
            raw = raw[1:-1]
        if not raw:
            if not paths:
                print("  Please enter at least one path.")
                continue
            break
        p = Path(raw)
        if not p.exists():
            print(f"  Warning: path not found: {raw}")
            if not _ask_yes_no("  Add it anyway?", default=False):
                continue
            paths.append(raw)
            continue
        if p.is_dir():
            matches = list(p.glob("*.xml"))
            if matches:
                print(f"    -> directory, {len(matches)} .xml files")
                total_xml += len(matches)
            else:
                print(f"    -> directory, no .xml files (will warn at run time)")
        elif p.is_file():
            print(f"    -> single file")
            total_xml += 1
        paths.append(raw)

    print(f"\n  Collected {len(paths)} path(s)"
          + (f", ~{total_xml} XML files (before dedup)" if total_xml else ""))

    # Optional corpus title.  For single-directory input the empty default
    # signals "use the directory name", matching the CLI default; for any
    # other shape the dashboard's _default_corpus_name falls back to
    # "Custom corpus (N plays)" if left blank.
    if len(paths) == 1 and Path(paths[0]).is_dir():
        suggested_name = Path(paths[0]).name
    else:
        suggested_name = ""
    name = _ask_text("Corpus name", default=suggested_name) if suggested_name \
           else input("  Corpus name (leave blank for 'Custom corpus (N plays)'): ").strip()
    output_dir = _ask_text("Output directory", default="output")
    return {"paths": paths, "name": name or None, "out": output_dir}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_interactive() -> Optional[Tuple[str, dict]]:
    """Top-level interactive entry.  Returns (command, kwargs) or None.

    `command` is one of "analyze" / "corpus"; `kwargs` is the dict of
    pipeline arguments the caller forwards to `analyze_one` /
    `cmd_corpus`.  Returns None when the user quits or cancels.
    """
    _print_header()
    command = _ask(
        "What would you like to do?",
        [
            ("analyze", "Analyze a single play"),
            ("corpus",  "Analyze a corpus of plays"),
            ("quit",    "Exit"),
        ],
        default=0,
    )
    if command == "quit":
        print("\n  Goodbye!")
        return None
    if command == "analyze":
        kwargs = _interactive_analyze()
    else:
        kwargs = _interactive_corpus()
    if kwargs is None:
        return None
    return (command, kwargs)


__all__ = ["run_interactive"]
