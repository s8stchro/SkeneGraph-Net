"""Metrics: schema, formula agreement, Gini family, plot-dynamics indices.

Several tests re-derive a metric from its published formula (the Methods
tab) and compare against the implementation, so the documentation and the
code are checked against each other rather than separately.
"""

from __future__ import annotations

import pytest

from conftest import milestone, move, sp, stage
from metrics import (_gini, _safe_eigenvector, compute_demographics,
                     compute_metrics,
                     compute_segment_indices, compute_speech_distribution,
                     compute_temporal_gini)
from network import build_static
from segmentation import segment_middle_seq, segment_stage_directions

METRIC_KEYS = {
    "id", "name", "size", "numEdges", "density", "averageDegree",
    "maxDegree", "maxDegreeIds", "diameter", "averagePathLength",
    "averageClustering", "numConnectedComponents", "nodes",
}
NODE_KEYS = {"id", "degree", "weightedDegree", "betweenness", "closeness",
             "eigenvector", "clustering", "triangles"}


@pytest.fixture(scope="module")
def demo_metrics(demo_play, demo_segments):
    G = build_static(demo_segments["middle-seq"], demo_play.characters)
    return compute_metrics(G, "demo", "Demo")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_metrics_schema(demo_metrics):
    assert set(demo_metrics) == METRIC_KEYS
    assert set(demo_metrics["nodes"][0]) == NODE_KEYS


def test_metrics_schema_is_word_based(demo_metrics, demo_play):
    """Regression guard: no verse-era key survives anywhere in the output."""
    blob = repr(demo_metrics) + repr(compute_speech_distribution(demo_play))
    for token in ("verse", "gini_verses", "total_verses"):
        assert token not in blob


def test_size_is_order_not_edge_count(demo_metrics):
    """`size` is the JSON field name for |V| (see Methods tab, section 1)."""
    assert demo_metrics["size"] == len(demo_metrics["nodes"])


def test_empty_graph_is_handled():
    import networkx as nx
    m = compute_metrics(nx.Graph())
    assert m["size"] == 0 and m["numEdges"] == 0
    assert m["nodes"] == []


# ---------------------------------------------------------------------------
# Formula agreement
# ---------------------------------------------------------------------------

def test_density_matches_formula(demo_metrics):
    n, e = demo_metrics["size"], demo_metrics["numEdges"]
    assert demo_metrics["density"] == pytest.approx(2 * e / (n * (n - 1)))


def test_average_degree_matches_formula(demo_metrics):
    n, e = demo_metrics["size"], demo_metrics["numEdges"]
    assert demo_metrics["averageDegree"] == pytest.approx(2 * e / n)


def test_density_and_average_degree_identity(demo_metrics):
    """d = k / (n - 1): the identity the iso-degree curve traces."""
    n = demo_metrics["size"]
    assert demo_metrics["density"] == pytest.approx(
        demo_metrics["averageDegree"] / (n - 1))


def test_max_degree_and_ids_agree(demo_metrics):
    by_id = {node["id"]: node["degree"] for node in demo_metrics["nodes"]}
    assert demo_metrics["maxDegree"] == max(by_id.values())
    assert (set(demo_metrics["maxDegreeIds"])
            == {i for i, d in by_id.items() if d == demo_metrics["maxDegree"]})


def test_bounded_metrics_are_in_range(demo_metrics):
    assert 0.0 <= demo_metrics["density"] <= 1.0
    assert 0.0 <= demo_metrics["averageClustering"] <= 1.0
    for node in demo_metrics["nodes"]:
        assert 0.0 <= node["betweenness"] <= 1.0
        assert 0.0 <= node["closeness"] <= 1.0


def test_triangle_has_known_metrics():
    import networkx as nx
    G = nx.Graph()
    G.add_edges_from([("a", "b"), ("b", "c"), ("a", "c")])
    m = compute_metrics(G)
    assert m["size"] == 3 and m["numEdges"] == 3
    assert m["density"] == pytest.approx(1.0)
    assert m["averageDegree"] == pytest.approx(2.0)
    assert m["diameter"] == 1
    assert m["averageClustering"] == pytest.approx(1.0)
    assert m["numConnectedComponents"] == 1


