"""Graph construction: the three network models, segment casts and weights."""

from __future__ import annotations

import pytest

from conftest import move, sp, stage
from network import build_dynamic, build_dynamic_spell_graph, build_static
from segmentation import segment_middle_seq, segment_stage_directions

# The three models, as (include_mutes, segment_cast).
MODELS = {
    "full":    dict(include_mutes=True,  segment_cast="stage"),
    "p-speaking": dict(include_mutes=False, segment_cast="stage"),
    "s-speaking": dict(include_mutes=False, segment_cast="speaking"),
}


@pytest.fixture
def graphs(demo_play, demo_segments):
    segs = demo_segments["middle-seq"]
    return {name: build_static(segs, demo_play.characters, **kw)
            for name, kw in MODELS.items()}


# ---------------------------------------------------------------------------
# Node sets
# ---------------------------------------------------------------------------

def test_stage_model_includes_mutes(graphs, demo_play):
    stage_nodes = set(graphs["full"].nodes())
    mutes = {c.id for c in demo_play.characters.values() if c.is_mute}
    assert stage_nodes & mutes, "stage model should keep play-level mutes"


def test_speaking_models_drop_mutes(graphs, demo_play):
    mutes = {c.id for c in demo_play.characters.values() if c.is_mute}
    for name in ("p-speaking", "s-speaking"):
        assert not (set(graphs[name].nodes()) & mutes), name


def test_node_sets_are_nested(graphs):
    stage_n = set(graphs["full"].nodes())
    p_speaking_n = set(graphs["p-speaking"].nodes())
    s_speaking_n = set(graphs["s-speaking"].nodes())
    assert p_speaking_n <= stage_n
    # Both mutes-out models share the same play-level cast filter.
    assert p_speaking_n == s_speaking_n


def test_speaking_cast_edges_are_a_subset_of_on_stage_edges(graphs):
    """Speakers in a segment are always present in it, so the speaking cast can only
    ever be a stricter segment cast."""
    dial = {frozenset(e) for e in graphs["p-speaking"].edges()}
    cosp = {frozenset(e) for e in graphs["s-speaking"].edges()}
    assert cosp <= dial


def test_edge_counts_decrease_across_the_three_models(graphs):
    assert (graphs["full"].number_of_edges()
            >= graphs["p-speaking"].number_of_edges()
            >= graphs["s-speaking"].number_of_edges())


# ---------------------------------------------------------------------------
# Edge semantics
# ---------------------------------------------------------------------------

def test_copresence_edge_requires_shared_segment(tiny_play):
    """a and b never share a segment -> no edge, though both appear."""
    body = "\n".join([
        stage(move("entrance", "a")),
        sp("a", "one"),
        stage(move("exit", "a"), move("entrance", "b")),
        sp("b", "two"),
    ])
    play = tiny_play(["a", "b"], body)
    G = build_static(segment_stage_directions(play), play.characters)
    assert set(G.nodes()) == {"a", "b"}
    assert G.number_of_edges() == 0


def test_speaking_cast_needs_both_to_speak_in_the_same_segment(tiny_play):
    """Both on stage together, but only one speaks in that segment."""
    body = "\n".join([
        stage(move("entrance", "a b")),
        sp("a", "one"),
        stage(move("entrance", "c")),
        sp("b", "two"),
        sp("c", "three"),
    ])
    play = tiny_play(["a", "b", "c"], body)
    segs = segment_stage_directions(play)

    presence = build_static(segs, play.characters, include_mutes=False,
                            segment_cast="stage")
    s_speaking = build_static(segs, play.characters, include_mutes=False,
                            segment_cast="speaking")
    assert presence.has_edge("a", "b")          # co-present in segment 1
    assert not s_speaking.has_edge("a", "b")      # but never both speaking in one segment
    assert s_speaking.has_edge("b", "c")          # both speak in segment 2


