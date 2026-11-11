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
       "betweenness": ..., "closeness": ..., "eigenvector": ...,
       "clustering": ..., "triangles": ...},
      ...
    ]
  }

Diameter and average path length are computed on the largest connected
component when the graph is disconnected, which is the convention DraCor
uses.  The two per-node fields DraCor's endpoint does not carry --
`clustering` and `triangles` -- are the local counterparts of
`averageClustering`, computed as NetworkX computes them.

No per-character speech count is published, DraCor's `numOfSpeechActs`
notwithstanding: a character's speech is cut into several <sp> wherever a
move falls inside it or the addressee changes, so the count would report
the annotation rather than the play (82 of the corpus's 6474 speeches are
such continuations, and the share runs from 0.2% to 3.3% by play).  Words
are the measure that survives the cut, and `num_speeches` stays per
segment, where it counts events on stage rather than a character's share.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set, TYPE_CHECKING

import networkx as nx

from segmentation import active_span

log = logging.getLogger("SkeneGraph-Net.metrics")

if TYPE_CHECKING:
    from parser import PlayData
    from segmentation import Segment


def _largest_component(G: nx.Graph) -> nx.Graph:
    if G.number_of_nodes() == 0 or nx.is_connected(G):
        return G
    nodes = max(nx.connected_components(G), key=len)
    return G.subgraph(nodes).copy()


_numpy_solver_reported = False


def _report_missing_numpy_solver(exc: ImportError) -> None:
    """Say, once per run, that the published solver is not the one running.

    `eigenvector_centrality_numpy` is where the `eigenvector` column of
    `characters.csv` and the field in `metrics.json` come from.  NetworkX
    requires neither NumPy nor SciPy -- they sit behind its `default` extra
    -- so the import can fail on an otherwise working install, and the
    power-iteration fallback answers a little differently: across the corpus
    the values move in the sixth decimal for 2 to 25 characters per play.
    Caught silently, that divergence shows up only when somebody diffs two
    dashboards.
    """
    global _numpy_solver_reported
    if _numpy_solver_reported:
        return
    _numpy_solver_reported = True
    log.warning(
        "eigenvector centrality: %s -- using power iteration for the rest of "
        "this run.  Its values differ from the published ones at about the "
        "sixth decimal; install numpy and scipy (see requirements.txt) to "
        "reproduce them.", exc)


def _eigenvector_on(H: nx.Graph) -> Dict[str, float]:
    """Eigenvector centrality of one connected graph, or zeros if it defies
    both solvers."""
    if H.number_of_edges() == 0:
        return {n: 0.0 for n in H.nodes()}
    try:
        return nx.eigenvector_centrality_numpy(H, weight="weight")
    except ImportError as exc:
        # Not a failure of this graph but of the install: worth naming, and
        # worth naming once rather than per component.
        _report_missing_numpy_solver(exc)
    except Exception:
        pass
    try:
        return nx.eigenvector_centrality(H, max_iter=1000, weight="weight")
    except Exception as exc:
        # Zeros are indistinguishable from a genuine result here -- an
        # isolate scores 0 legitimately -- so say so rather than let a
        # whole component read as uncentral because both solvers failed.
        log.warning(
            "eigenvector centrality failed on a component of %d nodes "
            "(%d edges); reporting 0 for %s: %s",
            H.number_of_nodes(), H.number_of_edges(),
            ", ".join(sorted(map(str, H.nodes()))[:6]), exc)
        return {n: 0.0 for n in H.nodes()}


