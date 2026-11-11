"""Properties that must hold of the data model on a whole play.

The unit tests pin each function's behaviour on synthetic input; these check
that the pieces still agree with one another on real TEI, in every
configuration the app offers -- three spines, three network models, with and
without partOf aggregation, eighteen per play.

They exist because an audit of the code found two defects that no
per-function test could see: a field returned by one branch of a function and
not the other, and one rule implemented twice in two files.  Both were
failures of agreement rather than of logic, which is what these check.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Set

import networkx as nx
import pytest

from aggregation import absorb_silent_parts, aggregate_play
from conftest import APP_DIR
from metrics import compute_metrics, compute_speech_distribution
from network import _kept_characters, build_static
from parser import PlayData, parse_play
from segmentation import SEGMENTERS, fold_for_model

CORPUS_DIR = APP_DIR.parent / "01-SkeneGraph-corpus" / "comedy"

MODELS = {"full": (True, "stage"),
          "p-speaking": (False, "stage"),
          "s-speaking": (False, "speaking")}


@dataclass
class Config:
    """One (play, spine, model, aggregation) view, built as the app builds it."""
    label: str
    play: PlayData
    segments: List
    kept: Set[str]
    graph: nx.Graph
    metrics: Dict
    speech: Dict


def configurations(play: PlayData) -> Iterator[Config]:
    for agg in (False, True):
        play0 = aggregate_play(play) if agg else play
        for model, (inc_mutes, seg_cast) in MODELS.items():
            p = absorb_silent_parts(play0) if model == "p-speaking" else play0
            speech = compute_speech_distribution(p)
            for spine, segmenter in sorted(SEGMENTERS.items()):
                segs = segmenter(p)
                if not segs:
                    continue
                if spine == "sd" and not inc_mutes:
                    segs = fold_for_model(
                        segs,
                        _kept_characters(p.characters, segs, inc_mutes, seg_cast),
                        seg_cast)
                kept = _kept_characters(p.characters, segs, inc_mutes, seg_cast)
                graph = build_static(segs, p.characters,
                                     include_mutes=inc_mutes,
                                     segment_cast=seg_cast)
                yield Config(
                    label=f"{p.play_id}/{spine}/{model}{'+agg' if agg else ''}",
                    play=p, segments=segs, kept=kept, graph=graph,
                    metrics=compute_metrics(graph), speech=speech)


# ---------------------------------------------------------------------------
# The properties
# ---------------------------------------------------------------------------

def every_speech_sits_in_exactly_one_segment(c: Config) -> None:
    placed = [sp for s in c.segments for sp in s.speeches]
    assert len(placed) == len(c.play.speeches), c.label
    assert len({id(sp) for sp in placed}) == len(placed), c.label


def segment_word_counts_are_attributed_sums(c: Config) -> None:
    for s in c.segments:
        assert s.word_count == sum(sp.attributed_words for sp in s.speeches), \
            f"{c.label} seg {s.id}"


def segment_totals_reconcile_with_the_play_total(c: Config) -> None:
    assert sum(s.word_count for s in c.segments) \
        == c.speech["total_words_spoken"], c.label


def casts_name_only_declared_characters(c: Config) -> None:
    declared = set(c.play.characters)
    for s in c.segments:
        assert s.characters_present <= declared, f"{c.label} seg {s.id}"
        assert s.speakers <= declared, f"{c.label} seg {s.id}"


def graph_nodes_are_the_models_kept_cast(c: Config) -> None:
    assert set(c.graph.nodes()) == c.kept, c.label


def edge_bookkeeping_is_self_consistent(c: Config) -> None:
    by_id = {s.id: s for s in c.segments}
    for u, v, d in c.graph.edges(data=True):
        assert u != v, f"{c.label}: self-loop on {u}"
        assert d["weight"] >= 1, f"{c.label} {u}-{v}"
        assert d["segments_shared"] == len(d["segment_ids"]), f"{c.label} {u}-{v}"
        assert d["segments_shared"] <= len(c.segments), f"{c.label} {u}-{v}"
        assert d["words_shared"] == sum(by_id[i].word_count
                                        for i in d["segment_ids"]), \
            f"{c.label} {u}-{v}"


def metrics_are_derivable_from_the_graph(c: Config) -> None:
    m, G = c.metrics, c.graph
    n, e = m["size"], m["numEdges"]
    assert (n, e) == (G.number_of_nodes(), G.number_of_edges()), c.label
    if n > 1:
        assert m["density"] == pytest.approx(2 * e / (n * (n - 1))), c.label
    if n > 0:
        assert m["averageDegree"] == pytest.approx(2 * e / n), c.label
    degrees = dict(G.degree())
    if degrees:
        top = max(degrees.values())
        assert m["maxDegree"] == top, c.label
        assert set(m["maxDegreeIds"]) == {i for i, d in degrees.items()
                                          if d == top}, c.label
    assert [x["id"] for x in m["nodes"]] == sorted(G.nodes()), c.label
    for x in m["nodes"]:
        assert x["degree"] == degrees.get(x["id"], 0), f"{c.label} {x['id']}"


def centralities_stay_in_range(c: Config) -> None:
    for x in c.metrics["nodes"]:
        for field in ("betweenness", "closeness", "eigenvector"):
            assert 0.0 <= x[field] <= 1.0, \
                f"{c.label} {x['id']} {field}={x[field]}"


def an_edgeless_graph_has_no_distances(c: Config) -> None:
    if c.metrics["numEdges"] == 0:
        assert c.metrics["diameter"] == 0, c.label
        assert c.metrics["averagePathLength"] == 0.0, c.label


def the_path_length_identity_holds_where_the_panel_claims_it(c: Config) -> None:
    """Section 1 states <d> = 2 - d' wherever D <= 2 and |V'| >= 2.

    Both bounds matter: d' is the largest component's density and not the
    panel's, which is the whole graph's, and a single-vertex component has no
    distance to average -- the app gives it 0 where 2 - d' would give 2.
    """
    m = c.metrics
    if m["numEdges"] == 0 or m["diameter"] > 2:
        return
    nodes = max(nx.connected_components(c.graph), key=len)
    if len(nodes) < 2:
        return
    d_prime = nx.density(c.graph.subgraph(nodes))
    assert m["averagePathLength"] == pytest.approx(2 - d_prime), c.label


PROPERTIES = [
    every_speech_sits_in_exactly_one_segment,
    segment_word_counts_are_attributed_sums,
    segment_totals_reconcile_with_the_play_total,
    casts_name_only_declared_characters,
    graph_nodes_are_the_models_kept_cast,
    edge_bookkeeping_is_self_consistent,
    metrics_are_derivable_from_the_graph,
    centralities_stay_in_range,
    an_edgeless_graph_has_no_distances,
    the_path_length_identity_holds_where_the_panel_claims_it,
]


# ---------------------------------------------------------------------------
# Applied to the demo play, and to the corpus where one is present
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def demo_configs(demo_play) -> List[Config]:
    return list(configurations(demo_play))


@pytest.fixture(scope="module")
def corpus_configs() -> List[Config]:
    if not CORPUS_DIR.is_dir():
        pytest.skip(f"no corpus at {CORPUS_DIR}")
    plays = sorted(CORPUS_DIR.glob("*.xml"))
    if not plays:
        pytest.skip(f"no plays in {CORPUS_DIR}")
    out: List[Config] = []
    for path in plays:
        out.extend(configurations(parse_play(path)))
    return out


def test_every_configuration_is_built(demo_configs):
    """Three spines x three models x two aggregations, or the battery below
    is quietly checking less than it claims."""
    assert len(demo_configs) == 18


@pytest.mark.parametrize("prop", PROPERTIES, ids=lambda p: p.__name__)
def test_property_holds_for_the_demo_play(prop, demo_configs):
    for cfg in demo_configs:
        prop(cfg)


@pytest.mark.slow
@pytest.mark.parametrize("prop", PROPERTIES, ids=lambda p: p.__name__)
def test_property_holds_across_the_corpus(prop, corpus_configs):
    for cfg in corpus_configs:
        prop(cfg)
