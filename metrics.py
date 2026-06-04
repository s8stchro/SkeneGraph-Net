"""DraCor-compatible network metrics.

The structure of the output JSON mirrors the response of DraCor's
`/corpora/{c}/plays/{p}/metrics` endpoint:

  {
    "id":           ...,
    "name":         ...,
    "size":         ...,
    "numEdges":     ...,
    "density":      ...,
    "averageDegree": ...,
    "maxDegree":     ...,
    "maxDegreeIds":  [...],
    "diameter":      ...,
    "averagePathLength": ...,
    "averageClustering": ...,
    "numConnectedComponents": ...,
    "nodes": [
      {"id": ..., "degree": ..., "weightedDegree": ...,
       "betweenness": ..., "closeness": ..., "eigenvector": ...},
      ...
    ]
  }

Diameter and average path length are computed on the largest connected
component when the graph is disconnected, which is the convention DraCor
uses.
"""

from __future__ import annotations

from typing import Dict, List, Set, TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from parser import PlayData
    from segmentation import Segment


def _largest_component(G: nx.Graph) -> nx.Graph:
    if G.number_of_nodes() == 0 or nx.is_connected(G):
        return G
    nodes = max(nx.connected_components(G), key=len)
    return G.subgraph(nodes).copy()


def _safe_eigenvector(G: nx.Graph) -> Dict[str, float]:
    if G.number_of_edges() == 0:
        return {n: 0.0 for n in G.nodes()}
    try:
        return nx.eigenvector_centrality_numpy(G, weight="weight")
    except Exception:
        try:
            return nx.eigenvector_centrality(G, max_iter=1000, weight="weight")
        except Exception:
            return {n: 0.0 for n in G.nodes()}


def compute_metrics(G: nx.Graph, play_id: str = "", play_name: str = "") -> Dict:
    """Build DraCor-style metrics dict for a static graph."""
    n = G.number_of_nodes()
    m = G.number_of_edges()

    metrics = {
        "id": play_id,
        "name": play_name,
        "size": n,
        "numEdges": m,
        "density": float(nx.density(G)) if n > 1 else 0.0,
        "averageDegree": (sum(dict(G.degree()).values()) / n) if n > 0 else 0.0,
        "maxDegree": 0,
        "maxDegreeIds": [],
        "diameter": 0,
        "averagePathLength": 0.0,
        "averageClustering": float(nx.average_clustering(G, weight=None)) if m > 0 else 0.0,
        "numConnectedComponents": (nx.number_connected_components(G) if n > 0 else 0),
        "nodes": [],
    }

    if n == 0:
        return metrics

    # Degree-related stats.
    degrees = dict(G.degree())
    weighted_degrees = dict(G.degree(weight="weight"))
    if degrees:
        max_deg = max(degrees.values())
        metrics["maxDegree"] = int(max_deg)
        metrics["maxDegreeIds"] = sorted(
            [nid for nid, d in degrees.items() if d == max_deg]
        )

    # Diameter / avg path length over largest component (DraCor convention).
    if m > 0:
        H = _largest_component(G)
        if H.number_of_nodes() >= 2:
            try:
                metrics["diameter"] = int(nx.diameter(H))
            except nx.NetworkXError:
                metrics["diameter"] = 0
            try:
                metrics["averagePathLength"] = float(nx.average_shortest_path_length(H))
            except nx.NetworkXError:
                metrics["averagePathLength"] = 0.0

    # Centralities.
    if m > 0:
        betweenness = nx.betweenness_centrality(G, weight=None, normalized=True)
        closeness = nx.closeness_centrality(G)
        eigenvector = _safe_eigenvector(G)
    else:
        betweenness = {nid: 0.0 for nid in G.nodes()}
        closeness = {nid: 0.0 for nid in G.nodes()}
        eigenvector = {nid: 0.0 for nid in G.nodes()}

    nodes = []
    for nid in sorted(G.nodes()):
        nodes.append({
            "id": nid,
            "degree": int(degrees.get(nid, 0)),
            "weightedDegree": float(weighted_degrees.get(nid, 0.0)),
            "betweenness": round(float(betweenness.get(nid, 0.0)), 6),
            "closeness": round(float(closeness.get(nid, 0.0)), 6),
            "eigenvector": round(float(eigenvector.get(nid, 0.0)), 6),
        })
    metrics["nodes"] = nodes

    return metrics


# ---------------------------------------------------------------------------
# Extended metrics for ancient drama
# ---------------------------------------------------------------------------

