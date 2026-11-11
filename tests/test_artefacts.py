"""What the pipeline writes, checked against what it computed.

Every file the app emits names its fields twice -- once in a header or
schema, once where the values are filled in -- and the two halves have drifted
before: a column declared and left empty in every row, a field added to the
node payload and not to the CSV writer.  Nothing caught either, because a
reader of the artefact sees a well-formed file.

The JavaScript half of the app is checked the same way.  Several of its
numbers exist nowhere else -- the heatmap's threshold-passage count, the beat
chart's word-position axis -- so they are re-derived here from the payload the
page is handed and tested as properties.
"""

from __future__ import annotations

import csv
import json
from xml.etree import ElementTree as ET

import pytest


@pytest.fixture(scope="module")
def artefacts(demo_path, tmp_path_factory):
    """One real run: all three spines, dashboards included."""
    from app import analyze_one

    out = tmp_path_factory.mktemp("artefacts")
    summary = analyze_one(
        xml_path=demo_path,
        seg_modes=["sd", "large-seq", "middle-seq"],
        out_root=out,
        export_model="full",
        edge_weight="segments",
        make_dashboard=True,
    )
    assert summary is not None
    return out


@pytest.fixture(scope="module")
def spine_dirs(artefacts):
    dirs = sorted(p for p in artefacts.rglob("*")
                  if p.is_dir() and p.name in ("sd", "large-seq", "middle-seq"))
    assert len(dirs) == 3
    return dirs


def _dashboard_data(path):
    text = path.read_text(encoding="utf-8")
    i = text.index("const DATA = ")
    j = text.index("\n", i)
    return json.loads(text[i + len("const DATA = "):j].rstrip().rstrip(";"))


# ---------------------------------------------------------------------------
# The files
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_every_expected_file_is_written(spine_dirs):
    expected = {"metrics.json", "characters.csv", "segments.csv",
                "networkdata.csv", "networkdata.gexf", "networkdata.graphml",
                "dynamic.gexf"}
    for d in spine_dirs:
        assert expected <= {f.name for f in d.iterdir() if f.is_file()}, d.name