def test_mute_is_excluded_under_speaking_cast_but_linked_under_stage_cast(tiny_play):
    body = "\n".join([
        stage(move("entrance", "hero attendant")),
        sp("hero", "a word"),                   # attendant never speaks -> mute
    ])
    play = tiny_play(["hero", "attendant"], body)
    segs = segment_stage_directions(play)

    stage_g = build_static(segs, play.characters, include_mutes=True,
                           segment_cast="stage")
    assert stage_g.has_edge("hero", "attendant")

    s_speaking_g = build_static(segs, play.characters, include_mutes=False,
                              segment_cast="speaking")
    assert "attendant" not in s_speaking_g.nodes()


def test_textless_speech_makes_a_speaking_cast_node(tiny_play):
    """A chorus whose song is lost is a speaker, so it survives into the
    mutes-out model instead of vanishing from it."""
    body = "\n".join([
        stage(move("entrance", "hero choros")),
        sp("hero", "a word"),
        sp("choros"),                           # the lost song
    ])
    play = tiny_play(["hero", "choros"], body)
    segs = segment_stage_directions(play)

    s_speaking_g = build_static(segs, play.characters, include_mutes=False,
                              segment_cast="speaking")
    assert "choros" in s_speaking_g.nodes()
    assert s_speaking_g.has_edge("hero", "choros")


# ---------------------------------------------------------------------------
# Edge weights
# ---------------------------------------------------------------------------

def test_default_weight_counts_shared_segments(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a b")),
        sp("a", "one"),
        stage(move("entrance", "c")),
        sp("a", "two"),
    ])
    play = tiny_play(["a", "b", "c"], body)
    G = build_static(segment_stage_directions(play), play.characters)
    # a and b are co-present in both segments; c joins only the second.
    assert G["a"]["b"]["weight"] == 2
    assert G["a"]["c"]["weight"] == 1


def test_weight_attributes_are_consistent(graphs):
    for name, G in graphs.items():
        for _, _, d in G.edges(data=True):
            assert d["weight"] == d["segments_shared"], name
            assert d["words_shared"] >= 0
            assert len(d["segment_ids"]) == d["segments_shared"]


def test_word_weighting_option(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a b")),
        sp("a", "one two three"),
    ])
    play = tiny_play(["a", "b"], body)
    segs = segment_stage_directions(play)
    G = build_static(segs, play.characters, edge_weight="words")
    assert G["a"]["b"]["weight"] == 3


def test_graph_records_its_model(demo_play, demo_segments):
    segs = demo_segments["middle-seq"]
    G = build_static(segs, demo_play.characters, include_mutes=False,
                     segment_cast="speaking")
    assert G.graph["include_mutes"] is False
    assert G.graph["segment_cast"] == "speaking"
    assert G.graph["num_segments"] == len(segs)


# ---------------------------------------------------------------------------
# Dynamic graphs
# ---------------------------------------------------------------------------

def test_dynamic_has_one_graph_per_segment(demo_play, demo_segments):
    segs = demo_segments["middle-seq"]
    graphs = build_dynamic(segs, demo_play.characters)
    assert len(graphs) == len(segs)


def test_dynamic_shares_one_node_set(demo_play, demo_segments):
    segs = demo_segments["middle-seq"]
    graphs = build_dynamic(segs, demo_play.characters)
    node_sets = {frozenset(g.nodes()) for g in graphs}
    assert len(node_sets) == 1, "node set must be stable across frames"


def test_dynamic_marks_presence_per_frame(demo_play, demo_segments):
    segs = demo_segments["middle-seq"]
    graphs = build_dynamic(segs, demo_play.characters)
    for seg, g in zip(segs, graphs):
        present = {n for n, d in g.nodes(data=True) if d["is_present"]}
        assert present == seg.characters_present & set(g.nodes())


def _one_body_pairs(cast, characters):
    """Pairs of the cast that are a collective and its own part."""
    from itertools import combinations
    return sum(1 for a, b in combinations(cast, 2)
               if b in characters[a].part_of or a in characters[b].part_of)


