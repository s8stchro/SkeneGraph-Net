"""Segmentation: the three spines, structural triggers, and the model fold."""

from __future__ import annotations

import pytest

from conftest import milestone, move, sp, stage
from metrics import compute_metrics, compute_speech_distribution
from network import build_static
from segmentation import (SEGMENTERS, Segment, active_span,
                          fold_for_model, fold_segments,
                          segment_stage_directions, segment_large_seq,
                          segment_middle_seq)


# ---------------------------------------------------------------------------
# Stage-direction spine
# ---------------------------------------------------------------------------

def test_structural_move_opens_a_segment(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a")),
        sp("a", "one"),
        stage(move("entrance", "b")),
        sp("b", "two"),
    ])
    segs = segment_stage_directions(tiny_play(["a", "b"], body))
    assert len(segs) == 2
    assert segs[0].characters_present == {"a"}
    assert segs[1].characters_present == {"a", "b"}


def test_state_change_does_not_open_a_segment(tiny_play):
    """The defining asymmetry of the sd spine: state-change applies its
    effect without cutting a boundary."""
    body = "\n".join([
        stage(move("entrance", "a")),
        sp("a", "one"),
        stage(move("state-change", "a", ana="#asleep")),
        sp("a", "two"),
    ])
    segs = segment_stage_directions(tiny_play(["a"], body))
    assert len(segs) == 1
    assert segs[0].word_count == 2


def test_exit_opens_a_segment(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a b")),
        sp("a", "one"),
        stage(move("exit", "b")),
        sp("a", "two"),
    ])
    segs = segment_stage_directions(tiny_play(["a", "b"], body))
    assert len(segs) == 2
    assert segs[1].characters_present == {"a"}


def test_leading_empty_onstage_is_its_own_segment(tiny_play):
    """The pre-play empty-stage marker stands alone (Trilcke/Fischer
    convention), so it does not absorb the first beat."""
    body = "\n".join([
        stage(move("onStage", "")),
        stage(move("entrance", "a")),
        sp("a", "one"),
    ])
    segs = segment_stage_directions(tiny_play(["a"], body))
    assert segs[0].characters_present == set()
    assert segs[0].is_initial is True
    assert segs[1].characters_present == {"a"}


def test_segment_ids_are_one_indexed_and_contiguous(demo_segments):
    for name, segs in demo_segments.items():
        assert [s.id for s in segs] == list(range(1, len(segs) + 1)), name


# ---------------------------------------------------------------------------
# Segment.speakers / silent_present
# ---------------------------------------------------------------------------

def test_textless_speech_credits_its_speaker(tiny_play):
    """An utterance whose text is lost still happened: the <sp>, not the word
    count, decides who spoke.  This is what makes the XOPOY interludes of
    Plutus and Ecclesiazusae record a performing chorus rather than an empty
    stage."""
    body = "\n".join([
        stage(move("entrance", "a b")),
        sp("a", "a word"),
        sp("b"),                       # textless <sp><l/></sp>
    ])
    segs = segment_stage_directions(tiny_play(["a", "b"], body))
    assert segs[0].speakers == {"a", "b"}
    assert segs[0].silent_present == set()
    assert segs[0].word_count == 2      # but it contributes no words


def test_present_without_a_speech_is_silent(tiny_play):
    """The contrast case: on stage, but the text attributes no utterance."""
    body = "\n".join([
        stage(move("entrance", "a b")),
        sp("a", "a word"),
    ])
    segs = segment_stage_directions(tiny_play(["a", "b"], body))
    assert segs[0].speakers == {"a"}
    assert segs[0].silent_present == {"b"}


def test_speakers_subset_of_present_on_milestone_spines(demo_segments):
    for name in ("large-seq", "middle-seq"):
        for s in demo_segments[name]:
            assert s.speakers <= s.characters_present, f"{name} seg {s.id}"


def test_word_count_is_sum_of_attributed_speech_words(demo_segments):
    for name, segs in demo_segments.items():
        for s in segs:
            assert s.word_count == sum(sp_.attributed_words
                                       for sp_ in s.speeches)


