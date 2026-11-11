"""partOf aggregation: id rewriting, mute re-derivation, edge multiplicity."""

from __future__ import annotations

from conftest import move, sp, stage
from aggregation import (absorb_silent_parts, aggregatable_groups,
                         aggregate_play, build_partof_map)
from network import build_static
from parser import Relation
from segmentation import segment_stage_directions


# ---------------------------------------------------------------------------
# The partOf map
# ---------------------------------------------------------------------------

def test_partof_map_is_transitive():
    rels = [Relation("partOf", "a", "b"), Relation("partOf", "b", "c")]
    assert build_partof_map(rels) == {"a": "c", "b": "c"}


def test_partof_map_ignores_other_relation_names():
    assert build_partof_map([Relation("spouse", "a", "b")]) == {}


def test_partof_map_survives_a_cycle():
    rels = [Relation("partOf", "a", "b"), Relation("partOf", "b", "a")]
    assert build_partof_map(rels)          # terminates, does not hang


# ---------------------------------------------------------------------------
# Selecting an intermediate group
# ---------------------------------------------------------------------------

NESTED = [Relation("partOf", "a", "b"), Relation("partOf", "b", "c")]


def test_selecting_an_intermediate_group_aggregates_into_it():
    """A partOf B partOf C, with B selected: A collapses into B, and C is
    left standing.  Resolving to the top first and filtering afterwards made
    this selection a silent no-op."""
    assert build_partof_map(NESTED, groups={"b"}) == {"a": "b"}


def test_selecting_the_top_group_reaches_through_the_middle():
    assert build_partof_map(NESTED, groups={"c"}) == {"a": "c", "b": "c"}


def test_selecting_both_ends_at_the_highest():
    assert build_partof_map(NESTED, groups={"b", "c"}) == {"a": "c", "b": "c"}


def test_an_unselected_chain_maps_nothing():
    assert build_partof_map(NESTED, groups={"elsewhere"}) == {}


def test_an_intermediate_group_is_offered_as_a_target(tiny_play):
    """What the dashboard offers as a checkbox, `aggregate_play` must honour:
    both lists come from `aggregatable_groups`."""
    play = tiny_play(["a", "b:group", "c:group"],
                     sp("a", "one") + "\n" + sp("b", "two"))
    play.relations = list(NESTED)
    assert aggregatable_groups(play) == ["b", "c"]
    for group in aggregatable_groups(play):
        assert aggregate_play(play, groups={group}) is not play, group


# ---------------------------------------------------------------------------
# Rewriting
# ---------------------------------------------------------------------------

def test_no_relations_returns_the_same_object(tiny_play):
    play = tiny_play(["a"], sp("a", "one"))
    assert aggregate_play(play) is play


def test_members_collapse_into_their_group(demo_play):
    pmap = build_partof_map(demo_play.relations)
    assert pmap, "demo play should declare partOf relations"
    agg = aggregate_play(demo_play)

    for member, group in pmap.items():
        assert member not in agg.characters
        assert group in agg.characters
    assert len(agg.characters) == len(demo_play.characters) - len(pmap)


def test_speech_and_move_ids_are_rewritten(demo_play):
    pmap = build_partof_map(demo_play.relations)
    agg = aggregate_play(demo_play)
    members = set(pmap)

    for s in agg.speeches:
        assert not (s.who & members)
    for m in agg.moves:
        assert not (m.who & members)
        assert not (m.corresp & members)


def test_original_play_is_not_mutated(demo_play):
    before = {cid: set(s.who) for cid, s in enumerate(demo_play.speeches)}
    aggregate_play(demo_play)
    after = {cid: set(s.who) for cid, s in enumerate(demo_play.speeches)}
    assert before == after


def test_group_selection_limits_the_rewrite(demo_play):
    pmap = build_partof_map(demo_play.relations)
    groups = set(pmap.values())
    if len(groups) < 1:
        return
    agg = aggregate_play(demo_play, groups=set())
    assert agg is demo_play, "empty group set should be a no-op"


def test_aggregated_group_absorbs_chorus_flag(demo_play):
    pmap = build_partof_map(demo_play.relations)
    agg = aggregate_play(demo_play)
    for group in set(pmap.values()):
        assert agg.characters[group].is_collective is True


def test_muteness_is_re_derived_after_aggregation(tiny_play):
    """A group whose members never speak stays mute; give one member a speech
    and the group becomes a speaker."""
    play = tiny_play(["m1", "m2", "other", "g:group"], sp("other", "a word"))
    play.relations = [Relation("partOf", "m1", "g"),
                      Relation("partOf", "m2", "g")]
    agg = aggregate_play(play)
    assert agg.characters["g"].is_mute is True

    play2 = tiny_play(["m1", "m2", "other", "g:group"],
                      sp("other", "a word") + "\n" + sp("m1", "a word"))
    play2.relations = [Relation("partOf", "m1", "g"),
                       Relation("partOf", "m2", "g")]
    agg2 = aggregate_play(play2)
    assert agg2.characters["g"].is_mute is False


