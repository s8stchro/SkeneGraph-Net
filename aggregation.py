"""Aggregation by partOf relations.

When the user enables the aggregator, characters declared as
`<relation name="partOf" active="#X" passive="#Y">` are rewritten to
their group id `Y` throughout the play data.  After rewriting, the
segmenter, graph builder, and metric pipeline run unchanged on the
aggregated character set.

Example (Lysistrata):
    chorosGeronton, chorosGynaikon  partOf  choros
    ->  in speeches' @who and @toWhom, in moves' @who and @corresp,
        both member ids are replaced by `choros`; both members are removed from
        the character list; `choros` (already a character in the
        cast) absorbs their chorus / speaker flags; muteness is
        re-derived behaviourally on the rewritten data.

Edge-weight merge rule
----------------------
None is needed explicitly.  The graph builder counts a segment once per
pair, so after the rewrite a segment holding C and any part of G yields
one G-C segment: the merged weight is the union of the members' segments
and the group's own, not the sum of their weights.  (Which is what a merge
means -- the note this replaces claimed the weights summed.)

Split/merge moves under aggregation
-----------------------------------
A split move (`@who=choros`, `@corresp=chorosGeronton chorosGynaikon`)
becomes, post-rewrite, `@who={choros}` and `@corresp={choros}` -- a
no-op for `apply_move`.  This is the correct semantics: under
aggregation the chorus never visibly splits.

Why moves need more than a rewrite
----------------------------------
Replacing ids is right for what a move *adds* and wrong for what it
*removes*.  The stage state is a set, so adding a group twice is the same
as adding it once -- but one part leaving would take the whole group off
stage with it, though its other parts are still standing there.  A
group's removals are therefore read off the members' own occupancy: the
group leaves when its last present member does.  See `_rewrite_moves`.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Dict, List, Optional, Set

from parser import Character, Move, PlayData, Relation, apply_move


log = logging.getLogger("SkeneGraph-Net.aggregation")


def build_partof_map(relations: List[Relation],
                     groups: Optional[Set[str]] = None) -> Dict[str, str]:
    """Map each member id to the group it aggregates into under partOf.

    With no `groups`, that is the top-level ancestor: if A partOf B and B
    partOf C, the map gives {A: C, B: C}.

    With `groups`, it is the highest *selected* ancestor, and a member with
    no selected ancestor is left out.  The dashboard offers a checkbox per
    declared group, intermediate ones included, and selecting B must mean
    what it says -- collapse A into B and leave C standing.  Resolving to the
    top first and filtering afterwards made that selection a silent no-op:
    no variant was generated for it, and the dashboard fell through to a
    block built under a different network model.

    Cycles (which shouldn't exist in well-formed data) are broken by a
    visited-set guard.
    """
    immediate: Dict[str, str] = {}
    for rel in relations:
        if rel.name != "partOf":
            continue
        immediate[rel.active] = rel.passive

    out: Dict[str, str] = {}
    for member in immediate:
        ancestors: List[str] = []
        seen: Set[str] = {member}
        cur = immediate[member]
        while True:
            ancestors.append(cur)
            if cur not in immediate or cur in seen:
                break
            seen.add(cur)
            cur = immediate[cur]
        if groups is None:
            out[member] = ancestors[-1]
        else:
            selected = [a for a in ancestors if a in groups]
            if selected:
                out[member] = selected[-1]
    return out


def _rewrite_moves(raw: List[Move], out: List[Move], project) -> None:
    """Rewrite the move stream so a group's presence follows its members'.

    Additions keep the plain projection: putting a group on stage twice is
    the same as putting it there once, and `onStage` in particular must keep
    a non-empty `@who`, an empty one being the marker for an empty stage.

    Removals cannot be projected that way.  Two parts of a chorus enter, one
    leaves, the other stays: rewriting that exit to the group id takes the
    whole chorus off stage while half of it is still there, and every later
    segment loses the group, its edges and its heatmap row.  What leaves is
    therefore read off the members' own occupancy -- replay the raw moves,
    and remove exactly those group ids that have no present member left.

    `raw` and `out` are the same moves before and after the id rewrite, in
    the same order; the replay walks them in document order, as the
    segmenters do.
    """
    state: Set[str] = set()
    for i in sorted(range(len(raw)), key=lambda j: raw[j].pos):
        src, dst = raw[i], out[i]
        before = project(state)
        apply_move(state, src)
        after = project(state)
        dst.corresp = project(src.corresp)
        if src.type in ("exit", "split", "merge"):
            dst.who = before - after
        else:
            dst.who = project(src.who)


def aggregatable_groups(play: PlayData) -> List[str]:
    """The groups a caller may aggregate into, in one place.

    Every declared `partOf` parent that is a character in its own right --
    intermediate parents included, each of which `aggregate_play` honours as
    a target.  The writer enumerates its variants from this list and the
    dashboard draws its checkboxes from it, so a box cannot name a
    combination that was never generated.
    """
    return sorted({r.passive for r in play.relations
                   if r.name == "partOf" and r.passive in play.characters})


def aggregate_play(play: PlayData, groups: Optional[Set[str]] = None,
                   members: Optional[Set[str]] = None) -> PlayData:
    """Return a copy of `play` with partOf-members rewritten to their top ancestor.

    When `groups` is None (default), every partOf relation in the play is
    aggregated.  When `groups` is a set of passive (group) ids, only members
    whose top ancestor is in that set are rewritten -- the rest stay as
    individuals.  This is what powers the per-group toggle in the dashboard.
    `members` narrows the same way from the other side, rewriting only the
    listed member ids; `absorb_silent_parts` uses it to fold away the silent
    parts of a speaking figure without touching parts that speak.

    Returns `play` unchanged (same object identity) when no rewriting
    would occur, so the caller can short-circuit on `agg is play`.
    """
    pmap = build_partof_map(play.relations, groups=groups)
    if not pmap:
        return play
    if members is not None:
        pmap = {m: g for m, g in pmap.items() if m in members}
    if not pmap:
        return play

    def rewrite(s: Set[str]) -> Set[str]:
        return {pmap.get(x, x) for x in s}

    out = deepcopy(play)

    for sp in out.speeches:
        sp.who = rewrite(sp.who)
        sp.addressees = rewrite(sp.addressees)
    _rewrite_moves(play.moves, out.moves, rewrite)

    members = set(pmap.keys())
    groups = set(pmap.values())

    # Drop absorbed members from the character set; keep everyone else.
    new_chars: Dict[str, Character] = {
        cid: ch for cid, ch in out.characters.items() if cid not in members
    }
    # Defensive: fabricate any group that wasn't declared in <listPerson>.
    # The parser currently drops such relations, so this branch should not
    # fire for the present corpus; the warning makes any future occurrence
    # visible.
    for g in groups:
        if g not in new_chars:
            new_chars[g] = Character(id=g, is_collective=True, is_chorus=True)
            log.warning("aggregation: fabricated group #%s (not in <listPerson>)", g)

    # The group is collective by construction; inherit chorus / speaker
    # flags from any member that had them.  sex / nature stay at the
    # group's declared values (a heterogeneous group's id-level annotation
    # is more authoritative than majority-vote across the parts).
    for g in groups:
        gc = new_chars[g]
        gc.is_collective = True
        member_ids = [m for m in members if pmap[m] == g and m in play.characters]
        if any(play.characters[m].is_chorus for m in member_ids):
            gc.is_chorus = True
        if any(play.characters[m].is_speaker_explicit for m in member_ids):
            gc.is_speaker_explicit = True

    out.characters = new_chars

    # Re-derive behavioural mute classification on the aggregated data.
    # A group is mute iff no <sp> is attributed to any of its members; since
    # only @who has been rewritten, the rule delivers the right answer for
    # both groups and untouched characters.  Same test as
    # `parser._classify_mutes`: the <sp>, not the word count, so a group whose
    # only utterance is a textless one still counts as speaking.
    spoke: Set[str] = set()
    for sp in out.speeches:
        spoke |= sp.who
    for cid, ch in out.characters.items():
        ch.is_mute = cid not in spoke

    return out


def absorb_silent_parts(play: PlayData) -> PlayData:
    """Fold a speaking figure's silent parts into the figure itself.

    A partOf member that never carries an <sp> is not a mute *character*:
    it is a phase of the figure it belongs to.  Ecclesiazusae's chorus
    arrives in three silent parts -- merosChorouA, B, C enter
    separately during the prologue (vv. 30, 43, 54) and are merged into
    `choros` at v. 285, where the parodos begins -- and none of them sings,
    because the chorus does not sing until it is whole.  Judged token by
    token they look like play-level mutes; judged as a figure they are the
    chorus, which speaks at length.

    Dropping them from the speaking cast on play level therefore erases the
    chorus from the prologue, where it stands on stage from v. 30.  Attributing
    their presence to the group keeps that model's node set exactly
    "characters who speak", while letting the chorus be present wherever any
    part of it is.  It also restores the aggregation toggle's monotonicity:
    without this the toggle *added* edges for Ecclesiazusae (32 -> 35),
    because collapsing the parts handed their presence to a node that had
    none of it.

    Members that speak in their own right -- the semichoruses of Acharnians,
    Peace and Lysistrata -- are left alone; collapsing those is what the
    aggregation toggle is for.  A member whose group is also mute is left
    alone too: there is no speaking figure to attribute its presence to.

    The rule is a special provision for a singular case and it is not free:
    it puts `choros` on stage from v. 30, part by part, before those parts
    have merged into the chorus they are going to become.  The encoding keeps
    the two facts apart -- `partOf` says these bodies belong to the chorus,
    `<move type="merge">` says when they become one body -- and this rule
    reads the first.  The stricter reading is not lost but relocated: under
    the segment-level model the chorus enters only where it speaks, at v. 285.
    What is not available is a model in which the parts are nobody while the
    aggregation toggle turns them into the chorus; the toggle asserts the
    `partOf` identity, so the unaggregated view must assert it too.

    Returns `play` unchanged when nothing qualifies.
    """
    pmap = build_partof_map(play.relations)
    silent = {
        m for m, g in pmap.items()
        if m in play.characters and play.characters[m].is_mute
        and g in play.characters and not play.characters[g].is_mute
    }
    if not silent:
        return play
    return aggregate_play(play, members=silent)


__all__ = ["build_partof_map", "aggregatable_groups", "aggregate_play",
           "absorb_silent_parts"]