def test_segment_words_sum_to_the_play_total(demo_play, demo_segments):
    """The one word rule, end to end: whatever the spine, the segment totals
    add up to the play total the metrics panel shows.

    Discriminating on the demo play, which has a four-speaker joint speech:
    under a per-<sp> segment count the spines came out six words short.
    """
    total = compute_speech_distribution(demo_play)["total_words_spoken"]
    for name, segs in demo_segments.items():
        assert sum(s.word_count for s in segs) == total, name


def test_joint_speech_is_credited_once_per_speaker_in_its_segment(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a b")),
        sp("a b", "one two"),
    ])
    segs = segment_stage_directions(tiny_play(["a", "b"], body))
    assert segs[0].word_count == 4        # 2 words x 2 speakers


def test_active_span_drops_only_empty_bookends(tiny_play):
    """The span trims housekeeping, not content.

    One definition serves the temporal Gini and the corpus chorus chart,
    whose agreement §5 and §11 assert; it used to be written out twice.
    A bookend holding one silent figure is a beat of the play and stays.
    """
    body = "\n".join([
        stage(move("onStage", "")),                 # empty pre-play marker
        stage(move("entrance", "a b")),
        sp("a", "one two"),
        stage(move("exit", "a")),
        sp("b", "three"),
        stage(move("exit", "b")),                   # empty terminal stage
    ])
    segs = segment_stage_directions(tiny_play(["a", "b"], body))
    span = active_span(segs)
    assert not segs[0].characters_present and not segs[-1].characters_present
    assert span == segs[1:-1]
    assert all(s.characters_present for s in span)


def test_active_span_keeps_a_bookend_with_anyone_on_stage(tiny_play):
    body = "\n".join([
        stage(move("entrance", "a")),               # opens with a on stage
        sp("a", "one"),
    ])
    segs = segment_stage_directions(tiny_play(["a"], body))
    assert active_span(segs) == segs


def test_segment_has_no_verse_count_field():
    """Regression guard for the verse->word migration."""
    assert not hasattr(Segment(id=1, label="x"), "verse_count")


# ---------------------------------------------------------------------------
# Milestone spines
# ---------------------------------------------------------------------------

def test_one_segment_per_milestone(tiny_play):
    body = "\n".join([
        milestone("large-seq", "L01"),
        stage(move("entrance", "a")),
        sp("a", "one"),
        milestone("large-seq", "L02"),
        sp("a", "two"),
    ])
    play = tiny_play(["a"], body)
    assert len(segment_large_seq(play)) == 2
    assert segment_middle_seq(play) == []      # no middle-seq milestones


def test_milestone_segment_labels_carry_the_unit_name(demo_segments):
    assert all(s.label.startswith("large-seq-")
               for s in demo_segments["large-seq"])
    assert all(s.label.startswith("middle-seq-")
               for s in demo_segments["middle-seq"])


def test_no_legacy_div_terminology_in_labels(demo_segments):
    """Regression guard for the div2/div3 -> large-seq/middle-seq rename."""
    for segs in demo_segments.values():
        for s in segs:
            assert "div2" not in s.label and "div3" not in s.label


def test_all_three_spines_are_non_empty(demo_segments):
    for name, segs in demo_segments.items():
        assert segs, f"{name} produced no segments"


def test_spines_cover_the_same_speeches(demo_play, demo_segments):
    """Every spine partitions the play's speeches, so the totals agree."""
    totals = {name: sum(s.word_count for s in segs)
              for name, segs in demo_segments.items()}
    assert len(set(totals.values())) == 1, totals


# ---------------------------------------------------------------------------
# Model-specific fold
# ---------------------------------------------------------------------------

def _speaking_cast(play, segs):
    kept = set(build_static(segs, play.characters, include_mutes=False,
                            segment_cast="stage").nodes())
    return lambda s: s.characters_present & kept


def test_fold_merges_adjacent_identical_casts(demo_play, demo_segments):
    segs = demo_segments["sd"]
    folded = fold_segments(segs, _speaking_cast(demo_play, segs))
    assert len(folded) <= len(segs)
    assert len(folded) < len(segs), "demo play should have foldable boundaries"


