"""Export graphs and metrics to disk in DraCor-compatible formats.

For each segmentation a separate sub-directory is produced::

    output/<title>/<segmentation>/
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
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
from xml.sax.saxutils import escape as xml_escape

import networkx as nx

from parser import Character, PlayData
from segmentation import Segment


log = logging.getLogger("SkeneGraph-Net.exporter")

SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

# Written into every play directory, naming the file the directory was built
# from.  It is what lets a later run tell its own output apart from another
# play's; see allocate_play_dir.
PROVENANCE_FILE = "source.json"


def _safe_dirname(s: str) -> str:
    s = SAFE_FILENAME_RE.sub("_", s.strip())
    return s.strip("._-") or "play"


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _recorded_source(play_dir: Path) -> Optional[str]:
    """The source file a play directory already holds output for.

    `None` where nothing is recorded: an empty slot, or a directory written
    before this marker existed, neither of which can be told from a re-run
    and so are not treated as collisions.
    """
    try:
        data = json.loads(
            (play_dir / PROVENANCE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    source = data.get("source")
    return source if isinstance(source, str) else None


def allocate_play_dir(out_root: Path, name: str, xml_path: Path,
                      claimed: Optional[Dict[str, str]] = None,
                      play_id: str = "") -> Path:
    """Give one play a directory that belongs to no other play.

    `name` is what the directory is called -- the play's English title, so the
    output tree reads as a list of plays -- and `play_id`, the play's unique
    identifier, is recorded in the marker beside the source file's name.

    Directories are named for the play, as they always have been.  But the
    name is a sanitised title, and distinct titles can sanitise alike --
    `Electra?` and `Electra!` both yield `Electra` -- as can two plays of the
    same name by different authors.  Whichever ran second used to overwrite
    the first's dashboard, CSVs and graph exports while both summaries went
    on pointing at the one surviving directory.

    A name held by a different source is therefore refused, and the source's
    own file name disambiguates it.  Re-running the same source is not a
    collision: it reuses its directory and overwrites its own output, which
    is the point of a re-run.

    Two sources are told apart by path within a run, through `claimed`, which
    maps each directory taken to the source that took it; and by file name
    across runs, through the marker file, which records the name alone.  A
    corpus moved to another folder therefore still re-runs into its own
    directories rather than beside them -- at the price of one gap: two plays
    of the same title in identically named files, analysed in separate runs
    into one output root, still look to the second run like a re-run of the
    first.  In a single run they collide and are caught.
    """
    source = xml_path.name
    key = str(xml_path.resolve())
    base = _safe_dirname(name or xml_path.stem)
    fallback = _safe_dirname(f"{base}-{xml_path.stem}")

    def holder(dirname: str) -> Optional[str]:
        """Who holds this directory, if anybody but us."""
        if claimed is not None and dirname in claimed:
            return None if claimed[dirname] == key else claimed[dirname]
        recorded = _recorded_source(out_root / dirname)
        return None if recorded in (None, source) else recorded

    for candidate in (base, fallback):
        if holder(candidate) is not None:
            continue
        play_dir = _ensure_dir(out_root / candidate)
        (play_dir / PROVENANCE_FILE).write_text(
            json.dumps({"source": source, "play_id": play_id or name},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        if claimed is not None:
            claimed[candidate] = key
        if candidate != base:
            log.warning(
                "%s wanted the directory %r, which holds %s; its output goes "
                "to %r instead", source, base, holder(base), candidate)
        return play_dir

    raise ValueError(
        f"{key} wants the output directory {fallback!r}, which holds "
        f"{holder(fallback)}: the two cannot be told apart by title or by "
        f"file name.  Rename one of them, or write them to separate --out "
        f"directories")


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
        # Local clustering and the triangles it counts: position measures
        # like the centralities above, and the pair a broker is read from.
        "clustering", "triangles",
        # Speech-time measures (per-character temporal Gini block).
        # Conceptually distinct from the centralities above: these are
        # properties of when a character's words fall along the
        # play's segment axis, not properties of their position in the
        # co-presence graph.  Kept on the same row for export
        # convenience; the dashboard separates them into their own
        # panel inside Plot Dynamics.
        "total_words", "speaking_segments", "n_onstage_segments",
        "temporal_gini",
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
                "clustering":  m.get("clustering", ""),
                "triangles":   m.get("triangles", ""),
                "total_words":        m.get("total_words", ""),
                "speaking_segments":  m.get("speaking_segments", ""),
                "n_onstage_segments": m.get("n_onstage_segments", ""),
                "temporal_gini":      m.get("temporal_gini", ""),
            })


def write_segments_csv(segments: List[Segment], path: Path,
                       nodes=None, segment_cast: str = "stage") -> None:
    """One row per segment.

    `characters` is who stands on stage, whatever the model.  `model_cast`
    is who the exported model puts in the segment -- the stage cast or the
    speakers, as `segment_cast` says, within the graph's node set `nodes` --
    so that a row rebuilds the segment's clique and agrees with `size` in
    dynamic_metrics.csv.  Under the two speaking models the stage cast alone
    showed silent and mute bystanders the exported graph never joined.
    """
    columns = [
        "segment_id", "label",
        "large_seq_id", "large_seq_type", "middle_seq_id",
        "is_initial", "is_final",
        "num_characters", "characters",
        "num_speeches", "word_count", "num_crossings",
        "speakers", "model_cast_size", "model_cast",
    ]
    node_set = set(nodes) if nodes is not None else None
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for s in segments:
            cast = s.speakers if segment_cast == "speaking" else s.characters_present
            if node_set is not None:
                cast = cast & node_set
            w.writerow({
                "segment_id": s.id,
                "label": s.label,
                "large_seq_id": s.large_seq_id or "",
                "large_seq_type": s.large_seq_type or "",
                "middle_seq_id": s.middle_seq_id or "",
                "is_initial": s.is_initial,
                "is_final": s.is_final,
                "num_characters": len(s.characters_present),
                "characters": "|".join(sorted(s.characters_present)),
                # Every <sp>, including a lost choral interlude: the speech
                # happened even where its text does not survive.  word_count
                # stays the measure of how much text there is.
                "num_speeches": len(s.speeches),
                "word_count": s.word_count,
                # Figures who appeared and were gone inside the segment
                # without joining its cast -- stage traffic that is
                # deliberately absent from the graph.
                "num_crossings": s.num_crossings,
                "speakers": "|".join(sorted(s.speakers)),
                "model_cast_size": len(cast),
                "model_cast": "|".join(sorted(cast)),
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

def _attr(v) -> str:
    """Escape one value for an XML attribute in the hand-written GEXF.

    `saxutils.escape` is for character data and leaves the quotation mark
    alone, so a character named `A "quoted" role` closed the attribute early
    and produced a file no XML parser would read -- while the export itself
    reported success.  Every attribute below is written inside double quotes,
    so the double quote is escaped and the apostrophe is not: it is legal
    there, and the corpus is full of it (`Men's Chorus`, `Μαθητής α'`).

    One helper for every attribute in this writer, ids and labels and values
    alike: an escape that has to be remembered at each call site is an escape
    that will be forgotten at one of them.
    """
    if isinstance(v, bool):
        return "true" if v else "false"
    return xml_escape(str(v), {'"': "&quot;"})


def _attr_def(idx: int, name: str, type_: str) -> str:
    return f'      <attribute id="{idx}" title="{_attr(name)}" type="{type_}"/>'


def _spell_lines(spells) -> List[str]:
    """One `<spell timestamp>` per segment an element is active in.

    The graph's `spells` are half-open segment runs, [s, e).  GEXF 1.3 has no
    open bound, and Gephi reads an interval as closed, so a run written as
    start=s end=e also claimed segment e: at every integer time the outgoing
    and the incoming cast stood together.  A segment is a step in an ordinal
    sequence, not a stretch of time, so it is written as one -- a timestamp,
    under the graph's `timerepresentation="timestamp"`.
    """
    if not spells:
        return []
    out = ['        <spells>']
    for s, e in spells:
        out.extend(f'          <spell timestamp="{k}"/>' for k in range(s, e))
    out.append('        </spells>')
    return out


def write_dynamic_gexf(G: nx.Graph, path: Path) -> None:
    """Emit a GEXF 1.3 dynamic graph with <spells> on nodes and edges.

    Time is the segment number, one timestamp per segment.  Elements carry no
    start/end of their own: a span from first to last appearance says nothing
    the spells do not, and a reader that honours it over the spells sees the
    character present through every gap.
    """
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
    lines.append('  <graph defaultedgetype="undirected" mode="dynamic" '
                 'timeformat="double" timerepresentation="timestamp">')

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
        lines.append(
            f'      <node id="{_attr(nid)}" '
            f'label="{_attr(data.get("name", nid))}">'
        )
        lines.append('        <attvalues>')
        for i, k in enumerate(node_attr_keys):
            v = data.get(k, "")
            lines.append(f'          <attvalue for="{i}" value="{_attr(v)}"/>')
        lines.append('        </attvalues>')
        lines.extend(_spell_lines(data.get("spells")))
        lines.append('      </node>')
    lines.append('    </nodes>')

    lines.append('    <edges>')
    for eid, (u, v, data) in enumerate(G.edges(data=True)):
        weight = data.get("weight", 1)
        lines.append(
            f'      <edge id="{eid}" source="{_attr(u)}" '
            f'target="{_attr(v)}" weight="{_attr(weight)}">'
        )
        lines.append('        <attvalues>')
        lines.append(f'          <attvalue for="0" value="{_attr(weight)}"/>')
        lines.append('        </attvalues>')
        lines.extend(_spell_lines(data.get("spells")))
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
    write_segments_csv(segments, p, nodes=static_graph.nodes(),
                       segment_cast=metrics.get("segment_cast", "stage"))
    paths["segments.csv"] = str(p)

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
    "allocate_play_dir",
    "PROVENANCE_FILE",
    "_safe_dirname",
]
