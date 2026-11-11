"""Static and dynamic co-occurrence graph builders.

Every graph built here is an *undirected co-occurrence network*: the
segment's cast is joined into a clique, and the play's graph is the union
of those cliques -- one pair excepted, a collective and its own part, which
are one body (`_pairs`).  The edge says "these two shared a segment" and
nothing more.  It is never a claim that one addressed, perceived, or replied to the
other -- @toWhom is not read in this module, and directed readings belong to
the perception app.

The central methodological choice is therefore not what an edge *means* but
who counts as being in a segment -- the `segment_cast` argument:

  * `segment_cast="stage"` (case 1, mutes-in)
        A character is in a segment by standing on it (stage state tracked
        via <move>).  Cat-2 pure mutes appear as nodes and contribute edges.
        This is the original SkeneGraph-Net model and the default for
        `include_mutes=True`.

  * `segment_cast="speaking"` (case 2, mutes-out)
        A character is in a segment only by being given an utterance in
        it (`Segment.speakers`: the <sp>, not its word count).  Cat 2 (pure mutes) are excluded from the node
        set; cat 3 (sometimes-speakers) contribute edges only in segments
        where they actually speak.  Used with `include_mutes=False`,
        bringing the network close to DraCor but applied per-segment under
        all three segmenters.  Note that an edge here still records
        co-occurrence of speech in a segment, not an exchange between the
        two speakers: both may be addressing a third party or the audience.

Dynamic graph (departure from DraCor): one graph per segment plus a single
GEXF carrying <spells> intervals.  Both casts generalise: under `speaking`,
per-segment nodes are `Segment.speakers` rather than
`Segment.characters_present`.
"""

from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from parser import Character
from segmentation import Segment


def _kept_characters(
    characters: Dict[str, Character],
    segments: List[Segment],
    include_mutes: bool,
    segment_cast: str = "stage",
) -> Set[str]:
    """Return the character ids that should appear as nodes.

    Under `segment_cast="stage"` (mutes-in) the node set is the union of
    every segment's `characters_present` plus everyone who appears as a
    speaker.  The second clause is a guard rather than a rule: no character
    in the present corpus carries a speech without also being placed on
    stage, but TEI that attributes one to a figure the stage directions
    never place would otherwise lose them.

    Under `segment_cast="speaking"` (mutes-out) the node set collapses to
    those who appear in some `seg.speakers` -- that is, to whom the play
    attributes at least one <sp>.  The test is the <sp>, not its word
    count: a speech whose text is lost still credits its speaker, which is
    what keeps the XOPOY interludes from registering as an empty stage
    (see `Segment.speakers`).  The corpus holds ten such speeches.
    """
    appearing: Set[str] = set()
    if segment_cast == "speaking":
        for seg in segments:
            appearing |= seg.speakers
    else:
        for seg in segments:
            appearing |= seg.characters_present
            for sp in seg.speeches:
                appearing |= sp.who
    kept = set()
    for cid in appearing:
        ch = characters.get(cid)
        if ch is None:
            # Referenced in @who but not declared in <listPerson> -- still keep.
            kept.add(cid)
            continue
        if not include_mutes and ch.is_mute:
            continue
        kept.add(cid)
    return kept


def _pairs(cast, characters: Dict[str, Character]):
    """The pairs a segment's cast joins: every two of its members, except a
    collective and one of its own parts.

    A part and its whole are one body.  On the stage-direction spine they
    never share a segment -- a split takes the whole off as the parts come
    on -- but a textual unit that holds a split or a merge holds both, and
    joining them asserted an encounter between the chorus and its own
    halves: 40 edges across the views of four Aristophanic plays, every one
    raising the chorus's degree and triangle count.  `Character.part_of` is
    transitive, so a part is kept apart from every whole it belongs to.
    """
    for a, b in combinations(sorted(cast), 2):
        ca, cb = characters.get(a), characters.get(b)
        if (ca is not None and b in ca.part_of) or \
           (cb is not None and a in cb.part_of):
            continue
        yield a, b


def _node_attrs(cid: str, characters: Dict[str, Character]) -> Dict:
    ch = characters.get(cid)
    if ch is None:
        return {"id": cid, "name": cid, "name_grc": "", "is_mute": False,
                "is_collective": False, "is_chorus": False, "sex": ""}
    return {
        "id": ch.id,
        "name": ch.display_name,
        "name_grc": ch.name_grc,
        "is_mute": ch.is_mute,
        "is_collective": ch.is_collective,
        "is_chorus": ch.is_chorus,
        "sex": ch.sex or "",
    }


