"""The pipeline on plays that barely are plays.

Every metric in the app divides by something a real play always has: a cast,
a segment, a word.  Nothing exercised those denominators at zero, and the
first such file will arrive from outside the Aristophanic corpus -- a
fragment, a work in progress, a test file someone points the app at.  The
contract is that the run completes and the numbers are honest, not that the
output is interesting.
"""

from __future__ import annotations

import json

import pytest

from conftest import build_tei, move, sp, stage


DEGENERATE = {
    "one_character_one_speech": (
        ["a"],
        stage(move("entrance", "a")) + "\n" + sp("a", "one two three"),
    ),
    "two_characters_never_together": (
        ["a", "b"],
        "\n".join([
            stage(move("entrance", "a")), sp("a", "one"),
            stage(move("exit", "a")),
            stage(move("entrance", "b")), sp("b", "two"),
        ]),
    ),
    "nobody_speaks": (
        ["a", "b"],
        stage(move("entrance", "a b")),
    ),
    "every_speech_textless": (
        ["a", "b"],
        "\n".join([stage(move("entrance", "a b")), sp("a"), sp("b")]),
    ),
    "empty_stage_only": (
        ["a"],
        stage(move("onStage", "")),
    ),
}


@pytest.mark.parametrize("name", sorted(DEGENERATE))
def test_pipeline_survives_a_degenerate_play(name, tmp_path):
    from app import analyze_one

    persons, body = DEGENERATE[name]
    src = tmp_path / f"{name}.xml"
    src.write_text(build_tei(persons, body), encoding="utf-8")

    out = tmp_path / "out"
    summary = analyze_one(
        xml_path=src,
        seg_modes=["sd"],
        out_root=out,
        export_model="full",
        edge_weight="segments",
        make_dashboard=True,
    )

    # A play with no segment at all yields no summary; anything else must
    # produce a complete, self-consistent one.
    if summary is None:
        return

    mfile = next(out.rglob("sd/metrics.json"))
    m = json.loads(mfile.read_text(encoding="utf-8"))

    assert m["size"] == len(m["nodes"])
    assert m["numEdges"] >= 0
    assert 0.0 <= m["density"] <= 1.0
    assert m["averageDegree"] >= 0.0
    assert m["diameter"] >= 0
    assert m["averagePathLength"] >= 0.0

    sd = m["speech_distribution"]
    assert sd["total_words_spoken"] >= 0
    assert 0.0 <= sd["gini_words"] < 1.0
    assert sd["effective_speakers"] >= 0.0
    assert 0.0 <= sd["top_speaker_word_share"] <= 1.0
    if sd["top_speaker_id"] is None:
        assert sd["top_speaker_ids"] == []
    else:
        assert sd["top_speaker_ids"][0] == sd["top_speaker_id"]

    si = m["segment_indices"]
    assert 0.0 <= si["all_in_index"] <= 1.0
    assert 0.0 <= si["final_segment_cast_share"] <= 1.0
    assert si["max_simultaneous_speakers"] >= 0

    for node in m["nodes"]:
        if node.get("temporal_gini") is not None:
            assert 0.0 <= node["temporal_gini"] < 1.0
            assert node["n_onstage_segments"] >= 1
            assert node["speaking_segments"] <= node["n_onstage_segments"]

    # the dashboard must render too, not merely the metrics
    assert next(out.rglob("dashboard.html")).stat().st_size > 0