def _gini(values: List[float], include_zeros: bool = False) -> float:
    """Standard Gini coefficient on a list of non-negative numbers.

    Returns 0 (perfectly equal) to 1 (one element holds everything).

    ``include_zeros`` controls whether zero-valued entries are kept in
    the distribution.  The cast-level Gini (`gini_verses`) drops them
    because a zero there means a non-speaker (a category we exclude
    from the speech distribution anyway).  The per-character temporal
    Gini, by contrast, must keep zeros: a zero there means "this
    character was silent in segment i", which is the very fact the
    metric needs to register.
    """
    if include_zeros:
        vs = [float(v) for v in values if v is not None and v >= 0]
    else:
        vs = [float(v) for v in values if v is not None and v > 0]
    if not vs:
        return 0.0
    vs.sort()
    n = len(vs)
    total = sum(vs)
    if total == 0:
        return 0.0
    cum = sum((i + 1) * v for i, v in enumerate(vs))
    return (2 * cum) / (n * total) - (n + 1) / n


def compute_demographics(play: "PlayData", include_mutes: bool = True) -> Dict:
    """Cast composition counts.

    The two requested count-pairs:
        speakers / mutes
        individuals / collectives
    plus sex (male / female / unspecified) and nature
    (human / divine / animal / concept / other).

    When ``include_mutes`` is False, mute characters are excluded from every
    bucket (the mute toggle in the dashboard should drive this).
    """
    speakers = mutes = 0
    individuals = collectives = 0
    collective_speakers = 0
    sex = {"male": 0, "female": 0, "unspecified": 0}
    nature = {"human": 0, "divine": 0, "animal": 0, "concept": 0, "other": 0}

    for ch in play.characters.values():
        if ch.is_mute and not include_mutes:
            continue
        if ch.is_mute:
            mutes += 1
        else:
            speakers += 1
        if ch.is_collective:
            collectives += 1
            if not ch.is_mute:
                collective_speakers += 1
        else:
            individuals += 1
        sex[ch.sex_class] += 1
        nature[ch.nature_class] += 1
    return {
        "speakers": speakers,
        "mutes": mutes,
        "individuals": individuals,
        "collectives": collectives,
        # collective characters who actually speak somewhere in the play
        # (intersection of `is_collective=True` and `is_mute=False`).  Used
        # by the corpus dashboard for the "collective speakers / total
        # speakers" ratio.
        "collective_speakers": collective_speakers,
        "sex": sex,
        "nature": nature,
    }


def compute_speech_distribution(play: "PlayData") -> Dict:
    """Per-character verse counts -> Gini, top speaker id, top verse share."""
    per_char: Dict[str, int] = {}
    for sp in play.speeches:
        if sp.verse_count <= 0 or not sp.who:
            continue
        for cid in sp.who:
            per_char[cid] = per_char.get(cid, 0) + sp.verse_count
    if not per_char:
        return {
            "gini_verses": 0.0,
            "top_speaker_id": None,
            "top_speaker_verse_share": 0.0,
            "total_verses_spoken": 0,
        }
    total = sum(per_char.values())
    top_id = max(per_char, key=per_char.get)
    top_share = per_char[top_id] / total if total else 0.0
    return {
        "gini_verses": _gini(list(per_char.values())),
        "top_speaker_id": top_id,
        "top_speaker_verse_share": top_share,
        "total_verses_spoken": total,
    }


def compute_segment_indices(segments: List["Segment"]) -> Dict:
    """Trilcke/Fischer 2017 event-based indices and three-actor diagnostic.

    * all-in-segment: index of the first segment by which the union of casts
      seen so far has matched the total cast appearing anywhere in the play.
    * all-in-index: (all_in_segment + 1) / num_segments  ∈ (0, 1].
      A value close to 1 means the cast keeps growing right up to the end
      (often tragedies); a value well below 1 means the play introduces
      its whole cast early (often comedies).  DraCor publishes this on
      Greek plays.
    * final-scene-size: |cast(last segment)| / |total appearing cast|.
      Trilcke/Fischer 2017 Fig. 2: comedy mean ≈ 0.49, tragedy ≈ 0.27.
    * max-simultaneous-speakers: the largest number of distinct speakers
      uttering at least one word inside a single segment -- a diagnostic
      for the classical three-actor rule.
    """
    if not segments:
        return {
            "all_in_segment": None,
            "all_in_index": 0.0,
            "final_scene_size": 0.0,
            "max_simultaneous_speakers": 0,
        }
    # If the play opens with an explicit empty pre-play segment 0, exclude
    # it from the all-in index search (it contributes no characters and
    # would shift the index by one without informative content).
    has_empty_initial = (
        len(segments) > 1
        and segments[0].is_initial
        and not segments[0].characters_present
    )
    scan_segments = segments[1:] if has_empty_initial else segments
    total_cast: Set[str] = set()
    for s in scan_segments:
        total_cast |= s.characters_present
    if not total_cast:
        return {
            "all_in_segment": None,
            "all_in_index": 0.0,
            "final_scene_size": 0.0,
            "max_simultaneous_speakers": 0,
        }
    seen: Set[str] = set()
    all_in_idx = None
    for i, s in enumerate(scan_segments):
        seen |= s.characters_present
        if seen >= total_cast:
            all_in_idx = i
            break
    # Trilcke/Fischer 2017 measures this on the last *acted* scene, not on
    # the empty-stage marker that the stage-direction segmenter appends at
    # the very end of the play.  We therefore walk back to the last segment
    # that still has a non-empty cast.
    final_cast = set()
    for s in reversed(segments):
        if s.characters_present:
            final_cast = s.characters_present
            break
    final_scene_size = len(final_cast) / len(total_cast) if total_cast else 0.0
    max_speakers = 0
    for s in segments:
        speakers_here: Set[str] = set()
        for sp in s.speeches:
            if sp.verse_count > 0:
                speakers_here |= sp.who
        if len(speakers_here) > max_speakers:
            max_speakers = len(speakers_here)
    return {
        "all_in_segment": all_in_idx,
        "all_in_index": (
            (all_in_idx + 1) / len(segments) if all_in_idx is not None else 1.0
        ),
        "final_scene_size": final_scene_size,
        "max_simultaneous_speakers": max_speakers,
    }


