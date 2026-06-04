"""Three segmentation strategies.

Each strategy returns an ordered list of `Segment` objects.  A `Segment`
records WHO is on stage during that segment (a set of character ids), the
speeches it contains, and its verse / word totals.

  * `segment_stage_directions(play)`     -- DraCor departure 1
        A new segment starts after every <move>.  Consecutive moves with no
        speeches between them form a single boundary, so we never emit empty
        intermediate segments.

  * `segment_div3(play)`                 -- DraCor's analogue (one segment per scene)
        One segment per <div3>.  A character is "in" the segment if they
        speak in it OR are physically on stage at any point during it (per
        the running stage state).  This is the inclusion rule that makes the
        three segmentations meaningfully different.

  * `segment_div2(play)`                 -- DraCor departure 1
        One segment per <div2>, with the same inclusion rule as div3.

Mute characters are placed on / off stage exactly like speakers.  Whether
they appear in the network at all is decided downstream by the graph
builder; the base segmenter never drops them.

`fold_segments` derives a *model-specific* spine from the raw stage-
direction segmentation: it merges adjacent segments whose cast is identical
under the active network model (e.g. a boundary triggered only by a mute's
entrance is invisible to the dialogic / co-speech models and is folded
away).  The static graph is invariant under the fold; only segment count
and the temporal series change.  Applied to the `sd` spine only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from parser import Div, Move, PlayData, Speech


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
    verse_count: int = 0
    word_count: int = 0
    div2_n: Optional[str] = None
    div2_type: Optional[str] = None
    div3_id: Optional[str] = None
    div3_n: Optional[str] = None
    is_initial: bool = False
    is_final: bool = False

    @property
    def num_characters(self) -> int:
        return len(self.characters_present)

    @property
    def speakers(self) -> Set[str]:
        """Characters with >=1 non-empty <l> attributed in this segment.

        This is the strict per-segment "speaker" set that drives the
        mutes-out network model (edges form within this set instead of
        within characters_present).  An empty <sp><l/></sp> placeholder
        does NOT count.  Computed on the fly so the speech records remain
        the single source of truth.
        """
        result: Set[str] = set()
        for sp in self.speeches:
            if sp.verse_count > 0:
                result |= sp.who
        return result

    @property
    def silent_present(self) -> Set[str]:
        """Characters present on stage but with no non-empty <l> in this
        segment (the per-segment-mute subset of characters_present)."""
        return self.characters_present - self.speakers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_move(state: Set[str], move: Move) -> None:
    """Update stage state with a move (mutates `state`)."""
    if move.type == "entrance":
        state.update(move.who)
    elif move.type == "exit":
        state.difference_update(move.who)
    elif move.type == "split":
        # The character splits into the @corresp ones; remove origin, add parts.
        state.difference_update(move.who)
        state.update(move.corresp)
    elif move.type == "merge":
        # The @who parts merge into @corresp; remove parts, add unified.
        state.difference_update(move.who)
        state.update(move.corresp)
    elif move.type == "onStage":
        # `onStage` with @who means "these characters are currently on stage".
        # Without @who it marks an empty stage (start/end of play).
        if move.who:
            state.update(move.who)
        else:
            state.clear()
    elif move.type == "state-change":
        # Annotation-only marker: the @subtype carries perception / visibility
        # / vitality state info for the directed-perception app.  The stage
        # state SET is unchanged -- the character was already on stage and
        # remains so; only their state-on-stage shifts.  The undirected
        # SkeneGraph-Net does not read the subtype.
        pass
    # Unknown move types are silently ignored.


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
    """Each move creates a new segment.  Consecutive moves cluster into one boundary.

    Special case at the start: when the play opens with an empty
    ``<move type="onStage"/>`` marker -- the convention in our annotated
    corpus to denote "the stage is currently empty" -- that marker stands
    alone as an empty segment 0 (the pre-play empty stage), and the first
    entrance opens segment 1.  This matches the Trilcke / Fischer 2017
    convention and the symmetric treatment of the terminal empty-stage
    marker.  Without this, the empty onStage would cluster with the
    following entrance and segment 0 would incorrectly carry the initial
    cast (e.g. *Knights*'s two slaves entering together).
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
    pending_div2_n: Optional[str] = None
    pending_div2_type: Optional[str] = None
    pending_div3_id: Optional[str] = None
    pending_div3_n: Optional[str] = None
    have_open_segment = False
    is_first_move = True

    def flush_segment() -> None:
        nonlocal next_seg_id, pending_speeches, pending_trigger_moves
        nonlocal have_open_segment
        nonlocal pending_div2_n, pending_div2_type, pending_div3_id, pending_div3_n
        if not have_open_segment:
            return
        seg = Segment(
            id=next_seg_id,
            label=f"sd-{next_seg_id}",
            characters_present=set(state),
            speeches=list(pending_speeches),
            trigger_moves=list(pending_trigger_moves),
            verse_count=sum(s.verse_count for s in pending_speeches),
            word_count=sum(s.word_count for s in pending_speeches),
            div2_n=pending_div2_n,
            div2_type=pending_div2_type,
            div3_id=pending_div3_id,
            div3_n=pending_div3_n,
        )
        segments.append(seg)
        next_seg_id += 1
        pending_speeches = []
        pending_trigger_moves = []
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
    # effect (via `_apply_move`'s no-op branch) without flushing, so
    # voice-only interjections (now `entrance subtype="voice-only"` +
    # later `state-change subtype="stage"`) stay in a single segment
    # with the surrounding dialogic exchange.
    STRUCTURAL = {"entrance", "exit", "onStage", "merge", "split"}

    for kind, item in _interleave(play):
        if kind == "move":
            # Pre-play empty-stage marker: emit a standalone empty
            # segment 0 and *don't* cluster it with the next move.
            if is_first_move:
                is_first_move = False
                if item.type == "onStage" and not item.who:
                    empty_seg = Segment(
                        id=next_seg_id,
                        label=f"sd-{next_seg_id}-initial-empty",
                        characters_present=set(),
                        speeches=[],
                        trigger_moves=[item],
                        verse_count=0,
                        word_count=0,
                        div2_n=item.div2_n,
                        div2_type=item.div2_type,
                        div3_id=item.div3_id,
                        div3_n=item.div3_n,
                        is_initial=True,
                    )
                    segments.append(empty_seg)
                    next_seg_id += 1
                    continue   # don't open a pending segment for this move

            if item.type in STRUCTURAL:
                # Structural move: flush the open segment (if any has content)
                # and open a new one anchored on this move.
                if have_open_segment and pending_speeches:
                    flush_segment()
                pending_trigger_moves.append(item)
                _apply_move(state, item)
                have_open_segment = True
                # Track the div context of the move that opened this segment.
                pending_div2_n = item.div2_n
                pending_div2_type = item.div2_type
                pending_div3_id = item.div3_id
                pending_div3_n = item.div3_n
            else:
                # Non-structural move (state-change / merge / split):
                # apply the state effect but do not flush.  If we have not
                # yet opened a segment, do not open one for this either --
                # an isolated state-change before any entrance is an
                # annotation oddity but should not produce an empty seg.
                _apply_move(state, item)
                if have_open_segment:
                    pending_trigger_moves.append(item)
        else:  # speech
            if not have_open_segment:
                # A speech before any move (rare but possible) -- start a segment.
                have_open_segment = True
                pending_div2_n = item.div2_n
                pending_div2_type = item.div2_type
                pending_div3_id = item.div3_id
                pending_div3_n = item.div3_n
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
# Div-based segmentation (div2 and div3 share the same inclusion logic)
# ---------------------------------------------------------------------------

def _segment_by_divs(play: PlayData, level: int) -> List[Segment]:
    """One segment per div at the given level.  A character is in a segment if
    they speak in it OR are physically on stage at any point during it.
    """
    divs = play.div2s if level == 2 else play.div3s
    if not divs:
        return []

    # Bucket by the div's document-position, which is unique even when two
    # divs share the same @n / @type (Lysistrata's div2s all use n="textpart").
    if level == 2:
        def key_of_move(m: Move):     return m.div2_pos
        def key_of_speech(s: Speech):  return s.div2_pos
        def key_of_div(d: Div):        return d.pos
    else:
        def key_of_move(m: Move):     return m.div3_pos
        def key_of_speech(s: Speech):  return s.div3_pos
        def key_of_div(d: Div):        return d.pos

    # Sweep moves once over the play to establish "who was on stage in div X
    # at any moment".  We walk in document order, applying moves to a running
    # state.  At each speech / move we add the current state to the
    # appropriate div bucket.
    presence: Dict[Optional[int], Set[str]] = {}
    speeches_in: Dict[Optional[int], List[Speech]] = {}
    state: Set[str] = set()

    for kind, item in _interleave(play):
        if kind == "move":
            # State BEFORE the move: those characters were present until now.
            k = key_of_move(item)
            presence.setdefault(k, set()).update(state)
            _apply_move(state, item)
            # State AFTER the move: those who entered are now also present.
            presence.setdefault(k, set()).update(state)
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
            label=f"div{level}-{idx + 1}-{d.label}",
            characters_present=present,
            speeches=speeches,
            verse_count=sum(s.verse_count for s in speeches),
            word_count=sum(s.word_count for s in speeches),
            div2_n=(d.n if level == 2 else d.parent_div2_n),
            div2_type=(d.type if level == 2 else d.parent_div2_type),
            div3_id=(d.xml_id if level == 3 else None),
            div3_n=(d.n if level == 3 else None),
        )
        segments.append(seg)

    if segments:
        segments[0].is_initial = True
        segments[-1].is_final = True
    return segments


