"""Two plays must never write into one output directory.

The directory is named for the play, and the name is a sanitised title, so
distinct titles can arrive at the same one: `Electra?` and `Electra!` both
give `Electra`, as do two plays of that name by different authors.  Whichever
ran second used to overwrite the first's dashboard, CSVs and graph exports,
while the corpus dashboard went on carrying two summaries whose links both
led to the survivor -- two rows of numbers describing one play.

What must hold: a second source never lands in a first source's directory;
the same source re-run lands in its own; and where neither title nor file
name can tell two sources apart, the run says so instead of overwriting.
"""

from __future__ import annotations

import json

import pytest

from conftest import build_tei, move, sp, stage
from exporter import PROVENANCE_FILE, allocate_play_dir


def write_play(path, title, cast=("a", "b")):
    x, y = cast
    body = "\n".join([stage(move("entrance", f"{x} {y}")),
                      sp(x, "one two three"), sp(y, "four five")])
    path.write_text(build_tei(list(cast), body, title=title), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The allocator on its own
# ---------------------------------------------------------------------------

def test_two_titles_that_sanitise_alike_get_two_directories(tmp_path):
    out = tmp_path / "out"
    first = allocate_play_dir(out, "Electra?", tmp_path / "eur-el.xml", {})
    second = allocate_play_dir(out, "Electra!", tmp_path / "soph-el.xml", {})
    assert first != second
    assert first.name == "Electra"
    assert second.name == "Electra-soph-el"


def test_the_same_source_re_run_keeps_its_directory(tmp_path):
    out = tmp_path / "out"
    src = tmp_path / "eur-el.xml"
    first = allocate_play_dir(out, "Electra", src, {})
    again = allocate_play_dir(out, "Electra", src, {})
    assert first == again
    assert [p.name for p in sorted(out.iterdir())] == ["Electra"]


def test_a_directory_from_an_older_version_is_reused(tmp_path):
    """No marker means no way to tell a re-run from a stranger; treat it as
    a re-run, so upgrading the app does not rename everyone's output."""
    out = tmp_path / "out"
    (out / "Electra").mkdir(parents=True)
    got = allocate_play_dir(out, "Electra", tmp_path / "eur-el.xml", {})
    assert got.name == "Electra"


def test_the_marker_names_the_source(tmp_path):
    out = tmp_path / "out"
    got = allocate_play_dir(out, "Electra", tmp_path / "eur-el.xml", {})
    marker = json.loads((got / PROVENANCE_FILE).read_text(encoding="utf-8"))
    assert marker == {"source": "eur-el.xml", "play_id": "Electra"}


def test_a_collision_within_one_run_is_caught_without_the_marker(tmp_path):
    """`claimed` alone must be enough: the marker is for earlier runs."""
    out = tmp_path / "out"
    claimed: dict = {}
    allocate_play_dir(out, "Electra?", tmp_path / "eur-el.xml", claimed)
    second = allocate_play_dir(out, "Electra!", tmp_path / "soph-el.xml",
                               claimed)
    assert second.name == "Electra-soph-el"
    assert set(claimed) == {"Electra", "Electra-soph-el"}


def test_two_sources_alike_in_title_and_file_name_still_keep_both(tmp_path):
    """Nothing separates these two but the order they arrive in, which is
    enough to keep both: the second takes the fallback name."""
    out = tmp_path / "out"
    a = tmp_path / "one" / "el.xml"
    b = tmp_path / "two" / "el.xml"
    for p in (a, b):
        p.parent.mkdir(parents=True)
    claimed: dict = {}
    first = allocate_play_dir(out, "Electra", a, claimed)
    second = allocate_play_dir(out, "Electra", b, claimed)
    assert (first.name, second.name) == ("Electra", "Electra-el")


def test_a_dead_end_fails_loudly_rather_than_overwriting(tmp_path):
    """Both candidate names held by other sources: there is nowhere left to
    put this play, and it must not be put on top of one of them."""
    out = tmp_path / "out"
    src = tmp_path / "three" / "el.xml"
    src.parent.mkdir(parents=True)
    for name, holder in (("Electra", "first.xml"),
                         ("Electra-el", "second.xml")):
        (out / name).mkdir(parents=True)
        (out / name / PROVENANCE_FILE).write_text(
            json.dumps({"source": holder, "play_id": "Electra"}),
            encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be told apart"):
        allocate_play_dir(out, "Electra", src, {})


def test_a_relocated_corpus_re_runs_into_its_own_directories(tmp_path):
    """Identity across runs is the file name, so moving the corpus does not
    double the output tree."""
    out = tmp_path / "out"
    before = tmp_path / "before" / "eur-el.xml"
    after = tmp_path / "after" / "eur-el.xml"
    for p in (before, after):
        p.parent.mkdir(parents=True)
    first = allocate_play_dir(out, "Electra", before, {})
    second = allocate_play_dir(out, "Electra", after, {})
    assert first == second
    assert [p.name for p in sorted(out.iterdir())] == ["Electra"]


def test_the_warning_names_both_sources(tmp_path, caplog):
    out = tmp_path / "out"
    allocate_play_dir(out, "Electra?", tmp_path / "eur-el.xml", {})
    with caplog.at_level("WARNING"):
        allocate_play_dir(out, "Electra!", tmp_path / "soph-el.xml", {})
    assert "soph-el.xml" in caplog.text and "eur-el.xml" in caplog.text


# ---------------------------------------------------------------------------
# The same thing through the pipeline
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_a_corpus_of_two_colliding_titles_keeps_both_plays(tmp_path):
    from app import analyze_one

    out = tmp_path / "out"
    out.mkdir()
    claimed: dict = {}
    summaries = []
    for title, cast, name in (("Electra?", ("a", "b"), "eur-el.xml"),
                              ("Electra!", ("c", "d"), "soph-el.xml")):
        src = write_play(tmp_path / name, title, cast)
        summaries.append(analyze_one(
            xml_path=src, seg_modes=["sd"], out_root=out,
            export_model="full", edge_weight="segments",
            make_dashboard=True, claimed_dirs=claimed))

    hrefs = [s["dashboard_href"] for s in summaries]
    assert len(set(hrefs)) == 2, hrefs
    for summary, cast in zip(summaries, (("a", "b"), ("c", "d"))):
        play_dir = out / summary["dashboard_href"].split("/")[0]
        rows = (play_dir / "sd" / "characters.csv").read_text(
            encoding="utf-8").splitlines()[1:]
        assert sorted(r.split(",")[0] for r in rows if r) == sorted(cast)
        assert summary["title_en"] in (play_dir / "dashboard.html").read_text(
            encoding="utf-8")
