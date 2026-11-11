"""Regression baseline for the demo play.

Every version-sensitive number lives here rather than being scattered through
the suite, so an intentional edit to `examples/Ar-07-Lys.xml` -- or to the
annotation of its milestones -- breaks one obvious test instead of twenty.

To accept a change:

    python tests/regen_baseline.py

which rewrites `baseline_demo.json` and prints exactly what moved.

The sample play is a copy of the corpus text, not a second edition of it.
The corpus file is authoritative and goes on being edited, so the copy is
refreshed by `tests/refresh_example.py` -- which copies and regenerates the
baseline in one step -- and never edited in place.  The last two tests below
fail when a sample and its corpus file have drifted apart, so a refresh that
is due cannot pass unnoticed; they skip where no corpus is checked out, which
is the case the bundled samples exist for.  The second sample,
`examples/Ar-01-Ach.xml`, is held to the corpus in the same way but has no
baseline of its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baseline_util import compute_fingerprint
from conftest import APP_DIR, DEMO_XML
from parser import parse_play

BASELINE = Path(__file__).resolve().parent / "baseline_demo.json"
CORPUS = APP_DIR.parent / "01-SkeneGraph-corpus" / "comedy"
# The second bundled sample.  No baseline depends on it; it is only held to
# the corpus text, like the demo play.
SECOND_SAMPLE = DEMO_XML.parent / "Ar-01-Ach.xml"


@pytest.fixture(scope="module")
def baseline():
    if not BASELINE.is_file():
        pytest.fail(
            f"{BASELINE.name} is missing -- create it with "
            "`python tests/regen_baseline.py`")
    return json.loads(BASELINE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fingerprint(demo_play):
    return compute_fingerprint(demo_play)


def test_no_quantity_is_missing(fingerprint, baseline):
    missing = sorted(set(baseline) - set(fingerprint))
    assert not missing, (
        "quantities disappeared from the fingerprint: " + ", ".join(missing))


def test_no_quantity_is_unexpected(fingerprint, baseline):
    extra = sorted(set(fingerprint) - set(baseline))
    assert not extra, (
        "new quantities not in the baseline: " + ", ".join(extra)
        + "\nrun `python tests/regen_baseline.py` to accept them")


def test_demo_fingerprint_matches_baseline(fingerprint, baseline):
    shared = sorted(set(fingerprint) & set(baseline))
    drift = {k: (baseline[k], fingerprint[k])
             for k in shared if baseline[k] != fingerprint[k]}
    assert not drift, (
        "demo play metrics drifted (expected -> actual):\n"
        + "\n".join(f"  {k}: {old!r} -> {new!r}" for k, (old, new) in drift.items())
        + "\n\nif the change is intended, run `python tests/regen_baseline.py`")


def _assert_matches_the_corpus(name, fingerprint):
    """Compared on the fingerprint rather than on bytes: reformatting the file
    is not drift, while a changed cast or a moved milestone is."""
    corpus_copy = CORPUS / name
    if not corpus_copy.is_file():
        pytest.skip(f"no corpus checked out at {corpus_copy}")
    authoritative = compute_fingerprint(parse_play(corpus_copy))
    drift = {k: (fingerprint.get(k), authoritative.get(k))
             for k in sorted(set(fingerprint) | set(authoritative))
             if fingerprint.get(k) != authoritative.get(k)}
    assert not drift, (
        f"{name} has fallen behind the corpus in {len(drift)} of "
        f"{len(set(fingerprint) | set(authoritative))} quantities "
        "(sample -> corpus):\n"
        + "\n".join(f"  {k}: {old!r} -> {new!r}"
                    for k, (old, new) in list(drift.items())[:12])
        + ("\n  ..." if len(drift) > 12 else "")
        + "\n\nrefresh it with `python tests/refresh_example.py`")


def test_example_still_matches_the_corpus(fingerprint):
    """The sample must describe the play the corpus now holds."""
    _assert_matches_the_corpus(DEMO_XML.name, fingerprint)


def test_second_sample_still_matches_the_corpus():
    """So must the second sample, which no baseline would otherwise watch."""
    _assert_matches_the_corpus(
        SECOND_SAMPLE.name, compute_fingerprint(parse_play(SECOND_SAMPLE)))
