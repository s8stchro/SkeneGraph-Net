"""End-to-end: exported artefacts and the command-line entry point."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys

import pytest

from conftest import APP_DIR
from exporter import write_outputs
from figure_export import CSS_PLACEHOLDER, JS_PLACEHOLDER
from jsrun import needs_node
from version import __version__
from metrics import compute_dynamic_metrics, compute_metrics
from network import build_dynamic, build_dynamic_spell_graph, build_static

LEGACY_TOKENS = ("verse_count", "total_verses", "gini_verses",
                 "div2", "div3", "dracor", "DraCor")


@pytest.fixture(scope="module")
def exported(demo_play, demo_segments, tmp_path_factory):
    """Run the export stage once and return the output directory."""
    segs = demo_segments["middle-seq"]
    static_g = build_static(segs, demo_play.characters)
    spell_g = build_dynamic_spell_graph(segs, demo_play.characters)
    metrics = compute_metrics(static_g, demo_play.play_id, demo_play.title_en)
    dyn_rows = compute_dynamic_metrics(build_dynamic(segs, demo_play.characters))

    out = tmp_path_factory.mktemp("export")
    write_outputs(demo_play, segs, static_g, spell_g, metrics, dyn_rows, out)
    return out


# ---------------------------------------------------------------------------
# Exported artefacts
# ---------------------------------------------------------------------------

EXPECTED_FILES = [
    "metrics.json", "characters.csv", "segments.csv", "networkdata.csv",
    "networkdata.gexf", "networkdata.graphml", "dynamic.gexf",
    "dynamic_metrics.csv",
]


@pytest.mark.parametrize("name", EXPECTED_FILES)
def test_export_writes_every_artefact(exported, name):
    path = exported / name
    assert path.is_file(), f"{name} not written"
    assert path.stat().st_size > 0, f"{name} is empty"


def test_dynamic_metrics_reports_no_per_segment_density(exported, demo_play):
    """A segment's graph is a clique, so its density is 1 wherever two or
    more stand together and 0 otherwise.  Exported, that column reads as a
    finding and states the construction; `numEdges` says the same as a count
    and is kept -- n(n-1)/2, less any collective joined to its own part."""
    from itertools import combinations
    rows = list(csv.DictReader(
        (exported / "dynamic_metrics.csv").read_text(encoding="utf-8")
        .splitlines()))
    casts = {r["segment_id"]: [c for c in r["model_cast"].split("|") if c]
             for r in csv.DictReader(
                 (exported / "segments.csv").read_text(encoding="utf-8")
                 .splitlines())}
    chars = demo_play.characters
    assert "density" not in rows[0]
    assert "numEdges" in rows[0]
    for r in rows:
        n = int(r["size"])
        one_body = sum(1 for a, b in combinations(casts[r["segment_id"]], 2)
                       if b in chars[a].part_of or a in chars[b].part_of)
        assert int(r["numEdges"]) == n * (n - 1) // 2 - one_body, r["segment_label"]


def test_metrics_json_is_valid_and_word_based(exported):
    data = json.loads((exported / "metrics.json").read_text(encoding="utf-8"))
    assert data["size"] > 0
    assert data["nodes"]
    blob = json.dumps(data)
    for token in LEGACY_TOKENS:
        assert token not in blob, f"legacy token {token!r} in metrics.json"


def test_characters_csv_header(exported):
    with open(exported / "characters.csv", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert "total_words" in header
    assert "temporal_gini" in header
    assert not [c for c in header if "verse" in c]


def test_speech_time_columns_are_populated_not_just_declared(exported_models):
    """A column in the header proves nothing about the rows.

    The export names its fields twice -- once in the header list, once in the
    row dict -- so adding one to the header alone yields a column of blanks.
    Read from a real CLI run: the `exported` fixture assembles its outputs by
    hand and never runs the temporal-Gini merge, so it has no speech-time
    values to check.
    """
    rows = exported_models["full"]["characters"]
    speakers = [r for r in rows if r["temporal_gini"]]
    assert speakers, "no character carries a temporal Gini"
    for r in speakers:
        for field in ("total_words", "speaking_segments",
                      "n_onstage_segments"):
            assert r[field], f"{r['id']}: {field} is empty"
        assert 0 < int(r["speaking_segments"]) <= int(r["n_onstage_segments"])


def test_segments_csv_header(exported):
    with open(exported / "segments.csv", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert "word_count" in header
    assert {"large_seq_id", "large_seq_type",
            "middle_seq_id"} <= set(header)
    assert not [c for c in header if "verse" in c or "div2" in c or "div3" in c]


def test_segments_csv_row_count_matches(exported, demo_segments):
    with open(exported / "segments.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(demo_segments["middle-seq"])


def test_networkdata_csv_is_an_edge_list(exported, demo_play, demo_segments):
    with open(exported / "networkdata.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert set(rows[0]) == {"Source", "Type", "Target", "Weight"}
    G = build_static(demo_segments["middle-seq"], demo_play.characters)
    assert len(rows) == G.number_of_edges()


def test_graphml_and_gexf_are_wellformed_xml(exported):
    from lxml import etree
    for name in ("networkdata.gexf", "networkdata.graphml", "dynamic.gexf"):
        etree.parse(str(exported / name))       # raises on malformed XML


def test_dynamic_gexf_carries_spells(exported):
    text = (exported / "dynamic.gexf").read_text(encoding="utf-8")
    assert "<spells>" in text and "<spell " in text


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

def _run_app(*args, cwd=APP_DIR, env=None):
    run_env = None
    if env:
        run_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, "app.py", *args],
        cwd=str(cwd), capture_output=True, text=True, timeout=600, env=run_env,
    )


@pytest.mark.slow
def test_cli_analyze_builds_a_dashboard(demo_path, tmp_path):
    out = tmp_path / "analyze"
    proc = _run_app("analyze", str(demo_path), "--seg", "middle-seq",
                    "--out", str(out))
    assert proc.returncode == 0, proc.stderr[-2000:]

    dashboards = list(out.rglob("dashboard.html"))
    assert dashboards, "no dashboard.html produced"
    html = dashboards[0].read_text(encoding="utf-8")
    assert "SkeneGraph-Net" in html
    # `div2` / `div3` are the dead names of the sequence segmenters; they must
    # never reappear.  DraCor was once on this list too, but the Methods panel
    # now names it deliberately, where it documents which field names
    # `metrics.json` borrows from that schema -- a reader who knows the
    # endpoint needs to be told that its `size` is our `order`.
    for token in ("div2", "div3"):
        assert token not in html, f"legacy token {token!r} in dashboard"


@pytest.mark.slow
def test_cli_corpus_builds_a_corpus_dashboard(demo_path, tmp_path):
    out = tmp_path / "corpus"
    proc = _run_app("corpus", str(demo_path), "--seg", "middle-seq",
                    "--out", str(out))
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert (out / "corpus_dashboard.html").is_file()


@pytest.mark.slow
def test_both_dashboards_carry_the_figure_exporter(demo_path, tmp_path):
    """Figures must be exportable as vector art, captioned with their model.

    The exporter and its provenance hook are injected by plain replace, the
    way the Methods panel is; an unreplaced placeholder or a missing hook
    would leave the buttons inert, which no other test would notice.
    """
    out = tmp_path / "figures"
    proc = _run_app("corpus", str(demo_path), "--seg", "sd", "--out", str(out))
    assert proc.returncode == 0, proc.stderr[-2000:]

    pages = [out / "corpus_dashboard.html", next(out.rglob("dashboard.html"))]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert CSS_PLACEHOLDER not in html, f"{page.name}: CSS placeholder unreplaced"
        assert JS_PLACEHOLDER not in html, f"{page.name}: JS placeholder unreplaced"
        assert "window.__figureExport" in html, f"{page.name}: exporter missing"
        assert ".fig-export button" in html, f"{page.name}: control styling missing"
        # The hook the exporter calls for the caption, defined per dashboard.
        assert "function figureProvenance" in html, f"{page.name}: no provenance hook"
        # The version is stamped in, so a figure traces to the build.
        assert f'APP_VERSION = "{__version__}"' in html, f"{page.name}: version missing"
        # Tables leave as data, and every configuration as one table.
        assert "function exportTableCSV" in html, f"{page.name}: no table export"
        assert "function figureComparisonRows" in html, (
            f"{page.name}: no all-configurations hook")
        assert "data-comparison-export" in html, (
            f"{page.name}: no panel carries the comparison control")


def test_a_figure_is_named_by_its_heading_not_its_controls():
    """Both dashboards keep the fullscreen toggle inside the panel heading,
    and its text ran into every exported figure's title and file name:
    'Density × order ⛶ fullscreen', density-order-fullscreen.svg."""
    from figure_export import figure_export_js
    title = figure_export_js().split("function panelTitle")[1].split("\n  }")[0]
    assert '".hint, .fig-export, button"' in title


def _wrap(text, max_width, per_char=6):
    """The exporter's caption wrap, run in node with a measurer of its own:
    a character is `per_char` wide, so the assertions do not depend on the
    fonts installed."""
    from figure_export import figure_export_js
    from jsrun import page_function, run_node
    return run_node(
        page_function(figure_export_js(), "wrapText")
        + "\nconst c = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        + "\nprocess.stdout.write(JSON.stringify("
        + "wrapText(c.text, c.maxWidth, s => s.length * c.perChar)));",
        {"text": text, "maxWidth": max_width, "perChar": per_char})


CAPTION = ("11 plays · stage-direction segmentation · stage co-presence · "
           "collectives aggregated · dots coloured by average degree · "
           "highlighted: Lys. · SkeneGraph-Net 2.0.0")


@needs_node
def test_a_key_travels_with_its_figure_however_it_is_painted():
    """The chorus chart keeps its key in `.legend-inline`, and two of its
    three swatches are a hatch and a ramp rather than a colour.  The
    collector read `.legend > span` and a background colour, so none of the
    three reached a figure: an exported chorus chart or heatmap no longer
    said which cells are silence, which are a performance whose text is
    lost, and which are words."""
    from figure_export import figure_export_js
    js = figure_export_js()
    assert '".legend > span, .legend-inline > span"' in js
    assert 'sw.getAttribute("data-swatch")' in js
    # The two paints a colour cannot carry, drawn as the charts draw them.
    assert 'item.kind === "ramp"' in js
    assert '"patternTransform", "rotate(45)"' in js


@pytest.mark.slow
def test_both_heatmaps_carry_their_key(demo_path, tmp_path):
    """Grey, hatch and ramp are the states a heatmap cell can hold.  The
    per-play one said so in its heading's hint, which no figure takes with
    it; it now keeps a key of its own, as the corpus chorus chart does."""
    out = tmp_path / "keys"
    proc = _run_app("corpus", str(demo_path), "--seg", "sd", "--out", str(out))
    assert proc.returncode == 0, proc.stderr[-2000:]
    pages = {"per-play": next(out.rglob("dashboard.html")),
             "corpus": out / "corpus_dashboard.html"}
    for label, path in pages.items():
        page = path.read_text(encoding="utf-8")
        assert 'data-swatch="hatch"' in page, label
        assert 'data-swatch="ramp"' in page, label
        assert "performs, text not transmitted" in page, label
        assert "present, silent" in page, label


def test_a_caption_is_wrapped_to_the_figure_rather_than_cut_off():
    """Beside a dashboard panel some 360 px wide, the ordinary caption runs
    to about 700 and was drawn as one line from the left margin: the second
    half fell outside the image, and outside the PNG for good.  The whole
    of it now stands inside the figure."""
    lines = _wrap(CAPTION, 363 - 16)
    assert len(lines) > 1, "the caption is too long for one line here"
    assert all(len(line) * 6 <= 363 - 16 for line in lines)
    assert " ".join(lines) == CAPTION, "no word is lost or repeated"


@needs_node
def test_a_caption_that_fits_stays_on_one_line():
    assert _wrap(CAPTION, 2000) == [CAPTION]


@needs_node
def test_a_word_wider_than_the_line_keeps_a_line_of_its_own():
    """Breaking a word would lose more than it saves; it overruns, alone."""
    assert _wrap("a bbbbbbbbbbbbbbbbbbbb c", 60) == ["a", "bbbbbbbbbbbbbbbbbbbb", "c"]


def test_the_figure_width_covers_its_caption_or_wraps_it():
    """The width is measured from the art and the heading, so the caption
    must be wrapped to it rather than drawn as one line."""
    from figure_export import figure_export_js
    js = figure_export_js()
    assert "wrapText(full, totalW - PAD * 2" in js
    assert "y += CAPTION_ROW + (lines.length - 1) * CAPTION_LINE;" in js


def test_the_heatmap_waits_for_a_container_with_a_width():
    """With no width the plot area is negative and every cell was drawn at a
    negative width: on a page rendered in a hidden window, some 4,000
    console errors and an empty heatmap.  It now draws nothing until the
    element has room, and draws itself when it gets it."""
    from dashboard import _TEMPLATE
    body = _TEMPLATE.split("function renderHeatmap")[1].split("\nfunction ")[0]
    assert "if (!(plotW > 0)) {{ drawWhenSized(svg.node(), renderHeatmap); return; }}" in body
    assert "new ResizeObserver" in _TEMPLATE


def test_a_figure_carries_no_html_but_its_heading_and_chart_titles():
    """Every text sibling of a lone <svg> used to be drawn into its figure,
    and where the <svg> sits in the panel itself the heading is one: its
    hint, checkboxes and buttons came out run together ('exit
    fullscreenSVGPNG'), and in fullscreen the segmentation controls too.
    Only the small multiples' titles travel now, and the figure is headed
    by the panel's title, set apart from the page's layout."""
    from figure_export import figure_export_js
    js = figure_export_js()
    labels = js.split("function labelsFor")[1].split("\n  }")[0]
    assert 'el.classList.contains("title")' in labels
    assert 'const heading = panel.querySelector("h3") ? panelTitle(panel) : "";' in js


@pytest.mark.slow
def test_no_metric_is_rendered_as_doubtful(demo_path, tmp_path):
    """Every headline metric is shown with the same weight.

    Diameter, path length, clustering and component count used to be greyed
    as a demoted sub-group.  They are exact for the graph shown, not
    estimates, so the greying asserted something untrue about them and
    invited the reader to discount the metrics beside them.
    """
    out = tmp_path / "weighting"
    proc = _run_app("analyze", str(demo_path), "--seg", "sd", "--out", str(out))
    assert proc.returncode == 0, proc.stderr[-2000:]
    html = next(out.rglob("dashboard.html")).read_text(encoding="utf-8")
    assert ".item.structural" not in html, "a metric is styled as demoted again"
    assert "reported for completeness" not in html, "the old hedge is back"
    # The substance it carried is kept, as a measured statement.
    assert "every value here is exact" in html, "the footnote lost its claim"


@pytest.mark.slow
def test_composition_row_does_not_fold_a_bucket_into_its_neighbour(demo_path, tmp_path):
    """`other` is shown, not added to `concept`.

    The row used to render `concept + other`, so a nature value outside the
    four categories appeared inside `concept` without saying so -- invisible
    while no play uses one, and silently wrong in the play that first does.
    """
    out = tmp_path / "composition"
    proc = _run_app("analyze", str(demo_path), "--seg", "sd", "--out", str(out))
    assert proc.returncode == 0, proc.stderr[-2000:]
    html = next(out.rglob("dashboard.html")).read_text(encoding="utf-8")
    assert "na.concept + (na.other" not in html, "the nature row folds again"
    assert "sx.mixed ?" in html, "the sex row lost its conditional bucket"


@pytest.mark.slow
def test_tables_sort_on_a_column_key_not_on_its_rendered_text(demo_path, tmp_path):
    """Columns may declare what to order by, separately from what they show.

    Without it the sort is lexicographic on the cell: the corpus "top spk"
    column orders by the speaker's name rather than by their share, and any
    formatted number orders by its digits, putting 12.74 before 3.67.
    """
    out = tmp_path / "sorting"
    proc = _run_app("corpus", str(demo_path), "--seg", "sd", "--out", str(out))
    assert proc.returncode == 0, proc.stderr[-2000:]

    for page in (out / "corpus_dashboard.html", next(out.rglob("dashboard.html"))):
        html = page.read_text(encoding="utf-8")
        assert "const keyOf = sortCol[3] || sortCol[1];" in html, (
            f"{page.name}: drawTable no longer honours a column's sort key")
    corpus = (out / "corpus_dashboard.html").read_text(encoding="utf-8")
    assert "top_speaker_word_share || 0]" in corpus, (
        "the corpus top-speaker column lost its share-based sort key")


# ---------------------------------------------------------------------------
# Cross-dashboard agreement
# ---------------------------------------------------------------------------

def _dashboard_data(html_path):
    """Pull the `const DATA = {...};` payload out of a generated dashboard."""
    text = html_path.read_text(encoding="utf-8")
    i = text.index("const DATA = ")
    j = text.index("\n", i)
    return json.loads(text[i + len("const DATA = "):j].rstrip().rstrip(";"))


def _agg_key(variants):
    """The full-group aggregation key ("a,b"), or "" if nothing aggregable.

    Taken from the variant keys themselves rather than re-deriving it from
    the partOf relations, so the test cannot drift from the producer.
    """
    keys = {k.split(":", 1)[1] for k in variants}
    keys.discard("")
    return max(keys, key=lambda k: k.count(",")) if keys else ""


@pytest.mark.slow
def test_corpus_and_play_dashboards_agree_on_temporal_gini(demo_path, tmp_path):
    """The corpus tGini column must equal the per-play dashboard's value.

    Regression guard for the `speech_distribution` sharing bug: the corpus
    summary reused the *stage* view's dict for every non-aggregated block.
    That is right for the four play-level word metrics, which are identical
    in every variant, but wrong for the two segment-axis-dependent fields
    (`top_speaker_temporal_gini`, `n_active_segments`) that app.py adds from
    `compute_temporal_gini(segments)`: under `sd` the mutes-out spine is
    folded, so they genuinely differ per mute mode.  The corpus then showed
    the unfolded value beside this block's folded `num_segments`.

    Checks every (segmentation x mute mode x aggregation) combination, and
    both the value the corpus table prints and the one the per-play tGini
    table prints (which comes from the character rows, a separate path).
    """
    from app import analyze_one

    out = tmp_path / "agree"
    summary = analyze_one(
        xml_path=demo_path,
        seg_modes=["sd", "large-seq", "middle-seq"],
        out_root=out,
        export_model="full",
        edge_weight="segments",
    )
    assert summary is not None, "analyze_one produced no summary"
    play_data = _dashboard_data(next(out.rglob("dashboard.html")))

    checked = 0
    for seg, corpus_block in summary["segmentations"].items():
        play_entry = play_data["segmentations"][seg]
        variants = play_entry.get("variants") or {}
        agg_key = _agg_key(variants)

        def play_variant(mute, agg):
            if mute == "full" and not agg:
                return play_entry
            return variants.get(f"{mute}:{agg_key if agg else ''}")

        blocks = [("full", False, corpus_block),
                  ("full", True, corpus_block.get("agg"))]
        for mute in ("p-speaking", "s-speaking"):
            sub = corpus_block.get(mute)
            blocks.append((mute, False, sub))
            blocks.append((mute, True, (sub or {}).get("agg")))

        for mute, agg, cblock in blocks:
            if cblock is None:
                continue
            pv = play_variant(mute, agg)
            assert pv is not None, f"{seg}/{mute}{'+agg' if agg else ''}: no play variant"
            csd = cblock.get("speech_distribution") or {}
            psd = (pv.get("metrics") or {}).get("speech_distribution") or {}
            where = f"{seg}/{mute}{'+agg' if agg else ''}"

            # The block must not mix variants: its segment count and its
            # segment-dependent speech fields have to come from one source.
            assert cblock["num_segments"] == pv["metrics"]["num_segments"], (
                f"{where}: num_segments {cblock['num_segments']} != "
                f"{pv['metrics']['num_segments']}")
            for field in ("top_speaker_temporal_gini", "n_active_segments"):
                assert csd.get(field) == psd.get(field), (
                    f"{where}: {field} {csd.get(field)} != {psd.get(field)}")

            # ...and must match what the per-play tGini table actually renders,
            # which reads the character rows rather than speech_distribution.
            top_id = csd.get("top_speaker_id")
            if top_id:
                chars = {c["id"]: c for c in (pv.get("characters") or [])}
                rendered = (chars.get(top_id) or {}).get("temporal_gini")
                assert csd.get("top_speaker_temporal_gini") == rendered, (
                    f"{where}: corpus tGini {csd.get('top_speaker_temporal_gini')} "
                    f"!= play table {rendered} for {top_id}")
            checked += 1

    # The demo play has a split chorus and all three spines, so every
    # combination should be present; a silent drop would void the guard.
    assert checked >= 12, f"only {checked} combinations checked"


@pytest.mark.slow
def test_every_word_figure_on_a_dashboard_reconciles(demo_path, tmp_path):
    """The one word rule, checked on the shipped payload.

    Three surfaces show word counts: the metrics panel (one play total), the
    segment table (one row per segment) and the beat chart (one cell per
    character x segment).  All three are sums of the same credits, so the
    cells add up to their row and the rows add up to the total -- in every
    variant, including the partOf-aggregated ones, where remapping can put
    two ids of a joint speech into one group.

    The demo play carries a four-speaker joint speech, so before the rule was
    unified the segment rows fell six words short of the panel.
    """
    from app import analyze_one

    out = tmp_path / "words"
    assert analyze_one(
        xml_path=demo_path,
        seg_modes=["sd", "large-seq", "middle-seq"],
        out_root=out,
        export_model="full",
        edge_weight="segments",
    ) is not None
    data = _dashboard_data(next(out.rglob("dashboard.html")))

    checked = 0
    for spine, entry in data["segmentations"].items():
        blocks = [("", entry)] + sorted((entry.get("variants") or {}).items())
        for key, block in blocks:
            where = f"{spine}/{key or 'full'}"
            segs = block["segments"]
            for s in segs:
                assert sum(s["words_by_speaker"].values()) == s["word_count"], (
                    f"{where} seg {s['id']}: beat-chart cells "
                    f"{sum(s['words_by_speaker'].values())} != row "
                    f"{s['word_count']}")
            total = block["metrics"]["speech_distribution"]["total_words_spoken"]
            assert sum(s["word_count"] for s in segs) == total, (
                f"{where}: segment rows {sum(s['word_count'] for s in segs)} "
                f"!= panel total {total}")
            checked += 1
    assert checked >= 12, f"only {checked} variants checked"


# ---------------------------------------------------------------------------
# --export-model
# ---------------------------------------------------------------------------

EXPORT_MODELS = [
    # cli name / model,  metrics.segment_cast,  mutes exported?
    ("full",             "stage",               True),
    ("p-speaking",       "stage",               False),
    ("s-speaking",       "speaking",            False),
]


@pytest.fixture(scope="module")
def exported_models(demo_path, tmp_path_factory):
    """One `analyze --seg sd` run per export model, keyed by CLI name."""
    root = tmp_path_factory.mktemp("export_models")
    out = {}
    for model, *_ in EXPORT_MODELS:
        d = root / model
        proc = _run_app("analyze", str(demo_path), "--seg", "sd",
                        "--export-model", model, "--no-dashboard", "--out", str(d))
        assert proc.returncode == 0, proc.stderr[-2000:]
        seg_dir = next(d.rglob("sd"))
        out[model] = {
            "metrics": json.loads((seg_dir / "metrics.json").read_text(encoding="utf-8")),
            "characters": list(csv.DictReader(
                (seg_dir / "characters.csv").open(encoding="utf-8"))),
        }
    return out


@pytest.mark.slow
@pytest.mark.parametrize("model,segment_cast,keeps_mutes", EXPORT_MODELS)
def test_export_model_writes_that_model(exported_models, model,
                                        segment_cast, keeps_mutes):
    """--export-model picks which of the three models reaches the files.

    It used to be `--no-mutes`, which was never read: `analyze_one` took the
    flag and then derived everything from the hard-coded mute modes, so the
    exports were always the stage view.  These assertions fail if the option
    goes inert again.
    """
    m = exported_models[model]["metrics"]
    # The model is named identically on the CLI and in the exported metrics.
    assert m["mute_mode"] == model
    assert m["segment_cast"] == segment_cast

    # A mutes-out export must drop the play-level mutes from the graph, but
    # still list them in characters.csv with in_network=False -- the roster
    # is the play's, the network is the model's.
    rows = exported_models[model]["characters"]
    in_net_mutes = [r for r in rows
                    if r["is_mute"] == "True" and r["in_network"] == "True"]
    assert bool(in_net_mutes) is keeps_mutes, (
        f"{model}: {len(in_net_mutes)} mute(s) in the exported network")
    assert sum(1 for r in rows if r["in_network"] == "True") == m["size"]


@pytest.mark.slow
def test_export_models_differ_from_each_other(exported_models):
    """Guard against the three names collapsing onto one graph."""
    full = exported_models["full"]["metrics"]
    p_spk = exported_models["p-speaking"]["metrics"]
    s_spk = exported_models["s-speaking"]["metrics"]
    # Dropping play-level mutes shrinks the node set...
    assert p_spk["size"] < full["size"]
    # ...and the two speaking models share it, differing only by segment cast.
    assert p_spk["size"] == s_spk["size"]
    assert s_spk["numEdges"] != p_spk["numEdges"]


@pytest.mark.slow
def test_exported_segment_indices_are_read_for_the_models_own_cast(
        exported_models):
    """The pipeline hands each model's segment cast to the indices.

    The two speaking models share a node set, so under the old code -- which
    always read the annotated stage -- their final shares came out identical
    while the dashboards' beat charts, which do follow the model, disagreed
    with them.  The segment-level reading must now be the stricter one.
    """
    p_idx = exported_models["p-speaking"]["metrics"]["segment_indices"]
    s_idx = exported_models["s-speaking"]["metrics"]["segment_indices"]
    assert s_idx["final_segment_cast_share"] < p_idx["final_segment_cast_share"]
    # The walk-back to the last acted segment survives: a speaking cast that
    # stopped at the terminal empty-stage marker would read 0.0 here.
    assert s_idx["final_segment_cast_share"] > 0.0


@pytest.mark.slow
def test_export_model_defaults_to_full(demo_path, tmp_path):
    """The default must stay the annotated stage spine (pre-flag behaviour)."""
    out = tmp_path / "default"
    proc = _run_app("analyze", str(demo_path), "--seg", "sd",
                    "--no-dashboard", "--out", str(out))
    assert proc.returncode == 0, proc.stderr[-2000:]
    m = json.loads(next(out.rglob("sd/metrics.json")).read_text(encoding="utf-8"))
    assert m["mute_mode"] == "full" and m["segment_cast"] == "stage"


@pytest.mark.slow
def test_exports_are_reproducible_across_hash_seeds(demo_path, tmp_path):
    """Two runs of the same command must produce byte-identical artefacts.

    Python randomises `hash()` per process, so any output built by iterating
    a set varies run to run.  That is how the spell graph's node order (and
    with it every GEXF edge's source/target orientation) used to drift --
    harmless for the data, but it defeated byte-diffing of outputs, which is
    the cheapest way to check whether a change altered results.

    `lastmodifieddate` is networkx's own write-time stamp and is normalised
    away here; everything else must match exactly.
    """
    outs = []
    for seed in ("0", "12345"):
        d = tmp_path / f"seed{seed}"
        proc = _run_app("analyze", str(demo_path), "--seg", "sd",
                        "--no-dashboard", "--out", str(d),
                        env={"PYTHONHASHSEED": seed})
        assert proc.returncode == 0, proc.stderr[-2000:]
        outs.append(next(d.rglob("sd")))

    a, b = outs
    names = sorted(p.name for p in a.iterdir())
    assert names, "no artefacts written"

    def digest(p):
        raw = p.read_bytes()
        raw = re.sub(rb'lastmodifieddate="[^"]*"', b"", raw)
        return hashlib.sha256(raw).hexdigest()

    differing = [n for n in names if digest(a / n) != digest(b / n)]
    assert not differing, f"not reproducible across hash seeds: {differing}"


@pytest.mark.slow
def test_cli_rejects_an_unknown_export_model(demo_path, tmp_path):
    proc = _run_app("analyze", str(demo_path), "--seg", "sd",
                    "--export-model", "no-mutes", "--out", str(tmp_path / "bad"))
    assert proc.returncode != 0
    assert "invalid choice" in (proc.stderr + proc.stdout)


@pytest.mark.slow
def test_cli_rejects_an_unknown_segmentation(demo_path, tmp_path):
    proc = _run_app("analyze", str(demo_path), "--seg", "div2",
                    "--out", str(tmp_path / "bad"))
    assert proc.returncode != 0
    assert "invalid choice" in (proc.stderr + proc.stdout)


@pytest.mark.slow
def test_cli_seg_choices_are_the_current_vocabulary(demo_path, tmp_path):
    proc = _run_app("analyze", "--help")
    assert proc.returncode == 0
    for token in ("sd", "large-seq", "middle-seq"):
        assert token in proc.stdout
    assert "div2" not in proc.stdout and "div3" not in proc.stdout