def test_group_with_only_a_textless_speech_is_not_mute(tiny_play):
    """The aggregated rule must match `parser._classify_mutes`: a member whose
    single utterance has lost its text still makes the group a speaker."""
    play = tiny_play(["m1", "m2", "other", "g:group"],
                     sp("other", "a word") + "\n" + sp("m1"))
    play.relations = [Relation("partOf", "m1", "g"),
                      Relation("partOf", "m2", "g")]
    agg = aggregate_play(play)
    assert agg.characters["g"].is_mute is False


# ---------------------------------------------------------------------------
# Effect on the graph
# ---------------------------------------------------------------------------

def test_edge_multiplicity_sums_across_segments(tiny_play):
    """A-C in one segment and B-C in another, with A and B both partOf G,
    become a single G-C edge of weight 2."""
    body = "\n".join([
        stage(move("entrance", "p1 c")),
        sp("p1", "one"),
        stage(move("exit", "p1"), move("entrance", "p2")),
        sp("p2", "two"),
    ])
    play = tiny_play(["p1", "p2", "c", "g:group"], body)
    play.relations = [Relation("partOf", "p1", "g"),
                      Relation("partOf", "p2", "g")]

    raw = build_static(segment_stage_directions(play), play.characters)
    assert raw["p1"]["c"]["weight"] == 1
    assert raw["p2"]["c"]["weight"] == 1

    agg = aggregate_play(play)
    merged = build_static(segment_stage_directions(agg), agg.characters)
    assert merged["g"]["c"]["weight"] == 2


def test_split_move_becomes_a_no_op_under_aggregation(tiny_play):
    """<move type="split" who="#g" corresp="#p1 #p2"> divides the chorus into
    parts aggregation has already merged, so nothing moves: nobody leaves and
    the group stays where it was."""
    body = stage(move("entrance", "g")) + "\n" + stage(move("split", "g", corresp="p1 p2"))
    play = tiny_play(["g:group", "p1", "p2"], body)
    play.relations = [Relation("partOf", "p1", "g"),
                      Relation("partOf", "p2", "g")]
    agg = aggregate_play(play)

    split = [m for m in agg.moves if m.type == "split"][0]
    assert split.who == set()
    assert split.corresp == {"g"}

    segs = segment_stage_directions(agg)
    assert all(s.characters_present <= {"g"} for s in segs)
    assert segs[-1].characters_present == {"g"}


# ---------------------------------------------------------------------------
# Staggered arrivals and departures
# ---------------------------------------------------------------------------

def test_a_group_stays_until_its_last_present_member_leaves(tiny_play):
    """Two parts enter, one leaves, the other stays, a third figure arrives.

    Rewriting the ids alone made the first part's exit take the whole group
    off stage: the later segments lost the group, and with it the edge to
    whoever it was standing beside.
    """
    body = "\n".join([
        stage(move("entrance", "p1 p2")),
        sp("p1", "one"),
        stage(move("exit", "p2")),
        sp("p1", "two"),
        stage(move("entrance", "c")),
        sp("c", "three"),
    ])
    play = tiny_play(["p1", "p2", "c", "g:group"], body)
    play.relations = [Relation("partOf", "p1", "g"),
                      Relation("partOf", "p2", "g")]

    agg = aggregate_play(play)
    casts = [s.characters_present for s in segment_stage_directions(agg)]
    assert casts == [{"g"}, {"g"}, {"g", "c"}]

    graph = build_static(segment_stage_directions(agg), agg.characters)
    assert graph.has_edge("g", "c")


def test_the_group_leaves_when_the_last_member_does(tiny_play):
    """The mirror case: the fix must not pin the group on stage for good."""
    body = "\n".join([
        stage(move("entrance", "p1 p2")),
        sp("p1", "one"),
        stage(move("exit", "p2")),
        stage(move("exit", "p1")),
        stage(move("entrance", "c")),
        sp("c", "two"),
    ])
    play = tiny_play(["p1", "p2", "c", "g:group"], body)
    play.relations = [Relation("partOf", "p1", "g"),
                      Relation("partOf", "p2", "g")]

    agg = aggregate_play(play)
    casts = [s.characters_present for s in segment_stage_directions(agg)]
    assert casts == [{"g"}, {"g"}, set(), {"c"}]

    graph = build_static(segment_stage_directions(agg), agg.characters)
    assert not graph.has_edge("g", "c")


def test_a_member_exit_keeps_its_segment_boundary(tiny_play):
    """The exit still opens a segment even when it moves nobody: the spine is
    cut by the annotation, not by the cast that results from it."""
    body = "\n".join([
        stage(move("entrance", "p1 p2")),
        sp("p1", "one"),
        stage(move("exit", "p2")),
        sp("p1", "two"),
    ])
    play = tiny_play(["p1", "p2", "g:group"], body)
    play.relations = [Relation("partOf", "p1", "g"),
                      Relation("partOf", "p2", "g")]

    raw = segment_stage_directions(play)
    agg = segment_stage_directions(aggregate_play(play))
    assert len(agg) == len(raw)