def test_average_clustering_is_the_mean_of_the_per_character_values(demo_metrics):
    """The play-level figure and the per-character column are the same
    measure at two levels, and cannot drift apart."""
    vals = [n["clustering"] for n in demo_metrics["nodes"]]
    assert demo_metrics["averageClustering"] == pytest.approx(
        sum(vals) / len(vals), abs=1e-6)


def test_a_character_with_one_neighbour_gets_a_zero_not_a_gap():
    """With fewer than two neighbours there is no neighbour pair and the
    quotient is 0/0.  NetworkX gives 0, and §1's mean already counts that 0;
    igraph returns NaN, which is where a table built there shows a gap."""
    import networkx as nx
    G = nx.Graph()
    G.add_edges_from([("a", "b"), ("a", "c"), ("b", "c"), ("a", "d")])
    n = {node["id"]: node for node in compute_metrics(G)["nodes"]}
    assert n["d"]["clustering"] == 0.0 and n["d"]["triangles"] == 0
    assert n["a"]["clustering"] == pytest.approx(1 / 3)   # 3 pairs, 1 joined
    assert n["b"]["clustering"] == pytest.approx(1.0)
    assert [n[c]["triangles"] for c in "abc"] == [1, 1, 1]


def test_a_triangle_is_counted_for_each_of_its_three_vertices():
    import networkx as nx
    m = compute_metrics(nx.complete_graph(["a", "b", "c", "d"]))
    assert sum(node["triangles"] for node in m["nodes"]) == 12   # 4 triangles


def test_no_per_character_speech_count_is_published(demo_metrics):
    """A character's speech is cut into several <sp> wherever a move falls
    inside it or the addressee changes -- 82 of the corpus's 6474 speeches
    are such continuations, and the share runs from 0.2% to 3.3% by play --
    so the count would report the annotation rather than the play.  Words
    survive the cut; `num_speeches` stays per segment."""
    import metrics as metrics_module
    assert not hasattr(metrics_module, "compute_speech_acts")
    assert all("speech_acts" not in node for node in demo_metrics["nodes"])


# ---------------------------------------------------------------------------
# Gini
# ---------------------------------------------------------------------------

def test_gini_of_equal_distribution_is_zero():
    assert _gini([5, 5, 5, 5]) == pytest.approx(0.0)


def test_gini_of_maximal_concentration():
    """With zeros kept, one holder of everything gives (n-1)/n."""
    assert _gini([0, 0, 0, 4], include_zeros=True) == pytest.approx(0.75)


def test_gini_drops_zeros_by_default():
    """The cast-level Gini ignores non-speakers."""
    assert _gini([0, 0, 0, 4]) == pytest.approx(0.0)


def test_gini_is_scale_invariant():
    assert _gini([1, 2, 3]) == pytest.approx(_gini([10, 20, 30]))


def test_gini_of_empty_is_zero():
    assert _gini([]) == 0.0


# ---------------------------------------------------------------------------
# Speech distribution
# ---------------------------------------------------------------------------

KEYS = {"gini_words", "effective_speakers", "top_speaker_id",
        "top_speaker_ids", "top_speaker_word_share", "total_words_spoken"}


def test_speech_distribution_keys(demo_play):
    assert set(compute_speech_distribution(demo_play)) == KEYS


def test_speech_distribution_keys_when_nobody_speaks(tiny_play):
    """The empty branch must answer with the same fields.

    It is a separate return statement, so a field added to one branch and not
    the other goes unnoticed until a silent play reaches the pipeline and a
    reader of metrics.json meets a missing key.
    """
    play = tiny_play(["a", "b"], sp("a"))      # one textless <sp>, no words
    sd = compute_speech_distribution(play)
    assert set(sd) == KEYS
    assert sd["total_words_spoken"] == 0 and sd["effective_speakers"] == 0.0


