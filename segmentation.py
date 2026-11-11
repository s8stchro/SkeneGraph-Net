"""Three segmentation strategies.

Each strategy returns an ordered list of `Segment` objects.  A `Segment`
records WHO is on stage during that segment (a set of character ids), the
speeches it contains, and its word totals.

  * `segment_stage_directions(play)`     -- DraCor departure 1
        A new segment starts after every <move>.  Consecutive moves with no
        speeches between them form a single boundary, so we never emit empty
        intermediate segments.

  * `segment_middle_seq(play)`                 -- DraCor's analogue (one segment per scene)
        One segment per <milestone unit="middle-seq">.  A character is "in" the segment if they
        speak in it OR are physically on stage at any point during it (per
        the running stage state).  This is the inclusion rule that makes the
        three segmentations meaningfully different.

  * `segment_large_seq(play)`                 -- DraCor departure 1
        One segment per <milestone unit="large-seq">, with the same inclusion rule as middle-seq.

Mute characters are placed on / off stage exactly like speakers.  Whether
they appear in the network at all is decided downstream by the graph
builder; the base segmenter never drops them.

`fold_segments` derives a *model-specific* spine from the raw stage-
direction segmentation: it merges adjacent segments whose cast is identical
under the active network model (e.g. a boundary triggered only by a mute's
entrance is invisible to the speaking-cast models and is folded
away).  The static graph is invariant under the fold; only segment count
and the temporal series change.  Applied to the `sd` spine only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from parser import Div, Move, PlayData, Speech, apply_move


@dataclass
class Segment:
    id: int
    label: str
    characters_present: Set[str] = field(default_factory=set)
    speeches: List[Speech] = field(default_factory=list)
    # The cluster of <move> elements that opened this segment.  Used by the
    # dashboard's TEI view to find the segment's first source line when the
    # segment has no speeches (e.g. the empty pre-play marker).
    trigger_moves: List[Move] = field(default_factory=list)
    # Moves inside the segment that left the occupancy unchanged: a `crossing`
    # is a figure who appeared and was gone within one beat, so they join no
    # cast and form no edge.  Kept here so the stage traffic stays countable
    # where it belongs -- as a property of the segment, not of the graph.
    crossings: List[Move] = field(default_factory=list)
    # Words this segment credits to characters: every speech counted once per
    # id in its @who (`Speech.attributed_words`).  The same rule as the
    # play-level and per-character totals, so the segment table sums exactly
    # to the play total.
    word_count: int = 0
    large_seq_id: Optional[str] = None
    large_seq_type: Optional[str] = None
    middle_seq_id: Optional[str] = None
    is_initial: bool = False
    is_final: bool = False

    @property
    def num_characters(self) -> int:
        return len(self.characters_present)

    @property
    def num_crossings(self) -> int:
        """Figures who appeared and were gone inside this segment without
        ever joining its cast (see `crossings`)."""
        return len(self.crossings)

    @property
    def speakers(self) -> Set[str]:
        """Characters to whom this segment attributes an utterance.

        This is the per-segment "speaker" set that drives the mutes-out
        network model (edges form within this set instead of within
        characters_present).  Membership follows the <sp>, not the word
        count: an utterance whose text is *lost* still happened, so a
        textless <sp> credits its speaker.  Every such speech in the corpus
        is a chorus performance the manuscripts record without its words --
        the XOPOY interludes of Plutus and Ecclesiazusae, and the lacuna at
        Clouds 888a -- and treating them as silent made those segments
        register an empty stage.  word_count measures how much such a speaker
        says; it is not the test of whether they spoke.
        Computed on the fly so the speech records remain the single source
        of truth.
        """
        result: Set[str] = set()
        for sp in self.speeches:
            result |= sp.who
        return result

    @property
    def silent_present(self) -> Set[str]:
        """Characters present on stage but credited with no <sp> in this
        segment (the per-segment-mute subset of characters_present).  A
        speech whose text is not transmitted still credits its speaker, so a
        chorus performing an XOPOY interlude is not in this set."""
        return self.characters_present - self.speakers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _interleave(play: PlayData):
    """Yield all moves and speeches in document order."""
    items = []
    items.extend(("move", m) for m in play.moves)
    items.extend(("sp", s) for s in play.speeches)
    items.sort(key=lambda x: x[1].pos)
    return items


# ---------------------------------------------------------------------------
# Stage-direction segmentation
# ---------------------------------------------------------------------------

def segment_stage_directions(play: PlayData) -> List[Segment]:
    """Each <stage> (a cluster of one or more <move>s) opens one segment.

    A <stage> opens a new segment iff it contains a *structural* move
    (entrance / exit / onStage / merge / split); a <stage> holding only a
    state-change applies its perception effect without opening a segment.
    Moves are grouped by their containing <stage> at parse time
    (`Move.stage_pos`): the encoder says "these stage events form one beat"
    by wrapping them in a single <stage>, and "treat them separately" with
    adjacent <stage>s.

    Special case at the start: when the play opens with an empty
    ``<move type="onStage"/>`` marker -- the convention to denote "the stage
    is currently empty" -- that marker stands alone as an empty segment 0
    (the pre-play empty stage); the first entrance then opens segment 1.
    In the corpus the marker now occupies a <stage> of its own (the bracket
    convention); this special case additionally rescues legacy files where
    it still shares a <stage> with the first entrance.  Matches the
    Trilcke / Fischer 2017 convention.
    """
    segments: List[Segment] = []
    state: Set[str] = set()

    # Segment IDs are 1-indexed throughout the app (user-facing presentation
    # convention).  The Python array index in `segments` is 0-based as usual;
    # downstream code that needs to look a segment up by id uses .find()
    # rather than direct indexing.
    next_seg_id = 1
    pending_speeches: List[Speech] = []
    pending_trigger_moves: List[Move] = []
    pending_crossings: List[Move] = []
    pending_large_seq_id: Optional[str] = None
    pending_large_seq_type: Optional[str] = None
    pending_middle_seq_id: Optional[str] = None
    have_open_segment = False
    is_first_move = True

    def flush_segment() -> None:
        nonlocal next_seg_id, pending_speeches, pending_trigger_moves
        nonlocal pending_crossings
        nonlocal have_open_segment
        nonlocal pending_large_seq_id, pending_large_seq_type, pending_middle_seq_id
        if not have_open_segment:
            return
        # Speakers are in the segment they speak in, whatever the move stream
        # says -- the guard `_segment_by_seq` applies to the textual spines.
        # Without it a speaker whose entrance is missing or misspelt was an
        # isolate on this spine and connected on the other two (the parser
        # warns about such speeches; see `_validate_speakers_on_stage`).
        # Only the segment is widened: the running stage state is not, so a
        # missing entrance does not leave the speaker standing on afterwards.
        spoke: Set[str] = set()
        for sp in pending_speeches:
            spoke |= sp.who
        seg = Segment(
            id=next_seg_id,
            label=f"sd-{next_seg_id}",
            characters_present=set(state) | spoke,
            speeches=list(pending_speeches),
            trigger_moves=list(pending_trigger_moves),
            crossings=list(pending_crossings),
            word_count=sum(s.attributed_words for s in pending_speeches),
            large_seq_id=pending_large_seq_id,
            large_seq_type=pending_large_seq_type,
            middle_seq_id=pending_middle_seq_id,
        )
        segments.append(seg)
        next_seg_id += 1
        pending_speeches = []
        pending_trigger_moves = []
        pending_crossings = []
        have_open_segment = False

    # Annotation-schema rule 7: structural moves trigger a segment
    # boundary in the stage-direction segmenter.  These are the moves
    # that change *who* is on stage:
    #     entrance / exit / onStage  -- characters arrive / leave / are
    #                                   asserted present
    #     merge / split              -- the cast set changes by
    #                                   re-grouping (chorus unifies /
    #                                   divides)
    # state-change does NOT trigger; it applies its perception/visibility
    # effect (via `apply_move`'s no-op branch) without flushing, so
    # voice-only interjections (now `entrance subtype="voice-only"` +
    # later `state-change subtype="stage"`) stay in a single segment
    # with the surrounding exchange.
    STRUCTURAL = {"entrance", "exit", "onStage", "merge", "split"}

    # A <stage> opens a segment iff it contains a structural move.  Pre-compute
    # this per stage cluster, so a state-change that leads a structural stage
    # still opens the segment at the stage's first move.
    stage_struct: Dict[Optional[int], bool] = {}
    for m in play.moves:
        stage_struct[m.stage_pos] = stage_struct.get(m.stage_pos, False) or (m.type in STRUCTURAL)

    cur_stage: Optional[int] = -1   # sentinel: distinct from any real stage_pos

    for kind, item in _interleave(play):
        if kind == "move":
            # Pre-play empty-stage marker: emit a standalone empty segment 0.
            # Leave `cur_stage` at the sentinel so the move sharing this <stage>
            # (the first entrance) still opens segment 1.
            if is_first_move:
                is_first_move = False
                if item.type == "onStage" and not item.who:
                    empty_seg = Segment(
                        id=next_seg_id,
                        label=f"sd-{next_seg_id}-initial-empty",
                        characters_present=set(),
                        speeches=[],
                        trigger_moves=[item],
                        word_count=0,
                        large_seq_id=item.large_seq_id,
                        large_seq_type=item.large_seq_type,
                        middle_seq_id=item.middle_seq_id,
                        is_initial=True,
                    )
                    segments.append(empty_seg)
                    next_seg_id += 1
                    continue

            new_stage = item.stage_pos != cur_stage
            if new_stage:
                cur_stage = item.stage_pos
                if stage_struct.get(item.stage_pos, False):
                    # Terminal bracket (mirror of the seg-0 special case): the
                    # play-final bare ``<move type="onStage"/>`` confirms an
                    # already-empty stage.  It closes the trailing empty
                    # interval opened by the final exeunt instead of starting
                    # a new beat, so the play ends on ONE empty segment.  If
                    # the final exit was not exhaustive (someone is still on
                    # stage), it flushes normally and the clearing remains
                    # visible as its own segment.
                    terminal_bracket = (
                        play.moves and item is play.moves[-1]
                        and item.type == "onStage" and not item.who
                        and not state and have_open_segment
                    )
                    if not terminal_bracket:
                        # A new structural <stage> = a new beat: close the open
                        # segment (with its speeches) and anchor a new one here.
                        flush_segment()
                        have_open_segment = True
                        pending_large_seq_id = item.large_seq_id
                        pending_large_seq_type = item.large_seq_type
                        pending_middle_seq_id = item.middle_seq_id
            apply_move(state, item)
            if have_open_segment:
                pending_trigger_moves.append(item)
                if item.type == "crossing":
                    pending_crossings.append(item)
        else:  # speech
            if not have_open_segment:
                # A speech before any structural stage opens a segment.
                have_open_segment = True
                pending_large_seq_id = item.large_seq_id
                pending_large_seq_type = item.large_seq_type
                pending_middle_seq_id = item.middle_seq_id
            pending_speeches.append(item)

    flush_segment()

    # Mark initial / final.  If we already emitted an explicit empty seg
    # (the initial empty-stage marker) above, its `is_initial` and label
    # were set there -- don't overwrite.
    if segments:
        if not segments[0].is_initial:
            segments[0].is_initial = True
            segments[0].label = f"sd-{segments[0].id}-initial"
        # Mark the terminal segment as `final` only if it is genuinely a
        # separate empty segment (not the same as the initial one).
        if len(segments) > 1 and not segments[-1].characters_present:
            segments[-1].is_final = True
            segments[-1].label = f"sd-{segments[-1].id}-final"

    return segments


# ---------------------------------------------------------------------------
# Div-based segmentation (large_seq and middle_seq share the same inclusion logic)
# ---------------------------------------------------------------------------

def _segment_by_seq(play: PlayData, level: int) -> List[Segment]:
    """One segment per div at the given level.  A character is in a segment if
    they speak in it OR are physically on stage at any point during it.
    """
    divs = play.large_seqs if level == 2 else play.middle_seqs
    if not divs:
        return []

    # Bucket by the div's document-position, which is unique even when two
    # divs share the same @n / @type (Lysistrata's large_seqs all use n="textpart").
    if level == 2:
        def key_of_move(m: Move):     return m.large_seq_pos
        def key_of_speech(s: Speech):  return s.large_seq_pos
        def key_of_div(d: Div):        return d.pos
    else:
        def key_of_move(m: Move):     return m.middle_seq_pos
        def key_of_speech(s: Speech):  return s.middle_seq_pos
        def key_of_div(d: Div):        return d.pos

    # Sweep moves once over the play to establish "who was on stage in div X
    # at any moment".  We walk in document order, applying moves to a running
    # state.  At each speech / move we add the current state to the
    # appropriate div bucket.
    presence: Dict[Optional[int], Set[str]] = {}
    speeches_in: Dict[Optional[int], List[Speech]] = {}
    crossings_in: Dict[Optional[int], List[Move]] = {}
    state: Set[str] = set()

    for kind, item in _interleave(play):
        if kind == "move":
            # State BEFORE the move: those characters were present until now.
            k = key_of_move(item)
            presence.setdefault(k, set()).update(state)
            apply_move(state, item)
            # State AFTER the move: those who entered are now also present.
            presence.setdefault(k, set()).update(state)
            # A crossing leaves both states identical, so whoever crossed is
            # in neither; record the event against the div instead.
            if item.type == "crossing":
                crossings_in.setdefault(k, []).append(item)
        else:
            k = key_of_speech(item)
            presence.setdefault(k, set()).update(state)
            presence.setdefault(k, set()).update(item.who)
            speeches_in.setdefault(k, []).append(item)

    segments: List[Segment] = []
    for idx, d in enumerate(divs):
        k = key_of_div(d)
        speeches = speeches_in.get(k, [])
        present = set(presence.get(k, set()))
        # Always include speakers whose speeches we counted -- guards against
        # state-tracking gaps where a character speaks without an explicit move.
        for sp in speeches:
            present.update(sp.who)
        seg = Segment(
            id=idx + 1,                              # 1-indexed segment ids
            label=f"{'large-seq' if level == 2 else 'middle-seq'}-{idx + 1}-{d.label}",
            characters_present=present,
            speeches=speeches,
            crossings=crossings_in.get(k, []),
            word_count=sum(s.attributed_words for s in speeches),
            large_seq_id=(d.xml_id if level == 2 else d.parent_large_seq_id),
            large_seq_type=(d.type if level == 2 else d.parent_large_seq_type),
            middle_seq_id=(d.xml_id if level == 3 else None),
        )
        segments.append(seg)

    if segments:
        segments[0].is_initial = True
        segments[-1].is_final = True
    return segments


def segment_large_seq(play: PlayData) -> List[Segment]:
    return _segment_by_seq(play, 2)


def segment_middle_seq(play: PlayData) -> List[Segment]:
    return _segment_by_seq(play, 3)


# ---------------------------------------------------------------------------
# Model-specific spine: fold boundaries a network model cannot see
# ---------------------------------------------------------------------------

def _relabel(new_id: int, is_initial: bool, is_final: bool, empty: bool) -> str:
    if is_initial:
        return f"sd-{new_id}-initial-empty" if empty else f"sd-{new_id}-initial"
    if is_final and empty:
        return f"sd-{new_id}-final"
    return f"sd-{new_id}"


def _merge_run(members: List[Segment], new_id: int) -> Segment:
    """Collapse a run of adjacent segments into one (also handles len==1).

    `characters_present` is the union over the run; speeches, trigger
    moves and crossings are concatenated in order; word counts are summed.
    The div context is taken from the first member (the run's opening div).
    `is_initial` / `is_final` carry over from the run's endpoints so the
    empty pre-play marker and terminal empty stage survive the fold.
    """
    first = members[0]
    present: Set[str] = set()
    for s in members:
        present |= s.characters_present
    speeches = [sp for s in members for sp in s.speeches]
    trig = [m for s in members for m in s.trigger_moves]
    is_init = members[0].is_initial
    is_fin = members[-1].is_final
    return Segment(
        id=new_id,
        label=_relabel(new_id, is_init, is_fin, not present),
        characters_present=present,
        speeches=speeches,
        trigger_moves=trig,
        # Copied like every other per-segment record: leaving it out set
        # num_crossings to 0 on every folded spine, so the speaking models'
        # segment tables and segments.csv lost the stage traffic Methods §9
        # promises stays countable.
        crossings=[c for s in members for c in s.crossings],
        word_count=sum(s.word_count for s in members),   # already attributed
        large_seq_id=first.large_seq_id,
        large_seq_type=first.large_seq_type,
        middle_seq_id=first.middle_seq_id,
        is_initial=is_init,
        is_final=is_fin,
    )


def fold_segments(segments: List[Segment], cast_of) -> List[Segment]:
    """Merge maximal runs of adjacent segments the active model cannot tell apart.

    `cast_of(seg) -> Set[str]` returns the set of characters that defines a
    segment's contribution to the active network model (stage presence, or
    the play-level speaking cast).  Two adjacent segments whose `cast_of`
    sets are equal describe the *same* constellation under that model, so
    the boundary between them is invisible to it -- e.g. a mute's entrance
    under the speaking model, where the mute is not a node.  Such
    boundaries are folded away, giving each model its own spine.

    The static graph is invariant: a merged segment re-emits the identical
    clique, so order, size, density, average degree, clustering and
    diameter are unchanged, and only the segment count and the per-segment
    series (DCR, change rates, segment indices, beat charts) move.  The
    segment-level speaking model folds further, and without that guarantee
    (see `fold_for_model`).  Segment ids are renumbered 1..N over the folded
    spine; `is_initial` / `is_final` and the empty pre-play marker are
    preserved.

    Intended for the stage-direction spine only -- large-seq / middle-seq are textual
    divisions, not cast-triggered boundaries, so they are left untouched
    by the caller.
    """
    if not segments:
        return segments
    return _renumber(_runs(segments, cast_of))


def _runs(segments: List[Segment], cast_of) -> List[List[Segment]]:
    """The maximal runs of equal `cast_of` that `fold_segments` merges."""
    runs: List[List[Segment]] = [[segments[0]]]
    for seg in segments[1:]:
        if cast_of(seg) == cast_of(runs[-1][-1]):
            runs[-1].append(seg)
        else:
            runs.append([seg])
    return runs


def _renumber(runs: List[List[Segment]]) -> List[Segment]:
    return [_merge_run(members, i) for i, members in enumerate(runs, start=1)]


def fold_for_model(segments: List[Segment], kept: Set[str],
                   segment_cast: str) -> List[Segment]:
    """The stage-direction spine as one network model sees it.

    Folds away the boundaries that model cannot see.  `kept` is its node
    set; `segment_cast` is "stage" or "speaking".  Callers apply this to the
    sd spine of the mutes-out models only -- the stage model keeps the
    faithful annotated spine, and the textual spines are not cast-triggered.

    The two models disagree about what makes a boundary visible:

    * "stage" (p-speaking) -- presence *is* the model's content, so any
      change to the kept cast is a real boundary.  Only moves by non-nodes
      (play-level mutes) fold away.  Edge-preserving.
    * "speaking" (s-speaking) -- presence is *not* the model's content.  A
      boundary matters only if a character entering or leaving at it
      actually speaks on one side of it, so a figure who crosses it in
      silence must not separate two characters speaking on either side of
      them -- whether that figure speaks elsewhere in the play is beside
      the point.  This can merge segments of differing cast and so add an
      edge the unfolded spine lacks; that is intended, the removed boundary
      being one the model should never have seen.  Who crosses is read off
      the stage as it stands on either side of the boundary; who speaks, off
      the whole of the merged segment, since that is what the model will be
      given.

      "The whole" is meant strictly: every boundary inside a merged segment
      must pass against all of its speakers, not only against those gathered
      by the time the fold reached it.  Checked only at the moment of
      merging, a figure who entered in silence and spoke two beats later had
      the boundary they entered at folded away -- Myrrhine's entrance in
      Lysistrata (line 942 of the example) was the case.  A boundary nobody
      in the node set crosses can never be seen, so those fold first, as
      under the play-level model; the rest fold left to right wherever the
      merged segment still satisfies the rule.

    Defined here, once, because the app and the test baseline must fold
    identically; they drifted apart when each carried its own copy.
    """
    def cast_of(seg):
        return seg.characters_present & kept

    if segment_cast != "speaking" or not segments:
        return fold_segments(segments, cast_of)

    def invisible(a, b, speaking):
        # Crossers are read off the adjacent pair -- not the union over a
        # run, where a character who left earlier is still "present", so
        # their return would never register and the boundary they re-enter
        # at would fold away even where they speak straight after it.
        prev, here = cast_of(a), cast_of(b)
        # An empty stage is a real caesura: never fold it into an occupied
        # segment, whether or not anyone speaks across the boundary.
        if bool(prev) != bool(here):
            return False
        return not ((prev ^ here) & speaking)

    runs: List[List[Segment]] = []
    for block in _runs(segments, cast_of):
        if runs:
            merged = runs[-1] + block
            speaking = set().union(*(s.speakers for s in merged))
            if all(invisible(a, b, speaking)
                   for a, b in zip(merged, merged[1:])):
                runs[-1] = merged
                continue
        runs.append(block)
    return _renumber(runs)


SEGMENTERS = {
    "sd":         segment_stage_directions,
    "large-seq":  segment_large_seq,
    "middle-seq": segment_middle_seq,
}


def active_span(segments: List[Segment]) -> List[Segment]:
    """The play's dramaturgically active stretch: bookend markers dropped.

    Leading and trailing segments with nobody on stage are the segmenter's
    housekeeping -- the sd spine's empty pre-play marker, the terminal empty
    stage after a full exeunt -- and including them in a denominator squeezes
    the real content into less than the whole span.

    Judged on `characters_present`, not on speech, so a bookend holding one
    silent figure is kept: that is a beat of the play.

    Defined here because two callers need the same span and their agreement
    is asserted in prose: the per-character temporal Gini (§5) and the corpus
    chorus beat chart (§11) are read against each other, so a trim that
    drifted between them would make the two charts disagree silently.
    """
    lo, hi = 0, len(segments)
    while lo < hi and not segments[lo].characters_present:
        lo += 1
    while hi > lo and not segments[hi - 1].characters_present:
        hi -= 1
    return segments[lo:hi]


__all__ = [
    "Segment",
    "segment_stage_directions",
    "segment_large_seq",
    "segment_middle_seq",
    "fold_segments",
    "fold_for_model",
    "active_span",
    "SEGMENTERS",
]