def test_speaking_fold_ignores_a_boundary_crossed_in_silence(tiny_play):
    """A figure who crosses a boundary without speaking must not separate
    two characters who speak on either side of it -- and it must make no
    difference whether that figure speaks elsewhere in the play.

    seg 1: a, b present, a speaks | seg 2: servant enters mute, b speaks.
    Under s-speaking a and b belong to one segment and are joined, because
    the only thing the boundary changed is the presence of someone silent
    on both sides of it.  The app used to fold on the kept cast alone, so
    the merge happened only when the servant was a play-level mute: a
    servant who spoke in some later scene became a node, the casts then
    differed, and a and b lost their edge.
    """
    core = (stage(move("onStage")) + stage(move("entrance", "a b")) + sp("a", "x")
            + stage(move("entrance", "servant")) + sp("b", "y"))
    bodies = {
        "silent everywhere": core + stage(move("exit", "a b servant")),
        "speaks later":      core + stage(move("exit", "a")) + sp("servant", "z")
                                  + stage(move("exit", "b servant")),
    }
    for label, body in bodies.items():
        play = tiny_play(["a", "b", "servant"], body)
        segs = segment_stage_directions(play)
        kept = set(build_static(segs, play.characters, include_mutes=False,
                                segment_cast="speaking").nodes())
        folded = fold_for_model(segs, kept, "speaking")
        G = build_static(folded, play.characters, include_mutes=False,
                         segment_cast="speaking")
        assert G.has_edge("a", "b"), (
            f"{label}: a and b speak on either side of a silent entrance "
            "and must be joined")


def test_speaking_fold_keeps_a_boundary_a_speaker_crosses(tiny_play):
    """The converse: a boundary that a speaking character crosses is real."""
    body = (stage(move("onStage")) + stage(move("entrance", "a b")) + sp("a", "x")
            + stage(move("exit", "a")) + sp("b", "y")
            + stage(move("exit", "b")))
    play = tiny_play(["a", "b"], body)
    segs = segment_stage_directions(play)
    kept = set(build_static(segs, play.characters, include_mutes=False,
                            segment_cast="speaking").nodes())
    folded = fold_for_model(segs, kept, "speaking")
    G = build_static(folded, play.characters, include_mutes=False,
                     segment_cast="speaking")
    # `a` leaves at the boundary and speaks before it, so the segments stay
    # apart and the two never share one.
    assert not G.has_edge("a", "b")


def test_speaking_fold_sees_a_silent_exit_followed_by_a_speaking_return(tiny_play):
    """Who crosses a boundary is read off the stage on either side of it,
    not off everyone the run has held.

    seg 1: a, b, c present, a speaks | seg 2: b leaves in silence, c speaks
    | seg 3: b returns and speaks.  The run accumulated by segment 2 still
    remembers b from segment 1, so against the union b never appears to
    enter at the second boundary: all three folded into one segment, b's
    return vanished, and b was joined to a and to c although b spoke with
    neither.  Against the stage as it stands, b enters and speaks, so the
    boundary is the model's to see.
    """
    body = (stage(move("onStage")) + stage(move("entrance", "a b c")) + sp("a", "x")
            + stage(move("exit", "b")) + sp("c", "y")
            + stage(move("entrance", "b")) + sp("b", "z")
            + stage(move("exit", "a b c")))
    play = tiny_play(["a", "b", "c"], body)
    segs = segment_stage_directions(play)
    kept = set(build_static(segs, play.characters, include_mutes=False,
                            segment_cast="speaking").nodes())
    folded = fold_for_model(segs, kept, "speaking")
    G = build_static(folded, play.characters, include_mutes=False,
                     segment_cast="speaking")
    assert not G.has_edge("a", "b"), "b returns after a has spoken"
    assert not G.has_edge("b", "c"), "b returns after c has spoken"
    assert G.has_edge("a", "c"), "a and c speak across a silent departure"


def test_fold_is_topology_preserving(demo_play, demo_segments):
    """The documented invariant: order, size, density, average degree,
    clustering and diameter survive the fold unchanged.

    Asserted for the p-speaking fold, which is an equality fold on the kept
    cast.  The s-speaking fold deliberately merges segments of differing
    cast (see `fold_for_model`) and carries no such guarantee -- the claim
    was once documented for both models, and was false for the second."""
    segs = demo_segments["sd"]
    cast_of = _speaking_cast(demo_play, segs)
    folded = fold_segments(segs, cast_of)

    kw = dict(include_mutes=False, segment_cast="stage")
    before = build_static(segs, demo_play.characters, **kw)
    after = build_static(folded, demo_play.characters, **kw)

    assert set(before.nodes()) == set(after.nodes())
    assert set(map(frozenset, before.edges())) == set(map(frozenset, after.edges()))

    m1, m2 = compute_metrics(before), compute_metrics(after)
    for key in ("size", "numEdges", "density", "averageDegree",
                "averageClustering", "diameter", "averagePathLength",
                "numConnectedComponents", "maxDegree"):
        assert m1[key] == pytest.approx(m2[key]), key


