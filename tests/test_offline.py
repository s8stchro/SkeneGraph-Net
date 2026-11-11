"""A dashboard must work with no network.

The pages once fetched d3 and KaTeX from CDNs; opened offline they showed
their frame and nothing else, since the first d3 call throws and no chart is
drawn.  Nothing in the output looked wrong, so nothing caught it.  The
libraries are now inlined from `vendor/`; these tests keep every resource
the page loads inside the file.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

import vendor_assets
from conftest import build_tei, move, sp, stage
from vendor_assets import vendor_assets_html


class Resources(HTMLParser):
    """Every URL the page itself loads: script sources and stylesheets.
    Plain links (<a href>) are the reader's to follow and are left out."""

    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("src"):
            self.urls.append(a["src"])
        if tag == "link" and a.get("href"):
            self.urls.append(a["href"])


def assert_self_contained(html: str) -> None:
    parser = Resources()
    parser.feed(html)
    assert parser.urls == [], parser.urls
    # a stylesheet can fetch too: KaTeX's fonts were relative URLs.  The
    # charts' `url(#hatch)` fills point into the page and are fine.
    targets = re.findall(r"""url\(\s*["']?([^"')]*)""", html)
    outside = [t[:40] for t in targets if not t.startswith(("data:", "#"))]
    assert outside == [], outside
    assert "d3js.org v7.9.0" in html
    assert "renderMathInElement" in html


def test_the_assets_carry_every_katex_font_inline():
    html = vendor_assets_html()
    faces = re.findall(r"@font-face\{[^}]*\}", html)
    assert len(faces) == 20
    for face in faces:
        assert "url(data:font/woff2;base64," in face, face[:80]
        assert "fonts/" not in face, face[:80]


def test_a_library_that_would_end_its_script_is_refused(tmp_path, monkeypatch):
    (tmp_path / "evil.js").write_text('var s = "</script>";', encoding="utf-8")
    monkeypatch.setattr(vendor_assets, "VENDOR_DIR", tmp_path)
    with pytest.raises(ValueError, match="</script"):
        vendor_assets._script("evil.js")


def test_the_corpus_dashboard_loads_nothing_from_outside(tmp_path):
    from corpus_dashboard import write_corpus_dashboard

    data = {"name": "c", "authors": [], "plays": [
        {"id": "p", "title_en": "P", "dashboard_href": "p/dashboard.html",
         "composition": {}, "segmentations": {}}]}
    out = write_corpus_dashboard(data, tmp_path / "corpus_dashboard.html")
    assert_self_contained(out.read_text(encoding="utf-8"))


@pytest.mark.slow
def test_the_play_dashboard_loads_nothing_from_outside(tmp_path):
    from app import analyze_one

    body = "\n".join([stage(move("entrance", "a b")), sp("a", "one two"),
                      sp("b", "three")])
    src = tmp_path / "play.xml"
    src.write_text(build_tei(["a", "b"], body, title="Offline"), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    analyze_one(xml_path=src, seg_modes=["sd"], out_root=out,
                export_model="full", edge_weight="segments",
                make_dashboard=True)
    assert_self_contained(
        next(out.rglob("dashboard.html")).read_text(encoding="utf-8"))