def test_top_speaker_share_is_a_fraction(demo_play):
    sd = compute_speech_distribution(demo_play)
    assert 0.0 < sd["top_speaker_word_share"] <= 1.0
    assert sd["top_speaker_id"] in demo_play.characters
    assert sd["top_speaker_ids"] == [sd["top_speaker_id"]]   # no tie here


def test_speech_distribution_on_a_known_play(tiny_play):
    body = sp("a", "one two three") + "\n" + sp("b", "four")
    play = tiny_play(["a", "b"], body)
    sd = compute_speech_distribution(play)
    assert sd["total_words_spoken"] == 4
    assert sd["top_speaker_id"] == "a"
    assert sd["top_speaker_word_share"] == pytest.approx(0.75)


def test_joint_speech_credits_both_speakers(tiny_play):
    """The word rule: a joint <sp> gives its full count to each id, so every
    total exceeds the number of words standing in the text."""
    play = tiny_play(["a", "b"], sp("a b", "one two"))
    sd = compute_speech_distribution(play)
    assert sd["total_words_spoken"] == 4          # 2 words x 2 speakers
    assert sum(s.attributed_words for s in play.speeches) == 4
    assert sum(s.word_count for s in play.speeches) == 2   # the text itself


def test_placeholder_speeches_are_excluded(tiny_play):
    body = sp("a", "one two") + "\n" + sp("b")
    play = tiny_play(["a", "b"], body)
    sd = compute_speech_distribution(play)
    assert sd["total_words_spoken"] == 2
    assert sd["top_speaker_id"] == "a"


def test_silent_play_yields_zero_distribution(tiny_play):
    play = tiny_play(["a"], sp("a"))
    sd = compute_speech_distribution(play)
    assert sd["total_words_spoken"] == 0
    assert sd["top_speaker_id"] is None
    assert sd["top_speaker_ids"] == []


def test_effective_speakers_at_the_two_extremes(tiny_play):
    """$n$ when the words are shared equally, $1$ when one speaker has them."""
    equal = tiny_play(["a", "b", "c"], "\n".join(
        [sp("a", "one two"), sp("b", "three four"), sp("c", "five six")]))
    assert compute_speech_distribution(equal)["effective_speakers"] \
        == pytest.approx(3.0)
    alone = tiny_play(["a", "b"], "\n".join([sp("a", "one two"), sp("b")]))
    assert compute_speech_distribution(alone)["effective_speakers"] \
        == pytest.approx(1.0)


def test_effective_speakers_ignores_a_bit_part_where_the_gini_does_not(tiny_play):
    """The property the metric is here for.

    Adding a character with one word is a change to the cast list rather than
    to who carries the play.  The Gini moves on it -- by as much as a tenth
    on a small cast -- because a new rank shifts every term; ESp moves only
    by the renormalisation of the other shares, so its response scales with
    the bit part's share of the text and vanishes as that share does.  The
    cast here is sized so that one word is about what a real one-line role
    is worth, a hundredth of a percent of the play.
    """
    cast = {"a": 2000, "b": 800, "c": 400, "d": 200, "e": 100, "f": 40}
    body = [sp(who, " ".join(["w"] * n)) for who, n in cast.items()]
    before = compute_speech_distribution(
        tiny_play(list(cast), "\n".join(body)))
    after = compute_speech_distribution(
        tiny_play(list(cast) + ["z"], "\n".join(body + [sp("z", "one")])))

    esp_move = abs(after["effective_speakers"] - before["effective_speakers"])
    gini_move = abs(after["gini_words"] - before["gini_words"])
    assert esp_move < 0.005, esp_move
    assert gini_move > 0.05, gini_move
    assert gini_move > 20 * esp_move, (gini_move, esp_move)