def test_fold_renumbers_ids_contiguously(demo_play, demo_segments):
    segs = demo_segments["sd"]
    folded = fold_segments(segs, _speaking_cast(demo_play, segs))
    assert [s.id for s in folded] == list(range(1, len(folded) + 1))


def test_fold_preserves_endpoints(demo_play, demo_segments):
    segs = demo_segments["sd"]
    folded = fold_segments(segs, _speaking_cast(demo_play, segs))
    assert folded[0].is_initial == segs[0].is_initial
    assert folded[-1].is_final == segs[-1].is_final


def test_fold_conserves_words_and_speeches(demo_play, demo_segments):
    segs = demo_segments["sd"]
    folded = fold_segments(segs, _speaking_cast(demo_play, segs))
    assert sum(s.word_count for s in folded) == sum(s.word_count for s in segs)
    assert (sum(len(s.speeches) for s in folded)
            == sum(len(s.speeches) for s in segs))


def test_fold_under_stage_model_is_a_no_op(demo_play, demo_segments):
    """Under stage co-presence every boundary is visible, so nothing folds."""
    segs = demo_segments["sd"]
    folded = fold_segments(segs, lambda s: s.characters_present)
    assert len(folded) == len(segs)


def test_fold_of_empty_input_is_empty():
    assert fold_segments([], lambda s: set()) == []


# ---------------------------------------------------------------------------
# Crossing moves (zero-duration round trips)
# ---------------------------------------------------------------------------

def test_crossing_is_invisible_to_occupancy_but_counted(tiny_play):
    """B6: a crossing joins no cast on any spine, and the segment counts it."""
    body = "\n".join([
        stage(move("entrance", "a")),
        milestone("middle-seq", "s001"),
        sp("a", "one"),
        stage(move("crossing", "t", ana="#fetch-prop")),
        sp("a", "two"),
    ])
    play = tiny_play(["a", "t"], body)
    mid = segment_middle_seq(play)
    assert mid[0].characters_present == {"a"}
    assert mid[0].num_crossings == 1
    sd = segment_stage_directions(play)
    assert all("t" not in s.characters_present for s in sd)
    assert sum(s.num_crossings for s in sd) == 1


def test_crossing_opens_no_stage_direction_segment(tiny_play):
    """B6: a <stage> holding only a crossing is not a structural beat."""
    base = "\n".join([
        stage(move("entrance", "a")), sp("a", "one"),
        stage(move("exit", "a")),
    ])
    withx = "\n".join([
        stage(move("entrance", "a")), sp("a", "one"),
        stage(move("crossing", "t", ana="#fetch-prop")),
        stage(move("exit", "a")),
    ])
    n_base = len(segment_stage_directions(tiny_play(["a", "t"], base)))
    n_with = len(segment_stage_directions(tiny_play(["a", "t"], withx)))
    assert n_with == n_base


# ---------------------------------------------------------------------------
# The segment-level speaking fold, held to its own rule
# ---------------------------------------------------------------------------

def _folded_runs(raw, folded):
    """The raw segments each folded segment was made of, in order."""
    owner = {id(m): f.id for f in folded for m in f.trigger_moves}
    runs = {}
    for s in raw:
        runs.setdefault(owner[id(s.trigger_moves[0])], []).append(s)
    return list(runs.values())


