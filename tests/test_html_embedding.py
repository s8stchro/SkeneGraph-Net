"""The payload must survive the HTML boundary, and arrive unchanged.

The dashboards write their data into an inline `<script>`. JSON quoting is no
protection there: the HTML parser scans for the literal characters `</script`
before any JavaScript runs, so a closing tag anywhere in the data ends the
element and the rest of the code becomes page text. The data carries the
whole TEI file for the source tab, and a legal XML comment may hold one.

Two things are checked here: that the script element still contains the code
after it, and that the escaping leaves the payload equal as a value.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser

import pytest

from conftest import build_tei, move, sp, stage
from dashboard import _json_for_script

HOSTILE = '<!-- </script><b>x</b> -->'


class InlineScripts(HTMLParser):
    """Every inline script's body, as a browser would see it."""

    def __init__(self):
        super().__init__()
        self.bodies = []
        self._in = False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and not dict(attrs).get("src"):
            self._in = True
            self.bodies.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in = False

    def handle_data(self, data):
        if self._in:
            self.bodies[-1] += data


def main_script(html: str) -> str:
    """The dashboard's own script, found by its DATA assignment -- not as the
    longest one, since the inlined d3 and KaTeX outweigh a small play's."""
    parser = InlineScripts()
    parser.feed(html)
    return next((b for b in parser.bodies if "const DATA =" in b), "")


def payload_of(html: str) -> dict:
    """The DATA object, read back as a browser's JSON.parse would read it."""
    m = re.search(r"const DATA = (.*?);?\n", main_script(html))
    assert m, "no DATA assignment in the main script"
    return json.loads(m.group(1))


# ---------------------------------------------------------------------------
# The serialiser
# ---------------------------------------------------------------------------

def test_the_boundary_characters_never_appear_raw():
    out = _json_for_script({"tei": HOSTILE, "amp": "a & b"})
    for ch in "<>&":
        assert ch not in out


def test_the_value_survives_the_escaping():
    payload = {"tei": HOSTILE, "amp": "a & b", "sep": "one two"}
    assert json.loads(_json_for_script(payload)) == payload


def test_greek_stays_readable():
    """ensure_ascii=False is deliberate: the file is UTF-8 and the names are
    Greek.  The escaping must not undo that."""
    assert "Νεφέλαι" in _json_for_script({"title": "Νεφέλαι"})


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def render(tmp_path, tei: str) -> str:
    """Run one play through the real pipeline and return its dashboard."""
    from app import analyze_one

    src = tmp_path / "hostile.xml"
    src.write_text(tei, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    analyze_one(xml_path=src, seg_modes=["sd"], out_root=out,
                export_model="full", edge_weight="segments",
                make_dashboard=True)
    return next(out.rglob("dashboard.html")).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def hostile_dashboard(tmp_path_factory) -> str:
    body = "\n".join([stage(move("entrance", "a b")), sp("a", "one two"),
                      sp("b", "three")])
    tei = build_tei(["a", "b"], body, title="Hostile")
    # a well-formed XML comment, which lxml parses without complaint
    tei = tei.replace("<text>", HOSTILE + "<text>", 1)
    return render(tmp_path_factory.mktemp("hostile"), tei)


@pytest.mark.slow
def test_a_closing_tag_in_the_tei_does_not_end_the_script(hostile_dashboard):
    """The whole dashboard, not just the data, must stay inside the element."""
    script = main_script(hostile_dashboard)
    for marker in ("const DATA =", "const STATE", "function render"):
        assert marker in script, marker


@pytest.mark.slow
def test_the_tei_source_arrives_intact(hostile_dashboard):
    """Escaped for the boundary, not altered as data: the source tab must
    still show the file as it was written."""
    assert HOSTILE in payload_of(hostile_dashboard)["tei_source"]


def test_the_corpus_dashboard_holds_the_same_boundary(tmp_path):
    """The other writer, with its own template and its own subtitle: a
    protection applied to one generator and not the other is none."""
    from corpus_dashboard import write_corpus_dashboard

    data = {
        "name": "</script> corpus",
        "authors": ['<img src=x onerror="boom">'],
        "plays": [{"id": "p", "title_en": "A </script> play",
                   "dashboard_href": "p/dashboard.html",
                   "composition": {}, "segmentations": {}}],
    }
    out = write_corpus_dashboard(data, tmp_path / "corpus_dashboard.html")
    html = out.read_text(encoding="utf-8")

    script = main_script(html)
    for marker in ("const DATA =", "function drawScatter", "_playKey"):
        assert marker in script, marker
    assert payload_of(html) == data
    sub = re.search(r'<div class="sub">(.*?)</div>', html, re.S).group(1)
    assert "<img src=x" not in sub
    assert "&lt;img src=x" in sub


@pytest.mark.slow
def test_metadata_is_escaped_in_the_subtitle(tmp_path):
    """The subtitle prints the author and the Greek title, both of them TEI
    header text, beside separators of our own that must stay markup."""
    body = stage(move("entrance", "a")) + "\n" + sp("a", "one")
    tei = build_tei(["a"], body, title="Hostile",
                    authors='<author>&lt;img src=x onerror="boom"&gt;</author>')
    html = render(tmp_path, tei)
    sub = re.search(r'<div class="sub">(.*?)</div>', html, re.S).group(1)
    assert "<img src=x" not in sub
    assert "&lt;img src=x" in sub
    assert "&middot;" in sub          # our own separator, still markup