def test_every_tied_top_speaker_is_reported(tiny_play):
    """A two-hander can end level; the code must not invent a winner."""
    body = "\n".join([sp("b", "one two"), sp("a", "three four"),
                      sp("c", "five")])
    sd = compute_speech_distribution(tiny_play(["a", "b", "c"], body))
    assert sd["top_speaker_ids"] == ["a", "b"]
    assert sd["top_speaker_id"] == "a"            # the first of them
    assert sd["top_speaker_word_share"] == pytest.approx(0.4)


def test_the_top_speaker_does_not_depend_on_set_iteration_order(tiny_play):
    """Two characters tying, both first heard in the same joint speech.

    `per_char` used to be filled by iterating `sp.who`, a set, so the pick
    followed Python's per-process string hashing: the same build reported a
    different top speaker from one run to the next.
    """
    sd = compute_speech_distribution(tiny_play(["a", "b"], sp("a b", "one two")))
    assert sd["top_speaker_ids"] == ["a", "b"]
    assert sd["top_speaker_word_share"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Demographics
# ---------------------------------------------------------------------------

def test_demographics_partition_the_cast(demo_play):
    dem = compute_demographics(demo_play)
    total = len(demo_play.characters)
    assert dem["speakers"] + dem["mutes"] == total
    assert dem["individuals"] + dem["collectives"] == total
    assert sum(dem["sex"].values()) == total
    assert sum(dem["nature"].values()) == total


def test_mixed_is_counted_apart_from_unspecified(tiny_play):
    """A deliberately mixed collective is not an absence of information.

    `mixed` says the group comprises both; `irrelevant` and a missing trait
    say the question does not arise or was not recorded.  Bucketing them
    together discarded a distinction the encoding takes trouble to make.
    """
    play = tiny_play(["a", "b", "c"], sp("a", "one"))
    play.characters["a"].sex = "mixed"
    play.characters["b"].sex = "irrelevant"
    play.characters["c"].sex = None
    dem = compute_demographics(play)
    assert dem["sex"]["mixed"] == 1
    assert dem["sex"]["unspecified"] == 2
    assert sum(dem["sex"].values()) == len(play.characters)


def test_collective_speakers_is_an_intersection(demo_play):
    dem = compute_demographics(demo_play)
    expected = sum(1 for c in demo_play.characters.values()
                   if c.is_collective and not c.is_mute)
    assert dem["collective_speakers"] == expected


def test_excluding_mutes_changes_the_counts(demo_play):
    with_mutes = compute_demographics(demo_play, include_mutes=True)
    without = compute_demographics(demo_play, include_mutes=False)
    assert without["mutes"] == 0
    assert without["speakers"] == with_mutes["speakers"]


# ---------------------------------------------------------------------------
# Segment indices
# ---------------------------------------------------------------------------

def test_segment_indices_ranges(demo_segments):
    idx = compute_segment_indices(demo_segments["middle-seq"])
    assert 0.0 < idx["all_in_index"] <= 1.0
    assert 0.0 < idx["final_segment_cast_share"] <= 1.0
    assert idx["max_simultaneous_speakers"] >= 1


def test_all_in_index_when_cast_completes_immediately(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a b")),
        milestone("middle-seq", "s001"), sp("a", "one"),
        milestone("middle-seq", "s002"), sp("b", "two"),
        milestone("middle-seq", "s003"), sp("a", "three"),
    ])
    play = tiny_play(["a", "b"], body)
    idx = compute_segment_indices(segment_middle_seq(play))
    assert idx["all_in_segment"] == 0
    assert idx["all_in_index"] == pytest.approx(1 / 3)


def test_all_in_index_when_cast_grows_to_the_end(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a")),
        milestone("middle-seq", "s001"), sp("a", "one"),
        milestone("middle-seq", "s002"), sp("a", "two"),
        milestone("middle-seq", "s003"),
        stage(move("entrance", "b")), sp("b", "three"),
    ])
    play = tiny_play(["a", "b"], body)
    idx = compute_segment_indices(segment_middle_seq(play))
    assert idx["all_in_index"] == pytest.approx(1.0)


