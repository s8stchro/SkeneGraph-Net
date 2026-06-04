"""Export graphs and metrics to disk in DraCor-compatible formats.

For each segmentation a separate sub-directory is produced::

    output/<play_id>/<segmentation>/
        metrics.json          (DraCor's /metrics schema)
        characters.csv        (one row per character)
        segments.csv          (one row per segment)
        networkdata.csv       (DraCor's edge list: Source,Type,Target,Weight)
        networkdata.gexf      (static graph, Gephi)
        networkdata.graphml   (static graph, Cytoscape / yEd)
        dynamic.gexf          (single time-coded graph with <spells>)

The dynamic GEXF is hand-rolled because NetworkX' default writer does not
emit per-element `<spells>`, which Gephi needs to play back the dynamic
graph on its timeline.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Dict, List
from xml.sax.saxutils import escape as xml_escape

import networkx as nx

from parser import Character, PlayData
from segmentation import Segment


SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_dirname(s: str) -> str:
    s = SAFE_FILENAME_RE.sub("_", s.strip())
    return s.strip("._-") or "play"


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Static graph exports
# ---------------------------------------------------------------------------

def write_networkdata_csv(G: nx.Graph, path: Path) -> None:
    """DraCor-style edge list: Source,Type,Target,Weight."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Source", "Type", "Target", "Weight"])
        for u, v, d in G.edges(data=True):
            w.writerow([u, "Undirected", v, d.get("weight", 1)])


def write_static_gexf(G: nx.Graph, path: Path) -> None:
    G2 = _stringify_attrs(G)
    nx.write_gexf(G2, path, version="1.2draft")


def write_graphml(G: nx.Graph, path: Path) -> None:
    G2 = _stringify_attrs(G)
    nx.write_graphml(G2, path)


def _stringify_attrs(G: nx.Graph) -> nx.Graph:
    """Convert non-scalar attrs (lists/sets) to strings so GEXF/GraphML accept them."""
    H = G.copy()
    for _, data in H.nodes(data=True):
        for k, v in list(data.items()):
            if isinstance(v, (list, set, tuple)):
                data[k] = ",".join(map(str, sorted(v) if isinstance(v, set) else v))
            elif isinstance(v, bool):
                data[k] = bool(v)
    for _, _, data in H.edges(data=True):
        for k, v in list(data.items()):
            if isinstance(v, (list, set, tuple)):
                data[k] = ",".join(map(str, sorted(v) if isinstance(v, set) else v))
    # Drop graph-level non-scalar attrs the writer might choke on.
    for k in list(H.graph.keys()):
        v = H.graph[k]
        if not isinstance(v, (str, int, float, bool)):
            H.graph[k] = str(v)
    return H


# ---------------------------------------------------------------------------
# Character list and segment list
# ---------------------------------------------------------------------------

