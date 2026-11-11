"""The hand-written dynamic GEXF must be XML, not nearly-XML.

`write_dynamic_gexf` builds its markup by hand -- NetworkX's writer emits no
`<spells>`, which is the whole point of the file -- and every value it writes
lands inside a double-quoted attribute. `saxutils.escape` is for character
data and leaves the quotation mark alone, so a name like `A "quoted" role`
closed the attribute early: the export reported success and produced a file
no parser would read.

These check both directions: the file parses, and the value comes back as it
went in.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import networkx as nx
import pytest

from exporter import write_dynamic_gexf

GEXF = "{http://gexf.net/1.3}"

HOSTILE = [
    'A "quoted" role',
    "Men's Chorus",                 # legal unescaped; the corpus is full of it
    "Both ' and \" at once",
    "angle < brackets > & ampersand",
    "Μαθητής α'",
]


@pytest.fixture()
def written(tmp_path):
    def _write(name: str, node_id: str = "n1") -> ET.Element:
        G = nx.Graph()
        G.add_node(node_id, name=name, name_grc=name, is_mute=False,
                   is_collective=False, is_chorus=False, sex="male",
                   spells=[(0, 1)])
        G.add_node("other", name="Other", spells=[(0, 1)])
        G.add_edge(node_id, "other", weight=2, spells=[(0, 1)])
        path = tmp_path / "dynamic.gexf"
        write_dynamic_gexf(G, path)
        return ET.parse(path).getroot()          # raises if it is not XML
    return _write


@pytest.mark.parametrize("name", HOSTILE)
def test_the_file_parses_and_the_label_survives(written, name):
    root = written(name)
    node = root.find(f".//{GEXF}node")
    assert node.get("label") == name


@pytest.mark.parametrize("name", HOSTILE)
def test_the_attribute_value_survives_too(written, name):
    """The same text is written a second time, as an attvalue."""
    root = written(name)
    values = [v.get("value") for v in root.iter(f"{GEXF}attvalue")]
    assert name in values


def test_an_id_with_a_quote_keeps_its_edge(written):
    """Ids reach four attributes: the node's, and both ends of the edge."""
    root = written("plain", node_id='odd"id')
    assert root.find(f".//{GEXF}node").get("id") == 'odd"id'
    edge = root.find(f".//{GEXF}edge")
    assert {edge.get("source"), edge.get("target")} == {'odd"id', "other"}


def test_an_apostrophe_is_left_alone(tmp_path):
    """Legal inside a double-quoted attribute, and escaping it would churn
    every name in the corpus that has one."""
    G = nx.Graph()
    G.add_node("n1", name="Men's Chorus", spells=[(0, 1)])
    path = tmp_path / "dynamic.gexf"
    write_dynamic_gexf(G, path)
    text = path.read_text(encoding="utf-8")
    assert "Men's Chorus" in text
    assert "&apos;" not in text