def test_move_belongs_to_the_milestone_in_force_when_it_occurs(tiny_play):
    """Boundary attribution on the milestone spines: a move placed *before*
    a milestone falls inside the preceding unit, and the entering character
    is credited to that unit -- so where an entrance sits relative to the
    milestone changes the segment cast."""
    def build(entrance_before_milestone: bool):
        third = [milestone("middle-seq", "s003"), stage(move("entrance", "b"))]
        if entrance_before_milestone:
            third.reverse()
        return "\n".join([
            stage(move("entrance", "a")),
            milestone("middle-seq", "s001"), sp("a", "one"),
            milestone("middle-seq", "s002"), sp("a", "two"),
            *third, sp("b", "three"),
        ])

    before = segment_middle_seq(tiny_play(["a", "b"], build(True)))
    after = segment_middle_seq(tiny_play(["a", "b"], build(False)))

    assert "b" in before[1].characters_present      # credited to s002
    assert "b" not in after[1].characters_present   # credited to s003
    assert "b" in after[2].characters_present


def test_max_simultaneous_speakers_counts_distinct_speakers(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a b c")),
        milestone("middle-seq", "s001"),
        sp("a", "one"), sp("b", "two"), sp("c", "three"),
        milestone("middle-seq", "s002"),
        sp("a", "four"),
    ])
    play = tiny_play(["a", "b", "c"], body)
    idx = compute_segment_indices(segment_middle_seq(play))
    assert idx["max_simultaneous_speakers"] == 3


def test_placeholder_speech_does_not_count_as_a_speaker(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a b")),
        milestone("middle-seq", "s001"),
        sp("a", "one"), sp("b"),
    ])
    play = tiny_play(["a", "b"], body)
    idx = compute_segment_indices(segment_middle_seq(play))
    assert idx["max_simultaneous_speakers"] == 1


def test_segment_indices_respect_the_model_node_set(tiny_play):
    """B6: with `kept` given, the indices answer for the model's cast --
    a mute arriving last no longer drags the all-in point to the end."""
    body = "\n".join([
        stage(move("entrance", "a")),
        milestone("middle-seq", "s001"), sp("a", "one"),
        milestone("middle-seq", "s002"),
        stage(move("entrance", "b")), sp("b", "two"),
        milestone("middle-seq", "s003"),
        stage(move("entrance", "m")), sp("a", "three"),
    ])
    segs = segment_middle_seq(tiny_play(["a", "b", "m"], body))
    raw = compute_segment_indices(segs)
    mod = compute_segment_indices(segs, kept={"a", "b"})
    assert raw["all_in_segment_label"] == "s003"
    assert raw["all_in_index"] == pytest.approx(1.0)
    assert mod["all_in_segment_label"] == "s002"
    assert mod["all_in_index"] == pytest.approx(2 / 3)


def test_model_empty_opening_segment_excluded_like_the_marker(tiny_play):
    """B5: an opening beat holding only characters the model drops leaves
    the scan and the divisor together, exactly like the pre-play marker."""
    body = "\n".join([
        stage(move("entrance", "m")),
        milestone("middle-seq", "s001"), sp("m", "mute-only opening"),
        milestone("middle-seq", "s002"),
        stage(move("entrance", "a b")), sp("a", "one"),
        milestone("middle-seq", "s003"), sp("b", "two"),
    ])
    segs = segment_middle_seq(tiny_play(["a", "b", "m"], body))
    mod = compute_segment_indices(segs, kept={"a", "b"})
    assert mod["all_in_segment_label"] == "s002"
    assert mod["all_in_index"] == pytest.approx(1 / 2)   # scanned frame: 2 segments