def compute_temporal_gini(segments: List["Segment"]) -> Dict[str, Dict]:
    """Per-character temporal Gini of per-segment verse counts.

    For every character with at least one verse anywhere in the play,
    builds their per-segment verse vector of length $N$ (zero-padded
    for silent and absent segments) and computes Gini over it.  This
    is perpendicular to the play-level `gini_verses`: that metric
    collapses the segment axis and asks how unequally speech is
    distributed across the cast; this one holds the segment axis open
    and asks, for one character at a time, how unequally that
    character's speech is distributed across the play.

    Range: 0 (perfectly even across all $N$ active segments) → close to
    1 (every verse in a single segment).  Two protagonist types emerge
    on the corpus: *steady* leads (low tGini, near-continuous stage
    presence, speech accumulates evenly) and *burst* leads (high tGini,
    onstage for only part of the play with concentrated set-pieces).

    The denominator $N$ is the dramaturgically-active span: the
    segmenter's empty bookend markers (sd segmenter convention) are
    stripped, matching the trim used by the corpus chorus beat chart,
    so that segmenter housekeeping does not inflate the metric.

    Returns a dict keyed by character id with fields:
        total_verses        (int, sum across active segments)
        speaking_segments   (int, count of segments with verse_count > 0)
        n_active_segments   (int, same for every character; = N after trim)
        temporal_gini       (float, see above)
    Characters with zero total verses get no entry.
    """
    if not segments:
        return {}
    # Same bookend trim as the chorus beat chart in corpus_dashboard:
    # drop leading / trailing segments whose characters_present is
    # empty.  This is independent of speech: a segment with one mute
    # character on stage is kept (zero contribution to every speaker's
    # vector, which is the correct dramaturgical reading).
    lo, hi = 0, len(segments)
    while lo < hi and not segments[lo].characters_present:
        lo += 1
    while hi > lo and not segments[hi - 1].characters_present:
        hi -= 1
    active = segments[lo:hi]
    n = len(active)
    if n == 0:
        return {}
    per_char_vec: Dict[str, List[int]] = {}
    for i, s in enumerate(active):
        for sp in s.speeches:
            if sp.verse_count <= 0 or not sp.who:
                continue
            for who in sp.who:
                vec = per_char_vec.get(who)
                if vec is None:
                    vec = [0] * n
                    per_char_vec[who] = vec
                vec[i] += sp.verse_count
    out: Dict[str, Dict] = {}
    for cid, vec in per_char_vec.items():
        total = sum(vec)
        speak = sum(1 for v in vec if v > 0)
        out[cid] = {
            "total_verses":      int(total),
            "speaking_segments": int(speak),
            "n_active_segments": int(n),
            "temporal_gini":     round(_gini(vec, include_zeros=True), 6),
        }
    return out


def compute_dynamic_metrics(graphs: List[nx.Graph]) -> List[Dict]:
    """Per-segment density / size / edges (cheap, useful for the dynamic plot)."""
    out = []
    for G in graphs:
        n = G.number_of_nodes()
        present = [nid for nid, d in G.nodes(data=True) if d.get("is_present")]
        sub = G.subgraph(present)
        out.append({
            "segment_id": G.graph.get("segment_id"),
            "segment_label": G.graph.get("segment_label"),
            "size": len(present),
            "numEdges": sub.number_of_edges(),
            "density": float(nx.density(sub)) if len(present) > 1 else 0.0,
            "verse_count": G.graph.get("verse_count", 0),
            "word_count": G.graph.get("word_count", 0),
            "is_initial": G.graph.get("is_initial", False),
            "is_final": G.graph.get("is_final", False),
        })
    return out


__all__ = [
    "compute_metrics",
    "compute_dynamic_metrics",
    "compute_demographics",
    "compute_speech_distribution",
    "compute_segment_indices",
    "compute_temporal_gini",
]