def write_characters_csv(
    play: PlayData,
    G: nx.Graph,
    metrics: Dict,
    path: Path,
) -> None:
    metrics_by_id = {n["id"]: n for n in metrics.get("nodes", [])}
    columns = [
        "id", "name_english", "name_greek",
        "is_mute", "is_collective", "is_chorus", "sex",
        "in_network",
        "degree", "weightedDegree",
        "betweenness", "closeness", "eigenvector",
        # Speech-time measures (per-character temporal Gini block).
        # Conceptually distinct from the centralities above: these are
        # properties of when a character's verses fall along the
        # play's segment axis, not properties of their position in the
        # co-presence graph.  Kept on the same row for export
        # convenience; the dashboard separates them into their own
        # panel inside Plot Dynamics.
        "total_verses", "speaking_segments", "temporal_gini",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for cid, ch in sorted(play.characters.items()):
            in_net = G.has_node(cid)
            m = metrics_by_id.get(cid, {})
            w.writerow({
                "id": cid,
                "name_english": ch.name_en,
                "name_greek": ch.name_grc,
                "is_mute": ch.is_mute,
                "is_collective": ch.is_collective,
                "is_chorus": ch.is_chorus,
                "sex": ch.sex or "",
                "in_network": in_net,
                "degree": m.get("degree", ""),
                "weightedDegree": m.get("weightedDegree", ""),
                "betweenness": m.get("betweenness", ""),
                "closeness": m.get("closeness", ""),
                "eigenvector": m.get("eigenvector", ""),
                "total_verses":      m.get("total_verses", ""),
                "speaking_segments": m.get("speaking_segments", ""),
                "temporal_gini":     m.get("temporal_gini", ""),
            })


def write_segments_csv(segments: List[Segment], path: Path) -> None:
    columns = [
        "segment_id", "label",
        "div2_n", "div2_type", "div3_id", "div3_n",
        "is_initial", "is_final",
        "num_characters", "characters",
        "num_speeches", "verse_count", "word_count",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for s in segments:
            w.writerow({
                "segment_id": s.id,
                "label": s.label,
                "div2_n": s.div2_n or "",
                "div2_type": s.div2_type or "",
                "div3_id": s.div3_id or "",
                "div3_n": s.div3_n or "",
                "is_initial": s.is_initial,
                "is_final": s.is_final,
                "num_characters": len(s.characters_present),
                "characters": "|".join(sorted(s.characters_present)),
                # Only non-empty speeches count: <sp><l/></sp> placeholders
                # (lost choral interludes, sound-effect cues, etc.) have 0
                # words / 0 verses and add nothing to any other metric.
                "num_speeches": sum(1 for sp in s.speeches if sp.word_count > 0),
                "verse_count": s.verse_count,
                "word_count": s.word_count,
            })


# ---------------------------------------------------------------------------
# Metrics JSON (DraCor-compatible)
# ---------------------------------------------------------------------------

def write_metrics_json(metrics: Dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False, sort_keys=True)


def write_dynamic_metrics_csv(rows: List[Dict], path: Path) -> None:
    if not rows:
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# Dynamic GEXF (with <spells>)
# ---------------------------------------------------------------------------

def _attr_def(idx: int, name: str, type_: str) -> str:
    return f'      <attribute id="{idx}" title="{xml_escape(name)}" type="{type_}"/>'


def _gexf_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return xml_escape(str(v))


def write_dynamic_gexf(G: nx.Graph, path: Path) -> None:
    """Emit a GEXF 1.3 dynamic graph with <spells> on nodes and edges."""
    node_attr_keys = ["name", "name_grc", "is_mute", "is_collective", "is_chorus", "sex"]
    node_attr_types = {
        "name": "string", "name_grc": "string",
        "is_mute": "boolean", "is_collective": "boolean", "is_chorus": "boolean",
        "sex": "string",
    }
    edge_attr_keys = ["weight"]

    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        '<gexf xmlns="http://gexf.net/1.3" version="1.3" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://gexf.net/1.3 http://gexf.net/1.3/gexf.xsd">'
    )
    lines.append('  <meta>')
    lines.append('    <creator>SkeneGraph-Net</creator>')
    lines.append('    <description>Dynamic co-presence graph (segment spells)</description>')
    lines.append('  </meta>')
    lines.append('  <graph defaultedgetype="undirected" mode="dynamic" timeformat="double">')

    lines.append('    <attributes class="node" mode="static">')
    for i, k in enumerate(node_attr_keys):
        lines.append(_attr_def(i, k, node_attr_types[k]))
    lines.append('    </attributes>')

    lines.append('    <attributes class="edge" mode="static">')
    for i, k in enumerate(edge_attr_keys):
        lines.append(_attr_def(i, k, "double"))
    lines.append('    </attributes>')

    lines.append('    <nodes>')
    for nid, data in G.nodes(data=True):
        spells = data.get("spells") or []
        start = data.get("start", spells[0][0] if spells else 0)
        end = data.get("end", spells[-1][1] if spells else 0)
        lines.append(
            f'      <node id="{xml_escape(str(nid))}" '
            f'label="{xml_escape(str(data.get("name", nid)))}" '
            f'start="{start}" end="{end}">'
        )
        lines.append('        <attvalues>')
        for i, k in enumerate(node_attr_keys):
            v = data.get(k, "")
            lines.append(f'          <attvalue for="{i}" value="{_gexf_value(v)}"/>')
        lines.append('        </attvalues>')
        if spells:
            lines.append('        <spells>')
            for s, e in spells:
                lines.append(f'          <spell start="{s}" end="{e}"/>')
            lines.append('        </spells>')
        lines.append('      </node>')
    lines.append('    </nodes>')

    lines.append('    <edges>')
    for eid, (u, v, data) in enumerate(G.edges(data=True)):
        spells = data.get("spells") or []
        start = data.get("start", spells[0][0] if spells else 0)
        end = data.get("end", spells[-1][1] if spells else 0)
        weight = data.get("weight", 1)
        lines.append(
            f'      <edge id="{eid}" source="{xml_escape(str(u))}" '
            f'target="{xml_escape(str(v))}" weight="{weight}" '
            f'start="{start}" end="{end}">'
        )
        lines.append('        <attvalues>')
        lines.append(f'          <attvalue for="0" value="{weight}"/>')
        lines.append('        </attvalues>')
        if spells:
            lines.append('        <spells>')
            for s, e in spells:
                lines.append(f'          <spell start="{s}" end="{e}"/>')
            lines.append('        </spells>')
        lines.append('      </edge>')
    lines.append('    </edges>')

    lines.append('  </graph>')
    lines.append('</gexf>')

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Top-level: write everything for one segmentation
# ---------------------------------------------------------------------------

def write_outputs(
    play: PlayData,
    segments: List[Segment],
    static_graph: nx.Graph,
    dynamic_spell_graph: nx.Graph,
    metrics: Dict,
    dynamic_rows: List[Dict],
    out_dir: Path,
) -> Dict[str, str]:
    _ensure_dir(out_dir)
    paths = {}

    p = out_dir / "metrics.json"
    write_metrics_json(metrics, p);                paths["metrics.json"] = str(p)

    p = out_dir / "characters.csv"
    write_characters_csv(play, static_graph, metrics, p)
    paths["characters.csv"] = str(p)

    p = out_dir / "segments.csv"
    write_segments_csv(segments, p);                paths["segments.csv"] = str(p)

    p = out_dir / "networkdata.csv"
    write_networkdata_csv(static_graph, p);         paths["networkdata.csv"] = str(p)

    p = out_dir / "networkdata.gexf"
    write_static_gexf(static_graph, p);             paths["networkdata.gexf"] = str(p)

    p = out_dir / "networkdata.graphml"
    write_graphml(static_graph, p);                 paths["networkdata.graphml"] = str(p)

    p = out_dir / "dynamic.gexf"
    write_dynamic_gexf(dynamic_spell_graph, p);     paths["dynamic.gexf"] = str(p)

    p = out_dir / "dynamic_metrics.csv"
    write_dynamic_metrics_csv(dynamic_rows, p);     paths["dynamic_metrics.csv"] = str(p)

    return paths


__all__ = [
    "write_outputs",
    "write_networkdata_csv",
    "write_static_gexf",
    "write_graphml",
    "write_dynamic_gexf",
    "write_metrics_json",
    "write_characters_csv",
    "write_segments_csv",
    "_safe_dirname",
]