def test_all_in_follows_the_models_segment_cast(tiny_play):
    """Under the speaking cast the index reports when the cast has finished
    speaking itself complete, not when every speaker has been seen."""
    body = "\n".join([
        stage(move("entrance", "a")),
        milestone("middle-seq", "s001"), sp("a", "one"),
        milestone("middle-seq", "s002"),
        stage(move("entrance", "b c")), sp("b", "two"),   # c present, silent
        milestone("middle-seq", "s003"), sp("c", "three"),
    ])
    segs = segment_middle_seq(tiny_play(["a", "b", "c"], body))
    kept = {"a", "b", "c"}
    on_stage = compute_segment_indices(segs, kept, "stage")
    speaking = compute_segment_indices(segs, kept, "speaking")
    # Presence completes the cast the moment c walks on ...
    assert on_stage["all_in_segment_label"] == "s002"
    assert on_stage["all_in_index"] == pytest.approx(2 / 3)
    # ... speech only when c finally says something.
    assert speaking["all_in_segment_label"] == "s003"
    assert speaking["all_in_index"] == pytest.approx(1.0)


def test_final_share_counts_speakers_under_the_speaking_cast(tiny_play):
    """The share answers for the graph on screen: under the segment-level
    model a closing tableau of silent speakers contributes nothing."""
    body = "\n".join([
        stage(move("entrance", "a b c")),
        milestone("middle-seq", "s001"), sp("a", "one"), sp("b", "two"),
        sp("c", "three"),
        milestone("middle-seq", "s002"), sp("a", "the last word"),
    ])
    segs = segment_middle_seq(tiny_play(["a", "b", "c"], body))
    kept = {"a", "b", "c"}
    assert compute_segment_indices(segs, kept, "stage")[
        "final_segment_cast_share"] == pytest.approx(1.0)
    assert compute_segment_indices(segs, kept, "speaking")[
        "final_segment_cast_share"] == pytest.approx(1 / 3)


def test_final_share_walks_back_to_the_last_segment_carrying_speech(tiny_play):
    """The walk-back is what makes the speaking cast usable at all: without
    it a play closing on silent business would read 0.000."""
    body = "\n".join([
        stage(move("entrance", "a b")),
        milestone("middle-seq", "s001"), sp("a", "one"), sp("b", "two"),
        milestone("middle-seq", "s002"),
        stage(move("entrance", "m")),          # mute walks on; nobody speaks
    ])
    segs = segment_middle_seq(tiny_play(["a", "b", "m"], body))
    assert not segs[-1].speakers, "the closing segment must carry no speech"
    idx = compute_segment_indices(segs, {"a", "b"}, "speaking")
    assert idx["final_segment_cast_share"] == pytest.approx(1.0)


def test_demo_play_indices_are_read_for_each_models_own_cast(demo_play):
    """End-to-end on the demo play, against an independent re-derivation.

    Pins the wiring as well as the rule: the segment-level model reads its
    own speaking cast, and the two models that count presence are untouched
    by the distinction.
    """
    from network import _kept_characters
    from segmentation import fold_for_model

    models = {"full": (True, "stage"), "p-speaking": (False, "stage"),
              "s-speaking": (False, "speaking")}
    for model, (inc_mutes, seg_cast) in models.items():
        segs = segment_stage_directions(demo_play)
        kept = _kept_characters(demo_play.characters, segs, inc_mutes, seg_cast)
        if not inc_mutes:
            segs = fold_for_model(segs, kept, seg_cast)
        idx = compute_segment_indices(segs, kept, seg_cast)

        # Re-derive from the model's own cast, without the function.
        casts = [(s.speakers if seg_cast == "speaking"
                  else s.characters_present) & kept for s in segs]
        total = set().union(*casts) if casts else set()
        final = next((c for c in reversed(casts) if c), set())
        assert idx["final_segment_cast_share"] == pytest.approx(
            len(final) / len(total)), model
        assert final, f"{model}: the walk-back found no acted final segment"

        # On its own spine, the presence reading is a different number for
        # the segment-level model and the same one for the other two.  This
        # is the assertion that fails if the cast argument stops being
        # threaded through: Lysistrata's finale is sung by three of the
        # twenty-three speakers, with the rest on stage and silent.
        on_stage = compute_segment_indices(segs, kept, "stage")
        differs = idx["final_segment_cast_share"] != pytest.approx(
            on_stage["final_segment_cast_share"])
        assert differs is (seg_cast == "speaking"), model