def _safe_eigenvector(G: nx.Graph) -> Dict[str, float]:
    """Eigenvector centrality, computed one connected component at a time.

    Eigenvector centrality is defined per component: the principal eigenvector
    of a disconnected adjacency matrix belongs to whichever component has the
    larger spectral radius, and the rest of the vector carries no information
    about the others.  `eigenvector_centrality_numpy` says so by refusing a
    disconnected graph (`AmbiguousSolution`); the power-iteration fallback does
    not refuse, but returns the decay of an iteration that has converged
    elsewhere -- values around 1e-6 and below, which look like small
    centralities in a sorted table and are not.

    Computing per component gives every character a value from their own
    component's eigenvector.  Each component is normalised to unit Euclidean
    length, as NetworkX normalises a whole graph, so values are comparable
    inside a component and not across components; a character alone in one has
    no edges and is given 0.  For a connected graph this is one component and
    the result is exactly what the solver returned before.
    """
    if G.number_of_edges() == 0:
        return {n: 0.0 for n in G.nodes()}
    if nx.is_connected(G):
        return _eigenvector_on(G)
    out: Dict[str, float] = {}
    for comp in nx.connected_components(G):
        out.update(_eigenvector_on(G.subgraph(comp)))
    return out


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

    # Local clustering and the triangle count behind it.  Unweighted, as
    # `averageClustering` above is: the mean of these values over all nodes.
    # A node with fewer than two neighbours closes nothing, and NetworkX
    # gives it 0 where igraph gives NaN; this keeps NetworkX's convention,
    # the one the play-level mean already follows.
    clustering = nx.clustering(G, weight=None)
    triangles = nx.triangles(G)

    nodes = []
    for nid in sorted(G.nodes()):
        nodes.append({
            "id": nid,
            "degree": int(degrees.get(nid, 0)),
            "weightedDegree": float(weighted_degrees.get(nid, 0.0)),
            "betweenness": round(float(betweenness.get(nid, 0.0)), 6),
            "closeness": round(float(closeness.get(nid, 0.0)), 6),
            "eigenvector": round(float(eigenvector.get(nid, 0.0)), 6),
            "clustering": round(float(clustering.get(nid, 0.0)), 6),
            "triangles": int(triangles.get(nid, 0)),
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
    the distribution.  The cast-level Gini (`gini_words`) drops them
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
    plus sex (male / female / mixed / unspecified) and nature
    (human / divine / animal / concept / other).

    When ``include_mutes`` is False, mute characters are excluded from every
    bucket (the mute toggle in the dashboard should drive this).
    """
    speakers = mutes = 0
    individuals = collectives = 0
    collective_speakers = 0
    sex = {"male": 0, "female": 0, "mixed": 0, "unspecified": 0}
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
    """Per-character word counts -> Gini, top speaker(s), top word share.

    Every character holding the largest total is reported, in `top_speaker_ids`.
    Ties do not arise in the Aristophanic corpus, where the leading role is
    thousands of words clear of a tie, but a two-hander can produce one, and
    the alternative -- picking a winner by an accident of iteration order --
    would be a rule invented by the code and stated nowhere.

    `top_speaker_id` is the first of that list, kept as a scalar for the
    fields and columns that need one referent (notably the top speaker's
    temporal Gini, §5).
    """
    per_char: Dict[str, int] = {}
    for sp in play.speeches:
        if sp.word_count <= 0 or not sp.who:
            continue
        # sorted(), not sp.who: iterating the set leaves `per_char` in an
        # order that depends on Python's per-process string hashing, and a
        # build should not vary between runs.
        for cid in sorted(sp.who):
            per_char[cid] = per_char.get(cid, 0) + sp.word_count
    if not per_char:
        # Every key the populated branch returns: a play where nobody has a
        # surviving word still has to answer the same questions, or a reader
        # of metrics.json meets a KeyError instead of a zero.
        return {
            "gini_words": 0.0,
            "effective_speakers": 0.0,
            "top_speaker_id": None,
            "top_speaker_ids": [],
            "top_speaker_word_share": 0.0,
            "total_words_spoken": 0,
        }
    total = sum(per_char.values())
    top_words = max(per_char.values())
    top_ids = sorted(cid for cid, w in per_char.items() if w == top_words)
    top_share = top_words / total if total else 0.0
    return {
        "gini_words": _gini(list(per_char.values())),
        "effective_speakers": _effective_speakers(per_char.values()),
        "top_speaker_id": top_ids[0],
        "top_speaker_ids": top_ids,
        "top_speaker_word_share": top_share,
        "total_words_spoken": total,
    }


def _effective_speakers(values) -> float:
    """How many voices effectively carry the play: $1 / \\sum_c s_c^2$.

    The inverse Herfindahl index -- the effective number of parties of
    Laakso & Taagepera (1979), the inverse Simpson index in ecology.  Equal to
    $n$ when every speaker says the same amount and to $1$ when one says
    everything, so it is read in speakers rather than on a $[0,1)$ scale.

    It is here as the companion the Gini needs rather than as a second
    inequality measure.  Weighting by share and not by rank, it barely notices
    a character with a line and a half, where the Gini moves by up to a tenth
    on the same addition; and it has no ceiling tied to cast size, so a
    small-cast play may be compared with a large-cast one.  See methods §4.
    """
    vs = [float(v) for v in values if v and v > 0]
    total = sum(vs)
    if not vs or total <= 0:
        return 0.0
    return (total * total) / sum(v * v for v in vs)


def compute_segment_indices(segments: List["Segment"],
                            kept: Optional[Set[str]] = None,
                            segment_cast: str = "stage") -> Dict:
    """Trilcke/Fischer 2017 event-based indices and three-actor diagnostic.

    The active model is given by the same two axes that define the network
    models themselves, and both must be passed, or the indices describe a
    graph the reader is not shown.

    `kept` is the model's node set (from `network._kept_characters`): every
    cast read here is intersected with it, so the indices answer for the graph
    the model selects rather than for the annotated stage.  `segment_cast` is
    the criterion of presence, and must be the one handed to the graph
    builder: "stage" counts the characters standing in a segment, "speaking"
    only those to whom the segment attributes an utterance (`Segment.speakers`
    -- the <sp>, not the word count, exactly as the edges are drawn).
    `kept=None` with the default "stage" keeps the raw-spine reading (every
    annotated body counts), which is what the tests use by default.

    Under "speaking" both quantities answer strictly: the all-in index reports
    when the cast has finished speaking itself complete rather than when every
    speaker has been seen on stage, and the final share counts who still
    speaks in the last segment carrying speech rather than who stands there.
    Both readings are available across the model set -- the play-level
    speaking model counts the same company by presence -- so the two
    questions stay separable, one model each.

    * all-in-segment: index of the first segment by which the union of casts
      seen so far has matched the total cast appearing anywhere in the play.
      The index is into the *scanned* segments -- the pre-play empty marker,
      where present, is excluded from both the search and the divisor.
      Emptiness is judged by the model cast, so an opening beat holding only
      characters the model drops is excluded the same way, as is one in which
      nobody speaks when the cast is the speaking one.
    * all-in-index: (all_in_segment + 1) / num_scanned_segments  ∈ (0, 1].
    * all-in-segment-label: the matched segment's own short label (sd-89,
      s033, L07) -- the display form.  The raw index is 0-based and lives in
      the scanned frame, so it matches nothing a reader can point at; the
      label does.
      A value close to 1 means the cast keeps growing right up to the end
      (often tragedies); a value well below 1 means the play introduces
      its whole cast early (often comedies).  DraCor publishes this on
      Greek plays.
    * final-segment-cast-share: |cast(last segment)| / |total cast|, both
      casts as the active model sees them.
      Trilcke/Fischer 2017 Fig. 2: comedy mean ≈ 0.49, tragedy ≈ 0.27.
    * max-simultaneous-speakers: the largest number of distinct speakers
      uttering at least one word inside a single segment -- a diagnostic
      for the classical three-actor rule.
    """
    if not segments:
        return {
            "all_in_segment": None,
            "all_in_segment_label": None,
            "all_in_index": 0.0,
            "final_segment_cast_share": 0.0,
            "max_simultaneous_speakers": 0,
        }
    def cast_of(seg) -> Set[str]:
        """The segment's cast as the active model sees it."""
        base = seg.speakers if segment_cast == "speaking" else seg.characters_present
        return base if kept is None else base & kept

    # If the play opens with a segment that is empty AS THE MODEL SEES IT --
    # the explicit pre-play marker, or an opening beat holding only
    # characters the model drops -- exclude it from the all-in search and
    # from the divisor alike, so numerator and denominator stay in one frame.
    has_empty_initial = (
        len(segments) > 1
        and segments[0].is_initial
        and not cast_of(segments[0])
    )
    scan_segments = segments[1:] if has_empty_initial else segments

    total_cast: Set[str] = set()
    for s in scan_segments:
        total_cast |= cast_of(s)
    if not total_cast:
        return {
            "all_in_segment": None,
            "all_in_segment_label": None,
            "all_in_index": 0.0,
            "final_segment_cast_share": 0.0,
            "max_simultaneous_speakers": 0,
        }
    seen: Set[str] = set()
    all_in_idx = None
    all_in_seg = None
    for i, s in enumerate(scan_segments):
        seen |= cast_of(s)
        if seen >= total_cast:
            all_in_idx = i
            all_in_seg = s
            break
    # Display label for the matched segment: the trailing token of the div
    # spines' labels is the pointable id (middle-seq-33-s033 -> s033,
    # large-seq-7-L07 -> L07); sd labels are already short (sd-89).
    all_in_label = None
    if all_in_seg is not None:
        lbl = all_in_seg.label or ""
        m = re.match(r"(?:large-seq|middle-seq)-\d+-(.+)$", lbl)
        all_in_label = m.group(1) if m else (lbl or None)
    # Trilcke/Fischer 2017 measures this on the last *acted* scene, not on
    # the empty-stage marker that the stage-direction segmenter appends at
    # the very end of the play.  We therefore walk back to the last segment
    # that still has a non-empty cast.  The walk-back is what makes the
    # speaking cast usable here at all: without it every play whose last
    # beats are silent business would read 0.000.
    final_cast: Set[str] = set()
    for s in reversed(segments):
        if cast_of(s):
            final_cast = cast_of(s)
            break
    final_segment_cast_share = len(final_cast) / len(total_cast) if total_cast else 0.0
    # Deliberately word-based, unlike `Segment.speakers`, which credits a
    # speech whose text is lost.  This is an actor-rule diagnostic: it must
    # count voices actually attested with surviving text, or a lacuna could
    # raise it.  Aligning the two would take Clouds from 3 to 4 on the
    # strength of the gap at 888a alone.
    max_speakers = 0
    for s in segments:
        speakers_here: Set[str] = set()
        for sp in s.speeches:
            if sp.word_count > 0:
                speakers_here |= sp.who
        if len(speakers_here) > max_speakers:
            max_speakers = len(speakers_here)
    return {
        "all_in_segment": all_in_idx,
        "all_in_segment_label": all_in_label,
        # Divided by the SCANNED segments, the same frame all_in_idx indexes.
        # Using len(segments) here put numerator and denominator in different
        # frames wherever a play opens with the empty pre-play marker, so the
        # index came out one segment short on every sd run and could never
        # reach 1.0 there.
        "all_in_index": (
            (all_in_idx + 1) / len(scan_segments) if all_in_idx is not None else 1.0
        ),
        "final_segment_cast_share": final_segment_cast_share,
        "max_simultaneous_speakers": max_speakers,
    }


def compute_temporal_gini(segments: List["Segment"]) -> Dict[str, Dict]:
    """Per-character temporal Gini of per-segment word counts.

    For every character with at least one word anywhere in the play, builds
    their per-segment word vector over the segments they are ON STAGE for,
    zero-padded for the ones they stand through in silence, and computes Gini
    over it.  It asks how unevenly a character speaks across their own
    presence -- how much of their stage time is silent -- which is the one
    question here that an encoding without a presence layer cannot pose.

    Range: 0 (speaks evenly throughout their presence) → close to 1 (their
    whole word total in one segment of a long presence).  The maximum is
    (m-1)/m for a span of m segments, so a character on stage briefly is
    measured against a lower ceiling than one present throughout.

    The span is per character and is presence union speech, so a speech
    attributed to a character never annotated as entering is still counted
    (the parser warns about that case separately).  Padding across the whole
    play instead -- the earlier definition -- made the value a proxy for
    absence: over the corpus it correlated at 0.97 with the share of segments
    a character does not speak in, which the `speaking_segments` field
    already reports.

    The play-level active span is still trimmed of the segmenter's empty
    bookend markers and reported as `n_active_segments`, unchanged, for the
    ratio the dashboard prints beside this.

    Returns a dict keyed by character id with fields:
        total_words         (int, sum across active segments)
        speaking_segments   (int, count of segments with word_count > 0)
        n_onstage_segments  (int, the character's own span -- the divisor)
        n_active_segments   (int, same for every character; = N after trim)
        temporal_gini       (float, see above)
    Characters with zero total words get no entry.
    """
    if not segments:
        return {}
    active = active_span(segments)
    n = len(active)
    if n == 0:
        return {}
    # Words per segment, and the segments each character is present for.
    # The span is presence UNION speech: a speech in a segment the character
    # is not annotated present for would otherwise drop out of the vector and
    # out of total_words, putting this metric at odds with §4's totals.
    words: Dict[str, Dict[int, int]] = {}
    span: Dict[str, Set[int]] = {}
    for i, s in enumerate(active):
        for cid in s.characters_present:
            span.setdefault(cid, set()).add(i)
        for sp in s.speeches:
            if sp.word_count <= 0 or not sp.who:
                continue
            for who in sp.who:
                words.setdefault(who, {})[i] = \
                    words.setdefault(who, {}).get(i, 0) + sp.word_count
                span.setdefault(who, set()).add(i)
    out: Dict[str, Dict] = {}
    for cid, by_seg in words.items():
        vec = [by_seg.get(i, 0) for i in sorted(span[cid])]
        total = sum(vec)
        speak = sum(1 for v in vec if v > 0)
        out[cid] = {
            "total_words":        int(total),
            "speaking_segments":  int(speak),
            "n_onstage_segments": int(len(vec)),
            "n_active_segments":  int(n),
            "temporal_gini":      round(_gini(vec, include_zeros=True), 6),
        }
    return out


def compute_dynamic_metrics(graphs: List[nx.Graph]) -> List[Dict]:
    """Per-segment size / edges / words for the dynamic plot and its export.

    No density here.  A segment's graph is its cast joined into a clique, so
    its density is 1 wherever two or more stand together and 0 otherwise --
    across the corpus under stage co-presence, 784 segments at 1.0 and 142 at
    0.0, and nothing else but the nine textual units that hold a collective
    beside its own part, a pair never joined.  A column of that shape reads
    as a finding ("fully connected") when
    it is a restatement of the construction, so it is not written.  `numEdges`
    is kept: it is the same fact stated as a count, $n(n-1)/2$ less any pair of
    a collective and its own part (`network._pairs`), which a reader
    rebuilding the segment's graph needs and nobody mistakes for a result.
    """
    out = []
    for G in graphs:
        present = [nid for nid, d in G.nodes(data=True) if d.get("is_present")]
        sub = G.subgraph(present)
        out.append({
            "segment_id": G.graph.get("segment_id"),
            "segment_label": G.graph.get("segment_label"),
            "size": len(present),
            "numEdges": sub.number_of_edges(),
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