def build_static(
    segments: List[Segment],
    characters: Dict[str, Character],
    include_mutes: bool = True,
    edge_weight: str = "segments",  # 'segments' | 'words'
    segment_cast: str = "stage",    # 'stage' | 'speaking'
) -> nx.Graph:
    """Aggregate static graph for the whole play.  See the module docstring
    for the two values of `segment_cast`."""
    G = nx.Graph()
    kept = _kept_characters(characters, segments, include_mutes, segment_cast)
    for cid in sorted(kept):
        G.add_node(cid, **_node_attrs(cid, characters))

    # Track per-edge metrics across all segments.
    edge_segments: Dict[Tuple[str, str], int] = {}
    edge_words:    Dict[Tuple[str, str], int] = {}
    edge_segids:   Dict[Tuple[str, str], List[int]] = {}

    for seg in segments:
        seg_set = seg.speakers if segment_cast == "speaking" else seg.characters_present
        for a, b in _pairs(seg_set & kept, characters):
            key = (a, b)
            edge_segments[key] = edge_segments.get(key, 0) + 1
            # Words spoken in the segments the pair shares, on the app's one
            # word rule (each speech counted once per id in its @who).
            edge_words[key] = edge_words.get(key, 0) + seg.word_count
            edge_segids.setdefault(key, []).append(seg.id)

    for (a, b), n in edge_segments.items():
        if edge_weight == "words":
            w = edge_words[(a, b)]
        else:
            w = n
        G.add_edge(
            a, b,
            weight=w,
            segments_shared=n,
            words_shared=edge_words[(a, b)],
            segment_ids=edge_segids[(a, b)],
        )

    G.graph["network_type"] = "static"
    G.graph["include_mutes"] = include_mutes
    G.graph["edge_weight"] = edge_weight
    G.graph["segment_cast"] = segment_cast
    G.graph["num_segments"] = len(segments)
    return G


def build_dynamic(
    segments: List[Segment],
    characters: Dict[str, Character],
    include_mutes: bool = True,
    segment_cast: str = "stage",
) -> List[nx.Graph]:
    """One graph per segment.  Same node set across all graphs (kept).

    A node's `is_present` attribute marks per-segment activity in whatever
    sense `segment_cast` encodes: on stage under `stage`, given an
    utterance in the segment under `speaking`.
    """
    kept = _kept_characters(characters, segments, include_mutes, segment_cast)
    graphs: List[nx.Graph] = []
    for seg in segments:
        G = nx.Graph()
        seg_set = seg.speakers if segment_cast == "speaking" else seg.characters_present
        present = seg_set & kept
        for cid in sorted(kept):
            attrs = _node_attrs(cid, characters)
            attrs["is_present"] = cid in present
            G.add_node(cid, **attrs)
        for a, b in _pairs(present, characters):
            G.add_edge(
                a, b,
                weight=1,
                word_count=seg.word_count,
            )
        G.graph["segment_id"] = seg.id
        G.graph["segment_label"] = seg.label
        G.graph["is_initial"] = seg.is_initial
        G.graph["is_final"] = seg.is_final
        G.graph["word_count"] = seg.word_count
        G.graph["network_type"] = "dynamic"
        G.graph["include_mutes"] = include_mutes
        G.graph["segment_cast"] = segment_cast
        graphs.append(G)
    return graphs


def build_dynamic_spell_graph(
    segments: List[Segment],
    characters: Dict[str, Character],
    include_mutes: bool = True,
    segment_cast: str = "stage",
) -> nx.Graph:
    """Single graph carrying per-segment spell intervals.

    For each character, store a list of [start, end) segment intervals
    during which they are "active" in the edge-rule's sense (stage-
    present under `presence`, speaking under `speaking`).  For each
    pair, store intervals of simultaneous activity.  This is the
    representation Gephi reads natively for GEXF mode="dynamic".
    """
    kept = _kept_characters(characters, segments, include_mutes, segment_cast)
    G = nx.Graph()
    G.graph["mode"] = "dynamic"
    G.graph["timeformat"] = "double"
    G.graph["network_type"] = "dynamic-spell"
    G.graph["include_mutes"] = include_mutes
    G.graph["segment_cast"] = segment_cast
    G.graph["num_segments"] = len(segments)

    def _seg_set(seg):
        return seg.speakers if segment_cast == "speaking" else seg.characters_present

    # Compute spells per node.  Seeded in sorted order (as build_static and
    # build_dynamic do): `kept` is a set, so iterating it directly made the
    # node insertion order depend on the hash seed.  That reached the GEXF
    # twice over -- nodes were emitted in that order, and each edge's
    # source/target orientation follows whichever endpoint networkx stored
    # first -- so two identical runs produced different bytes for the same
    # graph.  Sorting here makes the exported file reproducible.
    node_spells: Dict[str, List[Tuple[int, int]]] = {cid: [] for cid in sorted(kept)}
    for seg in segments:
        for cid in _seg_set(seg) & kept:
            spells = node_spells[cid]
            if spells and spells[-1][1] == seg.id:
                spells[-1] = (spells[-1][0], seg.id + 1)
            else:
                spells.append((seg.id, seg.id + 1))

    for cid, spells in node_spells.items():
        attrs = _node_attrs(cid, characters)
        attrs["spells"] = spells          # consumed by exporter
        attrs["start"] = spells[0][0] if spells else 0
        attrs["end"] = spells[-1][1] if spells else len(segments)
        G.add_node(cid, **attrs)

    # Compute spells per edge.
    edge_spells: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}
    for seg in segments:
        for a, b in _pairs(_seg_set(seg) & kept, characters):
            spells = edge_spells.setdefault((a, b), [])
            if spells and spells[-1][1] == seg.id:
                spells[-1] = (spells[-1][0], seg.id + 1)
            else:
                spells.append((seg.id, seg.id + 1))

    for (a, b), spells in edge_spells.items():
        G.add_edge(
            a, b,
            weight=sum(e - s for s, e in spells),
            spells=spells,
            start=spells[0][0],
            end=spells[-1][1],
        )

    return G


__all__ = [
    "build_static",
    "build_dynamic",
    "build_dynamic_spell_graph",
]