@pytest.mark.slow
def test_characters_csv_agrees_with_the_node_list(spine_dirs):
    for d in spine_dirs:
        m = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
        nodes = {n["id"] for n in m["nodes"]}
        with open(d / "characters.csv", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert {r["id"] for r in rows if r["in_network"] == "True"} == nodes, d.name
        ids = [r["id"] for r in rows]
        assert len(set(ids)) == len(ids), f"{d.name}: a character listed twice"


@pytest.mark.slow
def test_no_column_is_declared_and_left_empty(spine_dirs):
    """The defect this file was written for: a field added to the header and
    not to the row, so every value comes out blank."""
    for d in spine_dirs:
        m = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
        nodes = {n["id"] for n in m["nodes"]}
        with open(d / "characters.csv", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            if r["id"] not in nodes:
                continue
            for col in ("degree", "weightedDegree", "betweenness",
                        "closeness", "eigenvector"):
                assert r[col] != "", f"{d.name} {r['id']}: {col} empty"
        speakers = [r for r in rows if r["temporal_gini"]]
        assert speakers, f"{d.name}: nobody carries a temporal Gini"
        for r in speakers:
            for col in ("total_words", "speaking_segments",
                        "n_onstage_segments"):
                assert r[col] != "", f"{d.name} {r['id']}: {col} empty"


@pytest.mark.slow
def test_segments_and_edges_match_the_metrics(spine_dirs):
    for d in spine_dirs:
        m = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
        with open(d / "segments.csv", encoding="utf-8") as fh:
            segs = list(csv.DictReader(fh))
        assert len(segs) == m["num_segments"], d.name
        for r in segs:
            cast = [c for c in (r["characters"] or "").split("|") if c]
            assert len(cast) == int(r["num_characters"]), f"{d.name} {r['segment_id']}"
        with open(d / "networkdata.csv", encoding="utf-8") as fh:
            edges = list(csv.DictReader(fh))
        assert len(edges) == m["numEdges"], d.name
        nodes = {n["id"] for n in m["nodes"]}
        for r in edges:
            assert r["Source"] in nodes and r["Target"] in nodes, d.name


@pytest.mark.slow
@pytest.mark.parametrize("name", ["networkdata.gexf", "networkdata.graphml"])
def test_graph_files_parse_and_carry_the_whole_graph(spine_dirs, name):
    """Greek display names go into hand-rolled XML, so well-formedness is not
    a given."""
    for d in spine_dirs:
        m = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
        root = ET.parse(d / name).getroot()
        ns = {"g": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
        tag = (lambda t: f"g:{t}") if ns else (lambda t: t)
        assert len(root.findall(f".//{tag('node')}", ns)) == m["size"], d.name
        assert len(root.findall(f".//{tag('edge')}", ns)) == m["numEdges"], d.name


def _gexf_presence(path):
    """{(node id, segment)} from a dynamic GEXF's timestamp spells."""
    root = ET.parse(path).getroot()
    ns = {"g": root.tag.split("}")[0].strip("{")}
    graph = root.find("g:graph", ns)
    assert graph.get("timerepresentation") == "timestamp"
    pairs = set()
    for node in graph.iterfind(".//g:node", ns):
        for spell in node.iterfind("g:spells/g:spell", ns):
            pairs.add((node.get("id"), int(float(spell.get("timestamp")))))
    # No element carries a span of its own beside its spells: first-to-last
    # appearance says nothing the spells do not, and read over them it
    # would fill every gap.
    assert not root.findall(".//*[@start]") and not root.findall(".//*[@end]")
    return pairs


def _segments_rows(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.mark.slow
def test_dynamic_gexf_places_each_character_in_exactly_their_segments(spine_dirs):
    """One timestamp per segment a character is in -- no more.  Written as
    closed [k, k+1] intervals, every spell also claimed segment k+1, so the
    outgoing and the incoming cast stood together at each integer time."""
    for d in spine_dirs:
        expected = {(c, int(r["segment_id"]))
                    for r in _segments_rows(d / "segments.csv")
                    for c in r["model_cast"].split("|") if c}
        assert expected, d.name
        assert _gexf_presence(d / "dynamic.gexf") == expected, d.name


@pytest.mark.slow
@pytest.mark.parametrize("model", ["full", "p-speaking", "s-speaking"])
def test_segments_csv_names_the_exported_models_cast(demo_path, tmp_path, model):
    """segments.csv carries the cast the exported model joins, so a row
    rebuilds the segment's clique and agrees with dynamic_metrics.csv.  The
    stage cast alone showed bystanders the speaking models never join."""
    from app import analyze_one

    analyze_one(xml_path=demo_path, seg_modes=["sd"], out_root=tmp_path,
                export_model=model, edge_weight="segments",
                make_dashboard=False)
    d = next(tmp_path.rglob("sd"))
    rows = _segments_rows(d / "segments.csv")
    sizes = {int(r["segment_id"]): int(r["size"])
             for r in _segments_rows(d / "dynamic_metrics.csv")}
    nodes = {n["id"] for n in
             json.loads((d / "metrics.json").read_text(encoding="utf-8"))["nodes"]}
    for r in rows:
        cast = [c for c in r["model_cast"].split("|") if c]
        assert len(cast) == int(r["model_cast_size"]) == sizes[int(r["segment_id"])]
        assert set(cast) <= nodes
        speakers = {c for c in r["speakers"].split("|") if c}
        if model == "s-speaking":
            assert set(cast) == speakers & nodes
    assert _gexf_presence(d / "dynamic.gexf") == {
        (c, int(r["segment_id"])) for r in rows
        for c in r["model_cast"].split("|") if c}


# ---------------------------------------------------------------------------
# The numbers that live only in the browser
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def payload_blocks(artefacts):
    data = _dashboard_data(next(artefacts.rglob("dashboard.html")))
    blocks = []
    for spine, entry in data["segmentations"].items():
        blocks.append((f"{spine}/full", entry))
        for key, variant in sorted((entry.get("variants") or {}).items()):
            blocks.append((f"{spine}/{key}", variant))
    assert blocks
    return blocks


@pytest.mark.slow
def test_threshold_passages_count_whole_visits(payload_blocks):
    """The heatmap's "most stage entrances/exits" order counts a passage at
    every change of presence, padded with an empty stage at both ends -- so
    the count is twice the number of visits, and odd is impossible."""
    for label, blk in payload_blocks:
        chars = [c for c in blk["characters"] if c.get("in_network") is not False]
        passages = {c["id"]: 0 for c in chars}
        appeared, previous = set(), set()
        for s in blk["segments"]:
            present = set(s["characters"])
            appeared |= present
            for c in chars:
                if (c["id"] in present) != (c["id"] in previous):
                    passages[c["id"]] += 1
            previous = present
        for c in chars:
            if c["id"] in previous:
                passages[c["id"]] += 1
        for cid, n in passages.items():
            assert n % 2 == 0, f"{label} {cid}: {n} passages"
            assert (n >= 2) if cid in appeared else (n == 0), f"{label} {cid}"


@pytest.mark.slow
def test_word_position_axis_spans_exactly_the_plays_words(payload_blocks):
    """The beat chart can place segments by word mass instead of by index.
    The axis is the running sum of the segment word counts, so its right edge
    is the play total -- the same total the metrics panel prints."""
    for label, blk in payload_blocks:
        acc, edges = 0, []
        for s in blk["segments"]:
            edges.append(acc)
            acc += s.get("word_count") or 0
        assert edges == sorted(edges), f"{label}: axis not monotonic"
        total = blk["metrics"]["speech_distribution"]["total_words_spoken"]
        assert acc == total, f"{label}: axis {acc} vs panel {total}"
