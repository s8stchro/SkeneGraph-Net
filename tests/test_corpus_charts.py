"""The corpus dashboard's charts: wiring and the words beside them.

The chart code is JavaScript inside a Python template, so the suite cannot
run it; what it can hold in place is the part a reader acts on -- that each
panel has a chart behind it and a render call that fills it, and that no
hint describes a shape the chart does not draw.  Two hints did, for a whole
release: one named a curve that had never been drawn, the other promised
reference curves after the last one was removed.  The exception is the
label placement, which is plain geometry and is run in node where node is
installed.
"""

from __future__ import annotations

import math
import re

import pytest

from corpus_dashboard import write_corpus_dashboard
from jsrun import needs_node, page_function, run_node

MINIMAL = {
    "name": "test corpus",
    "authors": [],
    "plays": [{"id": "p", "title_en": "A play", "dashboard_href": "p/d.html",
               "composition": {}, "segmentations": {}}],
}


@pytest.fixture(scope="module")
def html(tmp_path_factory) -> str:
    out = tmp_path_factory.mktemp("corpus") / "corpus_dashboard.html"
    write_corpus_dashboard(MINIMAL, out)
    return out.read_text(encoding="utf-8")


def test_every_scatter_panel_has_a_render_call(html):
    """An svg with no drawScatter would sit empty; a call with no svg would
    draw into nothing."""
    panels = set(re.findall(r'<svg id="([a-z-]+-chart)"', html))
    drawn = set(re.findall(r'drawScatter\("#([a-z-]+-chart)"', html))
    assert drawn <= panels, drawn - panels
    # every stylesheet, not the first: the inlined KaTeX one precedes the page's
    css = "".join(re.findall(r"<style>(.*?)</style>", html, re.S))
    for chart in drawn:
        assert f"#{chart}" in css, f"{chart} has no height rule and would collapse"


def test_density_order_can_be_coloured_by_degree_and_is_not_sized(html):
    """One chart, with a switch: the dots' fill carries average degree when
    asked, and every dot keeps one size.  Size was tried and dropped -- an
    honest area ratio of 1.74 reads as 'slightly bigger' -- and a second
    density x order panel beside the first was one chart too many."""
    assert 'id="tone-by-degree"' in html
    assert "toneByDegree: false" in html            # off on load
    assert "sizing-degree-chart" not in html
    assert '.attr("r", dotR)' in html
    assert "Math.sqrt" not in html.split("function drawScatter")[1] \
        .split("function shortTitle")[0]


def test_density_order_opens_as_the_plain_plot(html):
    """Pair-lines and the tone are each a checkbox away; neither is on when
    the page opens."""
    assert 'id="show-pair-lines">' in html            # not `checked`
    assert "showPairLines: false" in html
    assert 'id="tone-by-degree">' in html
    assert "toneByDegree: false" in html


def test_the_tone_scale_is_fixed_not_fitted_to_the_view(html):
    """A domain fitted to the active view would stretch any spread, however
    small, across the whole ramp and dress an ordinary play as an outlier.
    The tone runs over a frame derived from the corpus-wide anchor."""
    assert "domain: [DEGREE_ANCHOR / 4, DEGREE_ANCHOR * 2]" in html
    assert "d3.extent" not in html.split("const toneFor")[1].split(";")[0]


def test_the_tone_is_reversed_viridis_darker_for_more(html):
    """A single blue left the plays near the median hard to tell apart:
    CIEDE2000 9.5 between the lowest and highest of the ten comedies below
    Lysistrata.  Reversed viridis shows 20.6 over the same fixed domain, and
    of the scales measured changes at the most even rate."""
    body = html.split("function drawScatter")[1].split("\nfunction ")[0]
    assert "d3.interpolateViridis(0.9 * (1 - t))" in body
    assert "interpolateBlues" not in body


def test_the_tone_legend_is_a_continuous_bar_not_classes(html):
    """Three dots toned for 4, 8 and 16 read as three classes of play; the
    tone runs continuously, so its legend is a bar over the whole frame,
    marked at the two ends and at the anchor."""
    body = html.split("function drawScatter")[1].split("\nfunction ")[0]
    legend = body.split("let legendBox = null;")[1].split("legendBox = boxOf")[0]
    assert 'append("linearGradient")' in legend
    assert 'append("circle")' not in legend
    assert "legend: [DEGREE_ANCHOR / 4, DEGREE_ANCHOR, DEGREE_ANCHOR * 2]" in html