def test_speaking_fold_holds_every_boundary_to_the_whole_segment(demo_play,
                                                                 demo_segments):
    """Inside a merged segment, nobody who crosses one of its boundaries
    speaks anywhere in it.  The greedy fold checked each boundary against the
    speakers gathered so far, so Myrrhine's first entrance folded away
    although she speaks in the merged segment two beats on.  The entrance is
    found in the play, not by line number, so the test survives a refresh of
    the example."""
    segs = demo_segments["sd"]
    kept = set(build_static(segs, demo_play.characters, include_mutes=False,
                            segment_cast="speaking").nodes())
    folded = fold_for_model(segs, kept, "speaking")
    for run in _folded_runs(segs, folded):
        speaking = set().union(*(s.speakers for s in run))
        for a, b in zip(run, run[1:]):
            crossers = ((a.characters_present & kept)
                        ^ (b.characters_present & kept))
            assert not crossers & speaking, (a.label, b.label,
                                             sorted(crossers & speaking))
    entrance = next(m for s in segs for m in s.trigger_moves
                    if m.type == "entrance" and "myrrhine" in m.who)
    assert any(f.trigger_moves[:1] == [entrance] for f in folded), (
        f"Myrrhine's first entrance (line {entrance.source_line}) "
        "must stay a boundary")


def test_speaking_fold_keeps_the_entrance_of_one_who_speaks_later(tiny_play):
    """m enters in silence, b speaks, a mute enters, then m speaks.  The mute's
    entrance is invisible, so m's speech belongs to the segment m entered --
    and m's entrance is a boundary a crosses no longer speaking.  Judged at
    the moment of merging, the fold ran all three together and joined a, who
    fell silent before m arrived, to m."""
    body = (stage(move("onStage")) + stage(move("entrance", "a b"))
            + sp("a", "x")
            + stage(move("entrance", "m")) + sp("b", "y")
            + stage(move("entrance", "mute")) + sp("m", "z")
            + stage(move("exit", "a b m mute")))
    play = tiny_play(["a", "b", "m", "mute"], body)
    segs = segment_stage_directions(play)
    kept = set(build_static(segs, play.characters, include_mutes=False,
                            segment_cast="speaking").nodes())
    folded = fold_for_model(segs, kept, "speaking")
    G = build_static(folded, play.characters, include_mutes=False,
                     segment_cast="speaking")
    assert not G.has_edge("a", "m")
    assert G.has_edge("b", "m"), "the mute's entrance is invisible"


@pytest.mark.parametrize("segment_cast", ["stage", "speaking"])
def test_fold_keeps_the_crossings(demo_play, demo_segments, segment_cast):
    """A crossing stays countable on every spine (Methods §9); the fold used to
    rebuild each segment without it, and both speaking models read 0."""
    segs = demo_segments["sd"]
    kept = set(build_static(segs, demo_play.characters, include_mutes=False,
                            segment_cast=segment_cast).nodes())
    folded = fold_for_model(segs, kept, segment_cast)
    assert len(folded) < len(segs)
    before = [m.source_line for s in segs for m in s.crossings]
    after = [m.source_line for s in folded for m in s.crossings]
    assert before and after == before


# ---------------------------------------------------------------------------
# Annotation gaps the stage-direction spine must survive
# ---------------------------------------------------------------------------

def test_a_speaker_is_in_the_segment_they_speak_in(tiny_play):
    """c speaks with no entrance.  The textual spines have always put a
    speaker in their unit; the stage-direction spine left c out of the cast,
    an isolate there and connected on the other two."""
    body = (milestone("middle-seq", "s1") + stage(move("entrance", "a"))
            + sp("a", "one") + sp("c", "two"))
    play = tiny_play(["a", "c"], body)
    sd = segment_stage_directions(play)
    assert any(s.characters_present >= {"a", "c"} for s in sd)
    for segs in (sd, segment_middle_seq(play)):
        assert build_static(segs, play.characters).has_edge("a", "c")
    # Only the segment is widened: c is not left standing afterwards.
    after = segment_stage_directions(tiny_play(
        ["a", "c"], body + stage(move("exit", "a")) + sp("a", "three")))
    assert "c" not in after[-1].characters_present


def test_bare_moves_still_cut_beats(tiny_play):
    """Moves outside any <stage> break the schema, but are read: each run of
    them between speeches is one beat.  Keyed on None they all joined the
    first one's cluster, and the play collapsed into one segment."""
    body = "\n".join([
        move("entrance", "a"), sp("a", "one two"),
        move("exit", "a"), move("entrance", "b"), sp("b", "three"),
    ])
    play = tiny_play(["a", "b"], body)
    sd = segment_stage_directions(play)
    assert [s.characters_present for s in sd] == [{"a"}, {"b"}]
    assert [len(s.speeches) for s in sd] == [1, 1]
