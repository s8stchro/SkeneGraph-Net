"""Static and dynamic co-presence graph builders.

Two edge rules (the central methodological choice of the app):

  * `edge_rule="presence"` (case 1, mutes-in)
        Edge (A, B) iff A and B are physically co-present in at least one
        segment (stage state tracked via <move>).  Cat-2 pure mutes appear
        as nodes and contribute edges.  This is the original SkeneGraph-Net
        model and the default for `include_mutes=True`.

  * `edge_rule="co_speech"` (case 2, mutes-out)
        Edge (A, B) iff A and B each have >=1 non-empty <l> attributed in
        the same segment (`Segment.speakers`).  Cat 2 (pure mutes) are
        excluded from the node set; cat 3 (sometimes-speakers) contribute
        edges only in segments where they actually speak.  Used with
        `include_mutes=False`, bringing the network close to DraCor but
        applied per-segment under all three segmenters.

Dynamic graph (departure from DraCor): one graph per segment plus a single
GEXF carrying <spells> intervals.  Both rules generalise: under
`co_speech`, per-segment nodes are `Segment.speakers` rather than
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
    edge_rule: str = "presence",
) -> Set[str]:
    """Return the character ids that should appear as nodes.

    Under `edge_rule="presence"` (mutes-in) the node set is the union of
    every segment's `characters_present` plus everyone who appears as a
    speaker.  Under `edge_rule="co_speech"` (mutes-out) the node set
    collapses to those who have at least one non-empty <l> anywhere in
    the play -- equivalently, those who appear in some `seg.speakers`.
    """
    appearing: Set[str] = set()
    if edge_rule == "co_speech":
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
    edge_weight: str = "segments",  # 'segments' | 'verses' | 'words'
    edge_rule: str = "presence",    # 'presence' | 'co_speech'
) -> nx.Graph:
    """Aggregate static graph for the whole play.  See module docstring
    for the two edge rules."""
    G = nx.Graph()
    kept = _kept_characters(characters, segments, include_mutes, edge_rule)
    for cid in sorted(kept):
        G.add_node(cid, **_node_attrs(cid, characters))

    # Track per-edge metrics across all segments.
    edge_segments: Dict[Tuple[str, str], int] = {}
    edge_verses:   Dict[Tuple[str, str], int] = {}
    edge_words:    Dict[Tuple[str, str], int] = {}
    edge_segids:   Dict[Tuple[str, str], List[int]] = {}

    for seg in segments:
        seg_set = seg.speakers if edge_rule == "co_speech" else seg.characters_present
        present = sorted(seg_set & kept)
        if len(present) < 2:
            continue
        for a, b in combinations(present, 2):
            key = (a, b)
            edge_segments[key] = edge_segments.get(key, 0) + 1
            edge_verses[key] = edge_verses.get(key, 0) + seg.verse_count
            edge_words[key] = edge_words.get(key, 0) + seg.word_count
            edge_segids.setdefault(key, []).append(seg.id)

    for (a, b), n in edge_segments.items():
        if edge_weight == "verses":
            w = edge_verses[(a, b)]
        elif edge_weight == "words":
            w = edge_words[(a, b)]
        else:
            w = n
        G.add_edge(
            a, b,
            weight=w,
            segments_shared=n,
            verses_shared=edge_verses[(a, b)],
            words_shared=edge_words[(a, b)],
            segment_ids=edge_segids[(a, b)],
        )

    G.graph["network_type"] = "static"
    G.graph["include_mutes"] = include_mutes
    G.graph["edge_weight"] = edge_weight
    G.graph["edge_rule"] = edge_rule
    G.graph["num_segments"] = len(segments)
    return G


def build_dynamic(
    segments: List[Segment],
    characters: Dict[str, Character],
    include_mutes: bool = True,
    edge_rule: str = "presence",
) -> List[nx.Graph]:
    """One graph per segment.  Same node set across all graphs (kept).

    A node's `is_present` attribute marks per-segment activity in whatever
    sense the edge rule encodes: stage co-presence under `presence`,
    speaker-in-segment under `co_speech`.
    """
    kept = _kept_characters(characters, segments, include_mutes, edge_rule)
    graphs: List[nx.Graph] = []
    for seg in segments:
        G = nx.Graph()
        seg_set = seg.speakers if edge_rule == "co_speech" else seg.characters_present
        present = seg_set & kept
        for cid in sorted(kept):
            attrs = _node_attrs(cid, characters)
            attrs["is_present"] = cid in present
            G.add_node(cid, **attrs)
        for a, b in combinations(sorted(present), 2):
            G.add_edge(
                a, b,
                weight=1,
                verse_count=seg.verse_count,
                word_count=seg.word_count,
            )
        G.graph["segment_id"] = seg.id
        G.graph["segment_label"] = seg.label
        G.graph["is_initial"] = seg.is_initial
        G.graph["is_final"] = seg.is_final
        G.graph["verse_count"] = seg.verse_count
        G.graph["word_count"] = seg.word_count
        G.graph["network_type"] = "dynamic"
        G.graph["include_mutes"] = include_mutes
        G.graph["edge_rule"] = edge_rule
        graphs.append(G)
    return graphs


def build_dynamic_spell_graph(
    segments: List[Segment],
    characters: Dict[str, Character],
    include_mutes: bool = True,
    edge_rule: str = "presence",
) -> nx.Graph:
    """Single graph carrying per-segment spell intervals.

    For each character, store a list of [start, end) segment intervals
    during which they are "active" in the edge-rule's sense (stage-
    present under `presence`, speaking under `co_speech`).  For each
    pair, store intervals of simultaneous activity.  This is the
    representation Gephi reads natively for GEXF mode="dynamic".
    """
    kept = _kept_characters(characters, segments, include_mutes, edge_rule)
    G = nx.Graph()
    G.graph["mode"] = "dynamic"
    G.graph["timeformat"] = "double"
    G.graph["network_type"] = "dynamic-spell"
    G.graph["include_mutes"] = include_mutes
    G.graph["edge_rule"] = edge_rule
    G.graph["num_segments"] = len(segments)

    def _seg_set(seg):
        return seg.speakers if edge_rule == "co_speech" else seg.characters_present

    # Compute spells per node.
    node_spells: Dict[str, List[Tuple[int, int]]] = {cid: [] for cid in kept}
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
        present = sorted(_seg_set(seg) & kept)
        for a, b in combinations(present, 2):
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