def test_a_play_is_highlighted_not_recoloured(html):
    """A chip marks a play with one highlight, not a colour from a palette:
    a colour code the reader invents has no legend and says nothing in an
    exported figure.  The highlight is a ring, so it survives a toned fill,
    and the dots' fill is never the reader's to set."""
    assert "PLAY_COLOR_PALETTE" not in html and "playColor" not in html
    assert "highlight-rings" in html
    assert '.attr("fill",   d => toneFor ? toneFor(tone.value(segOf(d.p))) : "var(--accent)")' in html
    assert 'id="clear-highlights"' in html


def test_a_highlighted_play_is_labelled_even_in_a_crowded_chart(html):
    """Above twenty plays the scatters drop their labels; the highlight is
    then the one way, short of hovering, to find a play, so its label stays."""
    assert "const labelled = ps.length <= 20 ? ps : hl;" in html


def test_every_scatter_label_goes_through_the_placement(html):
    """Every label is measured and placed, every dot is kept clear by the
    gap a label leaves at its own, and the tone legend counts as text."""
    body = html.split("function drawScatter")[1].split("\nfunction ")[0]
    assert "placeLabels(items, keepOff," in body
    assert 'labs.attr("x", (_, i) => spots[i].x)' in body
    assert "r = reach(d) + clear;" in body
    assert "legendBox ? [legendBox] : []" in body


# The placement is plain geometry, so unlike the rest of the chart code it
# can be run: cut out of the page and handed to node, where node is present
# (see `jsrun`).
LABEL = {"w": 20.0, "a": 9.0, "dsc": 3.0}      # a four-letter label at 10 px
BOUNDS = {"x0": 0, "y0": 0, "x1": 400, "y1": 300}
# A dot, the outer edge of a highlight's ring round it, and a label's gap;
# where the page sets a label's start, right of a dot and of a ring.
R, RING, GAP = 5, 9.5, 2
DX, DX_RING = 7, 11


def _place(html: str, case: dict) -> list[dict]:
    return run_node(
        page_function(html, "placeLabels")
        + "\nconst c = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        + "\nprocess.stdout.write(JSON.stringify("
        + "placeLabels(c.items, c.keepOff, c.bounds, c.taken)));",
        case)


def _case(dots, labelled=None, first=(), bounds=BOUNDS) -> dict:
    """Dots at the given centres, the ones in `first` highlighted, each
    with a label set right of it as the page sets one (or only the dots in
    `labelled`), and every dot kept clear by a label's gap, as the scatters
    keep them."""
    labelled = range(len(dots)) if labelled is None else labelled
    marks = [RING if i in first else R for i in range(len(dots))]
    items = [dict(cx=dots[i][0], cy=dots[i][1], r=marks[i], gap=GAP,
                  dx=DX_RING if i in first else DX, dy=3,
                  dot=i, first=i in first, **LABEL) for i in labelled]
    keep_off = [dict(x0=x - m - GAP, y0=y - m - GAP,
                     x1=x + m + GAP, y1=y + m + GAP)
                for (x, y), m in zip(dots, marks)]
    return {"items": items, "keepOff": keep_off, "bounds": bounds,
            "dots": dots, "marks": marks}


def _overlap(a: dict, b: dict) -> float:
    return (max(0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]))
            * max(0, min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])))


def _conflicts(case: dict, spots: list[dict]) -> list[str]:
    """Everything wrong with a placement: a label on another label or off
    the plot, or on another play's dot or nearer it than to its own."""
    boxes = [{"x0": s["x"], "y0": s["y"] - it["a"],
              "x1": s["x"] + it["w"], "y1": s["y"] + it["dsc"]}
             for it, s in zip(case["items"], spots)]
    found = []
    for i, (it, box) in enumerate(zip(case["items"], boxes)):
        found += [f"label {i} on label {j}" for j in range(i)
                  if _overlap(box, boxes[j]) >= 0.5]
        if _overlap(box, case["bounds"]) < it["w"] * (it["a"] + it["dsc"]) - 0.5:
            found.append(f"label {i} off the plot")
        # How far the label stands from each dot's mark, ring included.
        edge = [math.dist((min(max(x, box["x0"]), box["x1"]),
                           min(max(y, box["y0"]), box["y1"])), (x, y)) - m
                for (x, y), m in zip(case["dots"], case["marks"])]
        found += [f"label {i} nearer dot {j} than its own"
                  for j, e in enumerate(edge)
                  if j != it["dot"] and e < edge[it["dot"]] - 1e-9]
    return found


