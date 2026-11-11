"""Corpus path resolution and the default corpus title.

Both are pure functions reached only through the CLI, so the subprocess
pipeline tests exercise one arrangement of them and nothing checks the rest.
The deduplication in particular fails silently: a play analysed twice simply
appears twice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import _default_corpus_name, _resolve_corpus_paths


@pytest.fixture()
def corpus(tmp_path):
    d = tmp_path / "comedy"
    d.mkdir()
    for name in ("Ar-01.xml", "Ar-02.xml", "notes.txt"):
        (d / name).write_text("<TEI/>", encoding="utf-8")
    other = tmp_path / "tragedy"
    other.mkdir()
    (other / "So-01.xml").write_text("<TEI/>", encoding="utf-8")
    return tmp_path, d, other


def test_directory_is_globbed_by_pattern(corpus):
    _, d, _ = corpus
    got = _resolve_corpus_paths([str(d)], "*.xml")
    assert [p.name for p in got] == ["Ar-01.xml", "Ar-02.xml"]


def test_explicit_file_keeps_its_extension(corpus):
    _, d, _ = corpus
    got = _resolve_corpus_paths([str(d / "notes.txt")], "*.xml")
    assert [p.name for p in got] == ["notes.txt"]


def test_a_file_listed_twice_is_analysed_once(corpus):
    """`corpus comedy/ comedy/Ar-01.xml` must not double-count the play."""
    _, d, _ = corpus
    got = _resolve_corpus_paths([str(d), str(d / "Ar-01.xml")], "*.xml")
    assert [p.name for p in got] == ["Ar-01.xml", "Ar-02.xml"]


def test_dedup_sees_through_a_different_spelling_of_the_same_path(corpus):
    root, d, _ = corpus
    got = _resolve_corpus_paths([str(d), str(root / "." / "comedy")], "*.xml")
    assert len(got) == 2


def test_several_paths_are_merged_and_sorted(corpus):
    _, d, other = corpus
    got = _resolve_corpus_paths([str(other), str(d)], "*.xml")
    assert [p.name for p in got] == ["Ar-01.xml", "Ar-02.xml", "So-01.xml"]


def test_missing_path_is_skipped_not_fatal(corpus, caplog):
    _, d, _ = corpus
    got = _resolve_corpus_paths([str(d / "nope.xml"), str(d)], "*.xml")
    assert [p.name for p in got] == ["Ar-01.xml", "Ar-02.xml"]


def test_empty_directory_is_skipped(tmp_path):
    (tmp_path / "empty").mkdir()
    assert _resolve_corpus_paths([str(tmp_path / "empty")], "*.xml") == []


# ---------------------------------------------------------------------------
# The default title
# ---------------------------------------------------------------------------

def test_single_directory_is_named_after_itself(corpus):
    _, d, _ = corpus
    assert _default_corpus_name([str(d)], 2) == "comedy"


def test_several_paths_get_a_generic_title(corpus):
    _, d, other = corpus
    assert _default_corpus_name([str(d), str(other)], 3) \
        == "Custom corpus (3 plays)"


def test_one_play_is_not_called_plays(corpus):
    _, d, _ = corpus
    assert _default_corpus_name([str(d / "Ar-01.xml")], 1) \
        == "Custom corpus (1 play)"


def test_analyze_fails_when_nothing_was_produced(tiny_path, tmp_path, caplog):
    """Asking for a spine the file does not annotate exports nothing, and the
    exit status has to say so -- a script cannot read a log line."""
    from conftest import move, sp, stage
    from app import build_parser, cmd_analyze

    path = tiny_path(["a"], stage(move("entrance", "a")) + sp("a", "x"))
    out = tmp_path / "out"
    args = build_parser().parse_args(
        ["analyze", str(path), "--seg", "large-seq", "--out", str(out),
         "--no-dashboard"])
    assert cmd_analyze(args) == 1
    args = build_parser().parse_args(
        ["analyze", str(path), "--seg", "sd", "--out", str(out),
         "--no-dashboard"])
    assert cmd_analyze(args) == 0