def test_segment_indices_on_empty_input():
    idx = compute_segment_indices([])
    assert idx["all_in_segment"] is None
    assert idx["max_simultaneous_speakers"] == 0


# ---------------------------------------------------------------------------
# Temporal Gini
# ---------------------------------------------------------------------------

def test_temporal_gini_keys_and_range(demo_segments):
    tg = compute_temporal_gini(demo_segments["middle-seq"])
    assert tg
    for entry in tg.values():
        assert set(entry) == {"total_words", "speaking_segments",
                              "n_onstage_segments", "n_active_segments",
                              "temporal_gini"}
        assert 0 < entry["n_onstage_segments"] <= entry["n_active_segments"]
        assert 0.0 <= entry["temporal_gini"] < 1.0
        assert entry["total_words"] > 0


def test_temporal_gini_counts_silence_while_present(tiny_play):
    """Standing on stage without speaking is a zero in the vector.

    `a` is present throughout and speaks in one segment of three, so two
    thirds of their stage time is silent: (m-1)/m for m = 3.
    """
    body = "\n".join([
        stage(move("entrance", "a b")),
        milestone("middle-seq", "s001"), sp("a", "one two"),
        milestone("middle-seq", "s002"), sp("b", "three"),
        milestone("middle-seq", "s003"), sp("b", "four"),
    ])
    play = tiny_play(["a", "b"], body)
    tg = compute_temporal_gini(segment_middle_seq(play))
    assert tg["a"]["n_onstage_segments"] == 3
    assert tg["a"]["n_active_segments"] == 3
    assert tg["a"]["speaking_segments"] == 1
    assert tg["a"]["temporal_gini"] == pytest.approx(2 / 3, abs=1e-6)


def test_temporal_gini_ignores_segments_before_and_after_a_presence(tiny_play):
    """The point of the on-stage span: absence is not counted as silence.

    `a` speaks evenly through both segments they are on stage for and then
    leaves.  Padding across the whole play would have scored them 1/3 for a
    third segment they are nowhere near; over their own presence they are
    perfectly even.
    """
    body = "\n".join([
        stage(move("entrance", "a b")),
        milestone("middle-seq", "s001"), sp("a", "one"), sp("b", "one"),
        milestone("middle-seq", "s002"), sp("a", "two"), sp("b", "two"),
        stage(move("exit", "a")),
        milestone("middle-seq", "s003"), sp("b", "three"),
    ])
    play = tiny_play(["a", "b"], body)
    tg = compute_temporal_gini(segment_middle_seq(play))
    assert tg["a"]["n_onstage_segments"] == 2
    assert tg["a"]["n_active_segments"] == 3
    assert tg["a"]["temporal_gini"] == pytest.approx(0.0, abs=1e-6)
    assert tg["b"]["n_onstage_segments"] == 3


def test_temporal_gini_of_even_speaker_is_zero(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a")),
        milestone("middle-seq", "s001"), sp("a", "one"),
        milestone("middle-seq", "s002"), sp("a", "two"),
        milestone("middle-seq", "s003"), sp("a", "three"),
    ])
    play = tiny_play(["a"], body)
    tg = compute_temporal_gini(segment_middle_seq(play))
    assert tg["a"]["temporal_gini"] == pytest.approx(0.0, abs=1e-6)


def test_temporal_gini_skips_mutes(demo_play, demo_segments):
    tg = compute_temporal_gini(demo_segments["middle-seq"])
    mutes = {c.id for c in demo_play.characters.values() if c.is_mute}
    assert not (set(tg) & mutes)


def test_temporal_gini_totals_match_speech_distribution(demo_play, demo_segments):
    """Per-character word totals must reconcile with the play-level total."""
    tg = compute_temporal_gini(demo_segments["middle-seq"])
    sd = compute_speech_distribution(demo_play)
    assert sum(e["total_words"] for e in tg.values()) == sd["total_words_spoken"]


# ---------------------------------------------------------------------------
# Eigenvector centrality on disconnected graphs
# ---------------------------------------------------------------------------