@needs_node
def test_two_labels_in_each_others_way_are_moved_apart(html):
    """Clouds and Wasps stand 2.5 px apart on effective speakers x average
    degree, and both labels were set right of the dots, one on the other."""
    case = _case([(100, 100), (101, 102.5)])
    spots = _place(html, case)
    assert spots != [{"x": 107, "y": 103}, {"x": 108, "y": 105.5}]
    assert not _conflicts(case, spots)


@needs_node
def test_no_label_sits_nearer_another_play_than_its_own(html):
    """Density x order on large sequences, stage co-presence, aggregated:
    Wasps with Peace 8 px to its right and Frogs 20 px below.  A pass that
    kept labels off the dots and no further set 'Vesp.' below right of its
    dot, 2 px from it and 0.4 px from Frogs, where it named the wrong play."""
    case = _case([(185, 201), (193, 201), (185, 221)])
    spots = _place(html, case)
    assert not _conflicts(case, spots)


@needs_node
def test_a_label_with_nothing_in_its_way_stays_where_it_was(html):
    dots = [(50, 50), (200, 150), (300, 250)]
    assert _place(html, _case(dots)) == [{"x": x + 7, "y": y + 3} for x, y in dots]


@needs_node
def test_a_label_moves_off_another_plays_dot_and_back_inside_the_plot(html):
    """The first label would cover the second play's dot, which has no
    label of its own; the third would run past the plot's right edge."""
    case = _case([(100, 100), (115, 100), (390, 200)], labelled=[0, 2])
    spots = _place(html, case)
    assert spots[0] != {"x": 107, "y": 103}
    assert spots[1] != {"x": 397, "y": 203}
    assert not _conflicts(case, spots)


@needs_node
def test_a_highlighted_label_is_placed_first(html):
    """Two labels in each other's way and in nothing else's: the one placed
    first keeps its spot, and a highlighted play's is placed first.  (The
    ring is left out here: its wider margin would move the other label
    whatever the order.)"""
    case = _case([(100, 100), (100, 108)])
    case["items"][1]["first"] = True
    spots = _place(html, case)
    assert spots[1] == {"x": 107, "y": 111}
    assert spots[0] != {"x": 107, "y": 103}
    assert not _conflicts(case, spots)


@needs_node
def test_a_label_clears_a_highlighted_plays_ring(html):
    """A highlight's ring is part of the play's mark, and a label keeps the
    same gap from it as from a dot.  Here the label would clear the plain
    dot 13 px below, but not the ring round it."""
    case = _case([(100, 100), (100, 113)], labelled=[0], first={1})
    spots = _place(html, case)
    assert spots[0] != {"x": 107, "y": 103}
    assert not _conflicts(case, spots)


@needs_node
def test_with_no_free_spot_a_label_keeps_off_text_first(html):
    """Text on text cannot be read; a label near another play's dot can.
    So where no spot is free, a label takes one that covers no text, if
    any does, however much of a dot's margin it then covers.  Here the
    right spot lies on a label, above right catches 4.7 px2 of another, and
    every other spot lies on a wide margin to keep off."""
    item = dict(cx=100, cy=100, r=R, gap=GAP, dx=DX, dy=3, dot=0,
                first=False, **LABEL)
    taken = [{"x0": 106, "y0": 95.5, "x1": 140, "y1": 107},
             {"x0": 120, "y0": 80, "x1": 130, "y1": 84}]
    keep_off = [{"x0": 93, "y0": 93, "x1": 107, "y1": 107},
                {"x0": 70, "y0": 70, "x1": 104, "y1": 130}]
    [spot] = _place(html, {"items": [item], "keepOff": keep_off,
                           "bounds": BOUNDS, "taken": taken})
    box = {"x0": spot["x"], "y0": spot["y"] - LABEL["a"],
           "x1": spot["x"] + LABEL["w"], "y1": spot["y"] + LABEL["dsc"]}
    assert all(_overlap(box, t) < 0.5 for t in taken), spot


