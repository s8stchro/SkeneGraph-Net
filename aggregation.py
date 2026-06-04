"""Aggregation by partOf relations.

When the user enables the aggregator, characters declared as
`<relation name="partOf" active="#X" passive="#Y">` are rewritten to
their group id `Y` throughout the play data.  After rewriting, the
segmenter, graph builder, and metric pipeline run unchanged on the
aggregated character set.

Example (Lysistrata):
    chorosAndron, chorosGynaikon  partOf  choros
    ->  in speeches' @who, in moves' @who and @corresp, both member
        ids are replaced by `choros`; both members are removed from
        the character list; `choros` (already a character in the
        cast) absorbs their chorus / speaker flags; muteness is
        re-derived behaviourally on the rewritten data.

Edge-weight merge rule
----------------------
None is needed explicitly.  The graph builder already counts segments
in which two characters are co-present.  After aggregation, member ids
collapse to the group, so segments that previously contributed
A-C and B-C edges (with A,B both partOf G) contribute a single G-C
edge per segment.  Multiplicity sums by construction.

Split/merge moves under aggregation
-----------------------------------
A split move (`@who=choros`, `@corresp=chorosAndron chorosGynaikon`)
becomes, post-rewrite, `@who={choros}` and `@corresp={choros}` -- a
no-op for `_apply_move`.  This is the correct semantics: under
aggregation the chorus never visibly splits.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Dict, List, Optional, Set

from parser import Character, PlayData, Relation


log = logging.getLogger("SkeneGraph-Net.aggregation")


def build_partof_map(relations: List[Relation]) -> Dict[str, str]:
    """Map each member id to its top-level ancestor under partOf (transitive).

    If A partOf B and B partOf C, the map gives {A: C, B: C}.
    Cycles (which shouldn't exist in well-formed data) are broken by a
    visited-set guard; the offending entry maps to itself.
    """
    immediate: Dict[str, str] = {}
    for rel in relations:
        if rel.name != "partOf":
            continue
        immediate[rel.active] = rel.passive

    top: Dict[str, str] = {}
    for member in immediate:
        seen: Set[str] = {member}
        cur = immediate[member]
        while cur in immediate and cur not in seen:
            seen.add(cur)
            cur = immediate[cur]
        top[member] = cur
    return top


def aggregate_play(play: PlayData, groups: Optional[Set[str]] = None) -> PlayData:
    """Return a copy of `play` with partOf-members rewritten to their top ancestor.

    When `groups` is None (default), every partOf relation in the play is
    aggregated.  When `groups` is a set of passive (group) ids, only members
    whose top ancestor is in that set are rewritten -- the rest stay as
    individuals.  This is what powers the per-group toggle in the dashboard.

    Returns `play` unchanged (same object identity) when no rewriting
    would occur, so the caller can short-circuit on `agg is play`.
    """
    pmap = build_partof_map(play.relations)
    if not pmap:
        return play
    if groups is not None:
        pmap = {m: g for m, g in pmap.items() if g in groups}
        if not pmap:
            return play

    def rewrite(s: Set[str]) -> Set[str]:
        return {pmap.get(x, x) for x in s}

    out = deepcopy(play)

    for sp in out.speeches:
        sp.who = rewrite(sp.who)
        sp.addressees = rewrite(sp.addressees)
    for mv in out.moves:
        mv.who = rewrite(mv.who)
        mv.corresp = rewrite(mv.corresp)

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

    # Re-derive strict <l>-based mute classification on the aggregated data.
    # A group is mute iff none of its members ever had a non-empty <l>
    # attributed; since verse_count is preserved on each speech and only
    # @who has been rewritten, the rule delivers the right answer for both
    # groups and untouched characters.
    spoken: Dict[str, int] = {}
    for sp in out.speeches:
        if sp.verse_count <= 0:
            continue
        for cid in sp.who:
            spoken[cid] = spoken.get(cid, 0) + sp.verse_count
    for cid, ch in out.characters.items():
        ch.is_mute = spoken.get(cid, 0) == 0

    return out


__all__ = ["build_partof_map", "aggregate_play"]