def _two_component_graph():
    """A dense triangle, a separate edge, and an isolated vertex."""
    import networkx as nx
    G = nx.Graph()
    for a, b in (("a", "b"), ("b", "c"), ("a", "c")):
        G.add_edge(a, b, weight=3)
    G.add_edge("d", "e", weight=1)
    G.add_node("lonely")
    return G


def test_eigenvector_is_computed_per_component():
    """Every character is scored inside their own component.

    The principal eigenvector of a disconnected matrix belongs to one
    component; NetworkX's dense solver refuses such a graph outright and the
    power-iteration fallback returns the decay of an iteration that converged
    elsewhere -- values near 1e-6 that read as small centralities and are not.
    """
    ev = _safe_eigenvector(_two_component_graph())
    triangle = [ev["a"], ev["b"], ev["c"]]
    pair = [ev["d"], ev["e"]]
    assert all(v > 0.5 for v in triangle), triangle
    assert all(v > 0.5 for v in pair), pair      # not solver residue
    assert ev["lonely"] == 0.0                   # no edges, nothing to score


def test_each_component_is_normalised_to_unit_length():
    import math
    ev = _safe_eigenvector(_two_component_graph())
    for comp in (("a", "b", "c"), ("d", "e")):
        norm = math.sqrt(sum(ev[n] ** 2 for n in comp))
        assert norm == pytest.approx(1.0), comp


def test_connected_graphs_keep_the_solver_result(demo_play, demo_segments):
    """The repair must not move a single published value."""
    import networkx as nx
    G = build_static(demo_segments["sd"], demo_play.characters)
    assert nx.is_connected(G)
    assert _safe_eigenvector(G) == pytest.approx(
        nx.eigenvector_centrality_numpy(G, weight="weight"))


# ---------------------------------------------------------------------------
# When the published solver is not the one running
# ---------------------------------------------------------------------------

@pytest.fixture()
def without_numpy(monkeypatch):
    """NetworkX requires neither NumPy nor SciPy, so the dense solver can be
    absent on a working install.  Make it so, and reset the once-per-run flag
    the warning keeps."""
    import networkx as nx
    import metrics

    def missing(*a, **k):
        raise ImportError("No module named 'numpy'")

    monkeypatch.setattr(nx, "eigenvector_centrality_numpy", missing)
    monkeypatch.setattr(metrics, "_numpy_solver_reported", False)


def test_a_missing_numpy_solver_is_reported(without_numpy, caplog):
    """Caught silently, the fallback shows up only when someone diffs two
    dashboards: the values differ in about the sixth decimal."""
    with caplog.at_level("WARNING", logger="SkeneGraph-Net.metrics"):
        ev = _safe_eigenvector(_two_component_graph())
    assert "power iteration" in caplog.text
    assert "numpy" in caplog.text
    assert ev["a"] > 0.5                       # and it still answers


def test_the_missing_solver_is_reported_once_not_per_component(without_numpy,
                                                               caplog):
    """One line per run, not one per component of every graph in a corpus."""
    with caplog.at_level("WARNING", logger="SkeneGraph-Net.metrics"):
        for _ in range(3):
            _safe_eigenvector(_two_component_graph())
    assert caplog.text.count("power iteration") == 1


def test_an_ordinary_solver_failure_is_not_reported_as_a_missing_install(
        without_numpy, caplog):
    """The second solver failing is a different event, and keeps its own
    message: which component, how big, and who is being scored 0."""
    import networkx as nx
    monkey = nx.eigenvector_centrality

    def refuses(*a, **k):
        raise nx.PowerIterationFailedConvergence(1000)

    try:
        nx.eigenvector_centrality = refuses
        with caplog.at_level("WARNING", logger="SkeneGraph-Net.metrics"):
            ev = _safe_eigenvector(_two_component_graph())
    finally:
        nx.eigenvector_centrality = monkey
    assert "failed on a component" in caplog.text
    assert all(v == 0.0 for v in ev.values())