@needs_node
def test_a_crowd_with_no_free_spot_still_places_every_label(html):
    """Twelve labels round one point, and eight spots: the last labels
    take the spot they overlap least, and nothing fails."""
    case = _case([(100, 100)] * 12)
    spots = _place(html, case)
    assert len(spots) == 12
    assert all(math.isfinite(s["x"]) and math.isfinite(s["y"]) for s in spots)
    assert spots[0] == {"x": 107, "y": 103}


def test_an_exported_scatter_names_its_highlighted_plays(html):
    assert '"highlighted: " + marked.join(", ")' in html


def test_an_exported_figure_says_when_colour_is_data(html):
    """Coloured by average degree, the fill is a quantity; a figure taken
    from the chart must carry that in its caption."""
    assert '"dots coloured by average degree"' in html


def test_the_reference_is_always_the_plays_on_screen(html):
    """There is one set of plays, not two.  A second, 'anchor' set once let a
    play be shown without counting towards the medians; a median ignores an
    outlier by itself, so it moved a crosshair by at most a few per cent of
    an axis, and its documented effect on the KPI ranges was never wired."""
    assert "anchorPlays" not in html
    assert "display-only" not in html
    assert "const medX = median(ps.map" in html


def test_no_scatter_redraws_another(html):
    """Density x average degree is fixed by order and average degree
    (d = k / (n - 1)), so it redrew the two order charts from a third angle;
    top-speaker share x Gini summarised one word distribution twice (rank
    correlation +0.70 across the comedies).  Both were removed."""
    assert "topology-chart" not in html
    assert "share-gini-chart" not in html


def test_one_speech_measure_stands_against_average_degree(html):
    """Gini x average degree and top-speaker share x average degree drew one
    word distribution against the same axis twice.  One chart replaces them,
    with effective speakers: it reads the whole distribution, where the
    share reads one character, and unlike the Gini it does not track order,
    which two other charts already plot."""
    assert "gini-avgdeg-chart" not in html
    assert "share-avgdeg-chart" not in html
    assert re.search(r'drawScatter\("#esp-avgdeg-chart",\s*'
                     r's => \(s\.speech_distribution \|\| \{\}\)'
                     r'\.effective_speakers \|\| 0,\s*'
                     r's => s\.averageDegree,', html)


@pytest.mark.slow
def test_a_choral_song_without_transmitted_text_is_speech_not_silence(tmp_path):
    """The XOPOY interludes are <sp who="#choros"> with the text not
    transmitted.  Everywhere else the app counts such a speech as speech;
    the chorus chart and the heatmap drew it as silence.  Its cells must
    carry the <sp> as well as the words, so the chart can tell the two
    apart."""
    from app import analyze_one
    from conftest import APP_DIR

    plutus = APP_DIR.parent / "01-SkeneGraph-corpus" / "comedy" / "Ar-11-Plutus.xml"
    if not plutus.exists():
        pytest.skip(f"no corpus at {plutus.parent}")
    summary = analyze_one(xml_path=plutus, seg_modes=["sd"], out_root=tmp_path,
                          export_model="full", edge_weight="segments",
                          make_dashboard=False)
    rows = summary["segmentations"]["sd"]["chorus_data"]["full_raw"]
    choros = next(r for r in rows if r["id"] == "choros")
    without_text = [i for i, (w, s) in enumerate(zip(choros["words"],
                                                     choros["speaks"]))
                    if s and w == 0]
    assert without_text, "Wealth's interludes should show as performed"
    # words imply an <sp>, never the reverse
    assert all(s for w, s in zip(choros["words"], choros["speaks"]) if w > 0)


def test_both_charts_draw_the_fourth_state(html):
    """The corpus chorus chart and the per-play heatmap agree."""
    from dashboard import _TEMPLATE
    assert '"performs, text not transmitted"' in html
    assert 'url(#" + hatchId + ")' in html
    assert '"performs, text not transmitted"' in _TEMPLATE


def test_no_hint_names_a_shape_that_is_not_drawn(html):
    hints = " ".join(re.findall(r'<span class="hint">(.*?)</span>', html,
                                re.S))
    assert "the curve = order" not in hints
    assert "reference curves" not in hints