def test_per_segment_frame_is_a_clique(demo_play, demo_segments):
    """Every segment's edge set is complete on its active cast, but for a
    collective and its own part -- the reason the dynamic view encodes words
    rather than degree."""
    segs = demo_segments["middle-seq"]
    split = 0
    for seg, g in zip(segs, build_dynamic(segs, demo_play.characters)):
        present = [n for n, d in g.nodes(data=True) if d["is_present"]]
        k = len(present)
        one_body = _one_body_pairs(present, demo_play.characters)
        split += one_body
        assert g.number_of_edges() == k * (k - 1) // 2 - one_body
    assert split, "Lysistrata's middle sequences hold a chorus and its halves"


def test_spell_graph_intervals_are_well_formed(demo_play, demo_segments):
    segs = demo_segments["middle-seq"]
    G = build_dynamic_spell_graph(segs, demo_play.characters)
    for _, data in G.nodes(data=True):
        for start, end in data["spells"]:
            assert start < end
    for _, _, data in G.edges(data=True):
        assert data["weight"] == sum(e - s for s, e in data["spells"])


@pytest.mark.parametrize("builder", [build_static, build_dynamic_spell_graph])
@pytest.mark.parametrize("model", list(MODELS))
def test_node_insertion_order_is_deterministic(demo_play, demo_segments,
                                               builder, model):
    """Nodes go in sorted, so the exported files are reproducible.

    The kept-character set is a `set`; iterating it directly makes insertion
    order depend on the hash seed.  In the GEXF that shows up twice -- as the
    order of the <node> elements and, because networkx reports an edge from
    whichever endpoint it stored first, as the source/target orientation of
    every <edge>.  Two identical runs then produced different bytes for the
    same graph.
    """
    G = builder(demo_segments["middle-seq"], demo_play.characters,
                **MODELS[model])
    assert list(G.nodes()) == sorted(G.nodes())


# ---------------------------------------------------------------------------
# A collective and its own parts
# ---------------------------------------------------------------------------

_PARTOF = ('      <listRelation>\n'
           '        <relation name="partOf" active="#half1 #half2" passive="#chorus"/>\n'
           '      </listRelation>')


def _split_in_one_unit(tiny_play):
    """A chorus that splits inside a single middle sequence, so the unit
    holds the whole and both halves."""
    from conftest import milestone
    body = "\n".join([
        milestone("middle-seq", "s1"),
        stage(move("entrance", "a chorus")), sp("chorus", "one"),
        stage(move("split", "chorus", corresp="half1 half2")),
        sp("half1", "two"), sp("half2", "three"), sp("a", "four"),
    ])
    return tiny_play(["a", "chorus:group", "half1:group", "half2:group"],
                     body, profile_extra=_PARTOF)


def test_no_graph_joins_a_chorus_to_its_own_halves(tiny_play):
    """A part and its whole are one body.  A textual unit holding a split
    holds both, and its clique used to join the chorus to its own halves."""
    play = _split_in_one_unit(tiny_play)
    segs = segment_middle_seq(play)
    assert segs[0].characters_present >= {"chorus", "half1", "half2"}
    for name, kw in MODELS.items():
        static = build_static(segs, play.characters, **kw)
        spell = build_dynamic_spell_graph(segs, play.characters, **kw)
        dynamic = build_dynamic(segs, play.characters, **kw)
        for G in [static, spell] + dynamic:
            for half in ("half1", "half2"):
                assert not G.has_edge("chorus", half), name
        # Everyone else is still joined: the halves to each other, and the
        # chorus and its halves to a.
        assert static.has_edge("half1", "half2"), name
        assert static.has_edge("a", "chorus") and static.has_edge("a", "half1"), name


def test_no_demo_graph_joins_a_part_to_its_whole(demo_play, demo_segments):
    """Lysistrata's middle sequences hold the chorus beside its two halves."""
    for spine, segs in demo_segments.items():
        for name, kw in MODELS.items():
            G = build_static(segs, demo_play.characters, **kw)
            for cid, ch in demo_play.characters.items():
                for whole in ch.part_of:
                    assert not G.has_edge(cid, whole), (spine, name, cid)