def segment_div2(play: PlayData) -> List[Segment]:
    return _segment_by_divs(play, 2)


def segment_div3(play: PlayData) -> List[Segment]:
    return _segment_by_divs(play, 3)


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

    `characters_present` is the union over the run; speeches and trigger
    moves are concatenated in order; verse / word counts are summed.  The
    div context is taken from the first member (the run's opening div).
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
        verse_count=sum(s.verse_count for s in members),
        word_count=sum(s.word_count for s in members),
        div2_n=first.div2_n,
        div2_type=first.div2_type,
        div3_id=first.div3_id,
        div3_n=first.div3_n,
        is_initial=is_init,
        is_final=is_fin,
    )


def fold_segments(segments: List[Segment], cast_of) -> List[Segment]:
    """Merge maximal runs of adjacent segments with identical model-cast.

    `cast_of(seg) -> Set[str]` returns the set of characters that defines a
    segment's contribution to the active network model (stage presence,
    play-level dialogic cast, or per-segment speakers).  Two adjacent
    segments whose `cast_of` sets are equal describe the *same*
    constellation under that model, so the boundary between them is
    invisible to it -- e.g. a mute's entrance under the dialogic model,
    where the mute is not a node.  Such boundaries are folded away, giving
    each model its own segmentation spine.

    The static graph is invariant under this fold: a merged segment
    re-emits the identical co-presence / co-speech clique, so the union
    graph (and hence order, size, density, average degree, clustering,
    diameter) is unchanged.  Only the segment count and the temporal /
    per-segment series (DCR, change rates, segment indices, beat charts)
    move.  Segment ids are renumbered 1..N over the folded spine;
    `is_initial` / `is_final` and the empty pre-play marker are preserved.

    Intended for the stage-direction spine only -- div2 / div3 are textual
    divisions, not cast-triggered boundaries, so they are left untouched
    by the caller.
    """
    if not segments:
        return segments
    runs: List[List[Segment]] = [[segments[0]]]
    prev = cast_of(segments[0])
    for seg in segments[1:]:
        cur = cast_of(seg)
        if cur == prev:
            runs[-1].append(seg)
        else:
            runs.append([seg])
            prev = cur
    return [_merge_run(members, i) for i, members in enumerate(runs, start=1)]


SEGMENTERS = {
    "sd":   segment_stage_directions,
    "div2": segment_div2,
    "div3": segment_div3,
}


__all__ = [
    "Segment",
    "segment_stage_directions",
    "segment_div2",
    "segment_div3",
    "fold_segments",
    "SEGMENTERS",
]