def test_a_non_member_leaving_beside_a_member_still_leaves(tiny_play):
    """One exit naming both a part and an outsider: the outsider goes, the
    group stays because its other part is still on stage."""
    body = "\n".join([
        stage(move("entrance", "p1 p2 c")),
        sp("p1", "one"),
        stage(move("exit", "p2 c")),
        sp("p1", "two"),
    ])
    play = tiny_play(["p1", "p2", "c", "g:group"], body)
    play.relations = [Relation("partOf", "p1", "g"),
                      Relation("partOf", "p2", "g")]

    agg = aggregate_play(play)
    exit_move = [m for m in agg.moves if m.type == "exit"][0]
    assert exit_move.who == {"c"}
    casts = [s.characters_present for s in segment_stage_directions(agg)]
    assert casts == [{"g", "c"}, {"g"}]


def test_aggregated_presence_is_the_projection_of_raw_presence(demo_play):
    """The general statement of the two cases above, on real data: whoever is
    on stage under aggregation is exactly the raw cast with each member read
    as its group, segment by segment, on all three spines."""
    from segmentation import SEGMENTERS

    pmap = build_partof_map(demo_play.relations)
    assert pmap, "demo play should declare partOf relations"
    agg = aggregate_play(demo_play)
    for name, segmenter in sorted(SEGMENTERS.items()):
        raw_segs, agg_segs = segmenter(demo_play), segmenter(agg)
        assert len(raw_segs) == len(agg_segs), name
        for raw, got in zip(raw_segs, agg_segs):
            projected = {pmap.get(c, c) for c in raw.characters_present}
            assert got.characters_present == projected, f"{name} {raw.label}"


def test_aggregation_lowers_order_and_can_raise_density(demo_play, demo_segments):
    """The documented consequence for the density x order scatter."""
    raw_g = build_static(demo_segments["middle-seq"], demo_play.characters)
    agg = aggregate_play(demo_play)
    from segmentation import segment_middle_seq
    agg_g = build_static(segment_middle_seq(agg), agg.characters)
    assert agg_g.number_of_nodes() < raw_g.number_of_nodes()


# ---------------------------------------------------------------------------
# Silent parts of a speaking figure
# ---------------------------------------------------------------------------

def _eccl_shaped(tiny_play):
    """A chorus that arrives in two silent parts and only sings once whole.

    The shape of Ecclesiazusae: the parts enter separately during the
    prologue, are merged into the chorus, and never speak under their own
    ids -- so token by token they look like play-level mutes.
    """
    body = (stage(move("onStage"))
            + stage(move("entrance", "gyne partA")) + sp("gyne", "alpha")
            + stage(move("entrance", "partB")) + sp("gyne", "beta")
            + stage(move("merge", "partA partB", corresp="choros"))
            + sp("choros", "gamma")
            + stage(move("exit", "gyne choros")) + stage(move("onStage")))
    play = tiny_play(["gyne", "partA", "partB", "choros"], body)
    play.relations = [Relation("partOf", "partA", "choros"),
                      Relation("partOf", "partB", "choros")]
    return play


def test_silent_parts_are_absorbed_into_the_speaking_figure(tiny_play):
    """Under p-speaking the chorus must be present where its parts are.

    The parts carry no <sp>, so the mutes-out filter dropped them and the
    chorus vanished from the prologue although it stood on stage in parts.
    """
    play = _eccl_shaped(tiny_play)
    assert play.characters["partA"].is_mute and play.characters["partB"].is_mute
    absorbed = absorb_silent_parts(play)
    assert "partA" not in absorbed.characters and "partB" not in absorbed.characters

    segs = segment_stage_directions(absorbed)
    G = build_static(segs, absorbed.characters, include_mutes=False,
                     segment_cast="stage")
    assert G.has_node("choros")
    assert G.has_edge("gyne", "choros"), (
        "the chorus stands on stage with gyne from its first part")


def test_speaking_parts_are_left_alone(tiny_play):
    """A part that speaks in its own right is not absorbed -- collapsing
    those is what the aggregation toggle is for."""
    body = (stage(move("onStage"))
            + stage(move("entrance", "gyne half")) + sp("half", "alpha")
            + stage(move("exit", "gyne half")) + stage(move("onStage")))
    play = tiny_play(["gyne", "half", "choros"], body)
    play.relations = [Relation("partOf", "half", "choros")]
    assert absorb_silent_parts(play) is play


def test_absorption_keeps_the_aggregation_toggle_monotonic(tiny_play):
    """Collapsing a group must never add edges.

    Before absorption the toggle handed the parts' presence to a chorus that
    had none of it, so aggregating Ecclesiazusae *raised* the edge count.
    """
    play = _eccl_shaped(tiny_play)
    absorbed = absorb_silent_parts(play)
    raw = build_static(segment_stage_directions(absorbed), absorbed.characters,
                       include_mutes=False, segment_cast="stage")
    agg_play = aggregate_play(absorbed, groups={"choros"})
    agg = build_static(segment_stage_directions(agg_play), agg_play.characters,
                       include_mutes=False, segment_cast="stage")
    assert agg.number_of_edges() <= raw.number_of_edges()
