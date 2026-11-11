"""Corpus-level dashboard.

Bundles a one-row-per-play summary (metrics + cast composition + segment
indices + a compact per-segment beat-rate / size / word array for overlay
plots) into a single self-contained HTML page.

Layout
------
   ┌─────────────────────────────────────────────────────────┐
   │ Header (corpus name, plays, authors; view tabs)         │
   ├─────────────────────────────────────────────────────────┤
   │ Segmentation tabs, network model, aggregation toggle    │
   ├─────────────────────────────────────────────────────────┤
   │ Plays included (chip selector, highlights)              │
   ├─────────────────────────────────────────────────────────┤
   │ Corpus summary KPIs (totals + means + ranges)           │
   ├──────────────┬─────────────┬─────────────┬──────────────┤
   │ density ×    │ avg degree ×│ DCR × σ     │ eff. spk ×   │
   │ order        │ order       │ (typology)  │ avg degree   │
   ├──────────────┴─────────────┴─────────────┴──────────────┤
   │ Cast composition stacked bars (speakers / mutes)        │
   ├─────────────────────────────────────────────────────────┤
   │ Beat-chart small multiples (one per play)               │
   ├─────────────────────────────────────────────────────────┤
   │ Chorus presence across the play                         │
   ├─────────────────────────────────────────────────────────┤
   │ Sortable plays table -- click a row to open per-play    │
   │ dashboard                                               │
   └─────────────────────────────────────────────────────────┘

Departures from the per-play dashboard (small but meaningful):
* No force controls, no dynamic graph: this is a comparative view, not a
  per-play exploration tool.
* All panels react to the segmentation tab.
* Click a play row -> opens its per-play dashboard in the same tab,
  so the corpus dashboard works as a navigation hub.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import networkx as nx  # noqa: F401  (re-export of types used by callers)

from aggregation import aggregatable_groups
from segmentation import active_span
# One definition of each, shared with the per-play dashboard: an escape
# applied in one writer and not the other is no protection.
from dashboard import _html_escape, _json_for_script
from figure_export import (CSS_PLACEHOLDER, JS_PLACEHOLDER,
                           figure_export_css, figure_export_js)
from methods_content import methods_panel_html
from vendor_assets import PLACEHOLDER as VENDOR_PLACEHOLDER, vendor_assets_html


def _attach_agg(block, agg_block):
    """Nest a partOf-aggregated counterpart inside a mode block.

    Returns `block` with an `agg` key holding `agg_block`, but only when
    both exist.  Plays without aggregable partOf groups get `agg_block is
    None`, so the key is simply omitted and the JS `segOf` falls back to
    the raw block.
    """
    if block is not None and agg_block is not None:
        block["agg"] = agg_block
    return block


def _change_rates(segs, cast):
    """Beat-chart rates: the Jaccard distance between consecutive casts.

    Returns `(rates, start)`, `start` being the index of the segment the
    first transition departs from.  The transitions at both brackets are
    skipped -- out of an empty pre-play segment, and into an empty terminal
    one after a full exeunt -- each being 1.0 by definition, a cast compared
    with the empty set.  The per-play page computes the same series in the
    browser (`segmentChangeRates`).
    """
    start = 1 if (segs and segs[0].is_initial and not cast(segs[0])) else 0
    end = (len(segs) - 2
           if len(segs) > 1 and segs[-1].is_final and not cast(segs[-1])
           else len(segs) - 1)
    rates: List[float] = []
    for i in range(start, end):
        a, b = cast(segs[i]), cast(segs[i + 1])
        u = a | b
        rates.append(len(a ^ b) / len(u) if u else 0.0)
    return rates, start


def extract_play_summary(
    play, results: Dict[str, Dict], dashboard_href: str
) -> Dict:
    """Compact summary for one play across all its segmentations.

    `results` is the per-play dict the caller already built::
       {mode: {"static_graph", "segments", "metrics", "dynamic_rows"}}
    `dashboard_href` is the relative URL of this play's per-play
    dashboard, used by the corpus dashboard for drill-down clicks.
    """
    # Play-level composition ratios for the corpus plays table.  Computed
    # under all three mute modes so the JS can swap with the mute radio,
    # the same way the rest of the dashboard does.  Within each mode the
    # demographics come from the fully-aggregated variant (chorus
    # split-semichoruses collapsed) so the `collective speakers / total
    # speakers` ratio counts each chorus once.  Plays with no
    # <listRelation> entries fall back to the top-level (raw) demographics
    # for the given mode.
    #
    # The groups come from the one function that decides which variants the
    # writer builds; a list re-derived here could name a key never built,
    # and the lookups below would fall back to raw data without a word.  An
    # empty agg_key means the play has nothing to aggregate.
    agg_key = ",".join(aggregatable_groups(play))

    def _pick_demographics(mute_mode: str) -> Dict:
        if not results:
            return {}
        any_mode = next(iter(results.values()))
        target_key = f"{mute_mode}:{agg_key}" if agg_key else None
        variants = any_mode.get("variants") or {}
        if target_key and target_key in variants:
            return variants[target_key]["metrics"].get("demographics", {})
        # No partOf aggregation possible.  Fall back to the appropriate
        # top-level demographics: for "full" that's the raw metrics;
        # for "p-speaking" / "s-speaking" that's variants["p-speaking:"] /
        # variants["s-speaking:"] respectively.
        if mute_mode != "full":
            v = variants.get(f"{mute_mode}:")
            if v is not None:
                return v["metrics"].get("demographics", {})
        return any_mode["metrics"].get("demographics", {})

    def _ratios(dem: Dict) -> Dict:
        speakers = dem.get("speakers", 0)
        mutes = dem.get("mutes", 0)
        total = speakers + mutes
        coll_spk = dem.get("collective_speakers", 0)
        sx = dem.get("sex", {"male": 0, "female": 0, "mixed": 0,
                             "unspecified": 0})
        female = sx.get("female", 0)
        male = sx.get("male", 0)
        return {
            "speakers_share":            (speakers / total) if total else None,
            "collective_speakers_share": (coll_spk / speakers) if speakers else None,
            "female_share":              (female / (female + male)) if (female + male) else None,
        }

    composition = {
        "full":    _ratios(_pick_demographics("full")),
        "p-speaking": _ratios(_pick_demographics("p-speaking")),
        "s-speaking": _ratios(_pick_demographics("s-speaking")),
    }

    # Genre.  Read from the TEI header when the play declares one
    # (<textClass><catRef scheme="#genre" .../></textClass>); the author
    # heuristic below is the fallback for files not yet classified.  Used
    # by the corpus chorus beat chart to sort plays as
    # genre -> author -> title; unknown authors collapse to "other",
    # sorted last.
    def _genre_of(author: str) -> str:
        a = (author or "").lower()
        comedy_keys = (
            # Latin / English transliterations
            "aristophanes", "menander", "plautus", "terence",
            # Greek (lowercased Unicode)
            "ἀριστοφάνης", "αριστοφάνης", "μένανδρος",
        )
        tragedy_keys = (
            "sophocles", "euripides", "aeschylus", "seneca",
            "σοφοκλῆς", "σοφοκλης", "εὐριπίδης", "ευριπίδης",
            "αἰσχύλος", "αισχύλος",
        )
        if any(k in a for k in comedy_keys):
            return "comedy"
        if any(k in a for k in tragedy_keys):
            return "tragedy"
        return "other"

    summary = {
        "id": play.play_id or "",
        "title_en": play.title_en or "",
        "title_grc": play.title_grc or "",
        "title_lat": play.title_lat or "",
        "title_lat_abbr": play.title_lat_abbr or "",
        "author": play.author or "",
        "author_lat_abbr": play.author_lat_abbr or "",
        "genre": play.genre or _genre_of(play.author or ""),
        "dashboard_href": dashboard_href,
        "composition": composition,
        "segmentations": {},
    }
    for mode, r in results.items():
        m = r["metrics"]
        segs = r["segments"]

        # Beat-chart rates.  The start index -- the segment the series' first
        # transition departs from -- is shipped so the word-mode x-placement
        # never has to reconstruct the offset from length arithmetic
        # (impossible now that the trailing bracket is excluded too).
        rates_stage, rates_stage_start = _change_rates(
            segs, lambda s: s.characters_present)
        words_per_segment = [s.word_count for s in segs]

        # Build one "mode block" per (mute mode, aggregation state) -- same
        # field shape as the top-level (stage-mode raw) fields, so the JS
        # segOf(p) just returns the appropriate sub-dict.  `agg=True` reads
        # the partOf-aggregated variant (semi-choruses collapsed to one
        # node); change rates, per-segment series, speech distribution and
        # segment indices are all taken from that variant so order,
        # density, DCR, Gini and the beat-chart series reflect the
        # collapse.  For the raw blocks speech_distribution stays a
        # play-level constant shared from the stage view (the cast filter
        # does not change which characters speak); segment_indices, by
        # contrast, are computed per model -- the pipeline hands both of the
        # model's axes, its node set and its segment cast, to
        # compute_segment_indices, so they are read on the same cast as the
        # beat-chart series below -- so every block, raw or aggregated, keeps
        # its own.
        def _build_mode_block(mute_mode: str, agg: bool = False):
            if agg and not agg_key:
                return None  # nothing to aggregate -> no agg view
            key = f"{mute_mode}:{agg_key}" if agg else f"{mute_mode}:"
            v = (r.get("variants") or {}).get(key)
            if v is None:
                return None
            mo = v["metrics"]
            mo_segs = v["segments"]
            # Cast rule per mute mode, applied to this variant's own
            # segments (which already reflect the aggregation when agg).
            if mute_mode == "s-speaking":
                cast = lambda s: s.speakers
            elif mute_mode == "p-speaking":
                kept = {n["id"] for n in mo.get("nodes", [])}
                cast = lambda s: s.characters_present & kept
            else:  # stage
                cast = lambda s: s.characters_present
            seg_change, start_i = _change_rates(mo_segs, cast)
            size_per_seg = [len(cast(s)) for s in mo_segs]
            # Always the variant's own speech_distribution, never the stage
            # view's.  Four of its fields are play-level constants (gini_words,
            # top_speaker_id, top_speaker_word_share, total_words_spoken) and
            # are identical in every variant, so sharing them was harmless.
            # The other two are segment-axis dependent -- app.py adds
            # `top_speaker_temporal_gini` and `n_active_segments` from
            # compute_temporal_gini(segments) -- and under `sd` the mutes-out
            # spine is folded (fold_segments), so they genuinely differ per
            # mute mode.  Reading them from the stage view put the unfolded
            # value next to this block's folded num_segments and disagreed
            # with the per-play dashboard.
            speech_dist = mo.get("speech_distribution", m.get("speech_distribution", {}))
            seg_idx = mo.get("segment_indices", m.get("segment_indices", {}))
            return {
                "size":               mo["size"],
                "numEdges":           mo["numEdges"],
                "density":            mo["density"],
                "averageDegree":      mo["averageDegree"],
                "averageClustering":  mo["averageClustering"],
                "diameter":           mo["diameter"],
                "averagePathLength":  mo["averagePathLength"],
                "numConnectedComponents": mo["numConnectedComponents"],
                "maxDegree":          mo["maxDegree"],
                "maxDegreeIds":       mo["maxDegreeIds"],
                "num_segments":       mo["num_segments"],
                "demographics":       mo.get("demographics", {}),
                "speech_distribution": speech_dist,
                "segment_indices":     seg_idx,
                "change_rates":       seg_change,
                "change_rates_start": start_i,
                "size_per_segment":   size_per_seg,
                "words_per_segment": [s.word_count for s in mo_segs],
            }

        # Chorus beat-chart data for the corpus chart.  One row per
        # chorus character per (mute_mode, agg_state) combination.  Read
        # the chorus character list from each variant's character set
        # (filtered by is_chorus), then for each chorus character emit
        # its per-segment words + presence within that variant's segments.
        #
        # Trim leading and trailing segments that have an empty cast at
        # the play level (the sd segmenter emits an empty terminal
        # marker; the initial onStage flush can also be empty).  These
        # are dramaturgically vacuous bookkeeping segments; including
        # them in the denominator squeezes the real content of every
        # row into less than 100% of the chart width and makes the
        # right edge look jagged.  The trim is computed once per play
        # (against play-level characters_present) so every chorus in
        # the same play shares the same denominator -- consistency
        # within a row group matters more than the absolute count.
        def _chorus_rows(variant_data, variant_segments):
            chars = variant_data.get("characters", {}) if isinstance(variant_data, dict) else {}
            chorus_chars = [(cid, ch) for cid, ch in chars.items()
                            if getattr(ch, "is_chorus", False)]
            if not chorus_chars or not variant_segments:
                return []
            active = active_span(variant_segments)
            out = []
            for cid, ch in chorus_chars:
                words = []
                present = []
                speaks = []
                for s in active:
                    words.append(sum(sp.word_count for sp in s.speeches
                                     if cid in sp.who))
                    present.append(cid in s.characters_present)
                    # Follows the <sp>, not the word count, as everywhere
                    # else in the app: a choral song whose text is not
                    # transmitted (the XOPOY interludes) was performed, and
                    # is not silence.
                    speaks.append(cid in s.speakers)
                out.append({
                    "id":      cid,
                    "name":    ch.display_name,
                    "words":   words,
                    "present": present,
                    "speaks":  speaks,
                })
            return out

        # Resolve the six (mute_mode, agg_state) variants.  Top-level
        # results carry the stage-mode raw view; r["variants"] carries
        # p-speaking, s-speaking, and all partOf-aggregated variants.  When
        # a play has no partOf groups, the agg view falls back to the
        # raw view of the same mute mode.
        v = r.get("variants") or {}
        def _resolve(mute, agg):
            if mute == "full" and not agg:
                return {"characters": play.characters, "segments": segs}
            key = f"{mute}:{agg_key}" if agg else f"{mute}:"
            entry = v.get(key)
            if entry:
                return {"characters": entry["play"].characters,
                        "segments":   entry["segments"]}
            # Fall back to raw view at this mute mode (if not stage).
            if mute != "full":
                fb = v.get(f"{mute}:")
                if fb:
                    return {"characters": fb["play"].characters,
                            "segments":   fb["segments"]}
            return {"characters": play.characters, "segments": segs}

        chorus_data = {}
        for mute in ("full", "p-speaking", "s-speaking"):
            for agg in (False, True):
                vd = _resolve(mute, agg)
                chorus_data[f"{mute}_{'agg' if agg else 'raw'}"] = _chorus_rows(
                    vd, vd["segments"])

        summary["segmentations"][mode] = {
            "size":               m["size"],
            "numEdges":           m["numEdges"],
            "density":            m["density"],
            "averageDegree":      m["averageDegree"],
            "averageClustering":  m["averageClustering"],
            "diameter":           m["diameter"],
            "averagePathLength":  m["averagePathLength"],
            "numConnectedComponents": m["numConnectedComponents"],
            "maxDegree":          m["maxDegree"],
            "maxDegreeIds":       m["maxDegreeIds"],
            "num_segments":       m["num_segments"],
            "demographics":       m.get("demographics", {}),
            "speech_distribution": m.get("speech_distribution", {}),
            "segment_indices":    m.get("segment_indices", {}),
            "change_rates":       rates_stage,
            "change_rates_start": rates_stage_start,
            "size_per_segment":   [len(s.characters_present) for s in segs],
            "words_per_segment": words_per_segment,
            # Non-default mute modes as sub-dicts.  Each carries the
            # same field shape as the top-level fields (which are the
            # stage-mode view), so the JS segOf(p) can swap the active
            # mode by returning the right sub-dict.  Missing entries
            # (e.g. when no partOf groups exist) fall back gracefully
            # in segOf().  Each block also carries a nested `agg`
            # counterpart (partOf-aggregated, semi-choruses collapsed to
            # one node) that segOf returns when the global "aggregate
            # chorus halves" toggle is on; the top-level stage view gets
            # its agg counterpart under the "agg" key.  `agg` is absent
            # for plays without aggregable groups, so segOf falls back to
            # the raw block.
            "p-speaking":           _attach_agg(_build_mode_block("p-speaking"),
                                              _build_mode_block("p-speaking", agg=True)),
            "s-speaking":           _attach_agg(_build_mode_block("s-speaking"),
                                              _build_mode_block("s-speaking", agg=True)),
            "agg":                _build_mode_block("full", agg=True),
            "chorus_data":        chorus_data,
        }
    return summary


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title} - SkeneGraph-Net corpus</title>
<!--VENDOR_ASSETS-->
<style>
:root {{
  --bg: #fafafa; --panel: #ffffff; --border: #e0e0e0;
  --ink: #1a1a1a; --muted: #666; --accent: #1a5fb4;
  --speaker: #e07a5f; --mute: #aaa; --chorus: #4daf4a;
  --collective: #377eb8; --beat: #b73779;
  --tragedy: #1f78b4; --comedy: #e31a1c;
  /* Highlight ring on the scatters: orange, the complement of the blue dots
     and well clear of the red pair-lines. */
  --highlight: #f08c00;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px; line-height: 1.4; }}
/* Sticky topbar wraps the page header AND the view-tabs nav so that the
   corpus title and the Analysis / Methods tabs stay pinned to the top
   while the body scrolls. */
.topbar {{ position: sticky; top: 0; z-index: 100;
  background: var(--panel); }}
header {{ background: var(--panel); border-bottom: 1px solid var(--border);
  padding: 16px 24px; }}
/* Status chip strip under the title - reflects the active network model
   (mutes-in / mutes-out) so screenshots are self-documenting. */
.active-filters {{ margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap;
  font-size: 11px; min-height: 0; }}
.active-filters .filter-chip {{ display: inline-flex; align-items: baseline;
  gap: 4px; padding: 1px 8px; border-radius: 10px; background: #f0e8d4;
  color: #6b5d2e; border: 1px solid #d6c87a; font-weight: 500; }}
.active-filters .filter-chip .detail {{ color: #9b8b46; font-weight: 400;
  font-size: 10.5px; }}
header h1 {{ margin: 0 0 4px 0; font-size: 24px; }}
header .sub {{ color: var(--muted); font-size: 13px; }}
main {{ padding: 12px 16px; }}
/* Top-level view tabs (Analysis | Methods).  Distinct from `.tabs`,
   which switches segmentation. */
.view-tabs {{ background: var(--panel); border-bottom: 1px solid var(--border);
  padding: 0 16px; display: flex; gap: 2px; align-items: flex-end;
  margin-top: -1px; }}
.view-tabs .view-tab {{ padding: 8px 18px; background: transparent;
  border: 1px solid var(--border); border-bottom-color: transparent;
  border-radius: 4px 4px 0 0; cursor: pointer; font-size: 13px;
  font-weight: 500; color: var(--ink); position: relative; top: 1px; }}
.view-tabs .view-tab.active {{ background: var(--bg); border-bottom-color: var(--bg);
  color: var(--accent); }}
.view-tabs .view-tab:hover:not(.active) {{ background: #f0f0f0; }}
.view {{ }}
.view.hidden {{ display: none; }}
.methods-content {{ padding: 8px 8px 24px 8px; max-width: 980px;
  font-size: 14px; line-height: 1.55; }}
.methods-content .methods-intro {{ background: var(--panel);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 12px 16px; margin-bottom: 24px; color: var(--ink); }}
.methods-section {{ margin-bottom: 28px; }}
.methods-section h3 {{ margin: 0 0 12px 0; font-size: 16px;
  color: var(--accent); padding-bottom: 4px;
  border-bottom: 2px solid var(--accent); }}
.metric {{ margin: 0 0 18px 0; }}
.metric h4 {{ font-size: 14px; margin: 0 0 4px 0; font-weight: 600;
  color: var(--ink); }}
.metric p {{ margin: 4px 0; }}
.metric .ref {{ font-size: 12.5px; color: var(--muted);
  padding: 4px 10px; margin-top: 6px; border-left: 2px solid var(--border);
  background: #fafafa; }}
.metric .note {{ font-size: 12.5px; color: #6b5d2e;
  padding: 4px 10px; margin-top: 6px;
  border-left: 2px solid #d6c87a; background: #fbf8ec; }}
.metric .ref code, .metric .note code {{ background: #ececec; padding: 1px 4px;
  border-radius: 2px; font-size: 11.5px; font-family: ui-monospace,
  SFMono-Regular, monospace; }}
.biblio {{ font-size: 12.5px; padding-left: 18px; color: var(--muted); }}
.biblio li {{ margin-bottom: 6px; }}
.biblio a {{ color: var(--accent); }}
/* The segmentation tabs row pins just below the topbar.  `--topbar-h` is
   measured in JS on load and on resize.  Only takes effect inside the
   Analysis view; when hidden, sticky is moot. */
.tabs {{ display: flex; gap: 4px; margin: 0; padding: 8px 0 12px 0;
  align-items: center;
  position: sticky; top: var(--topbar-h, 0px); z-index: 90;
  background: var(--bg); }}
.tabs button.tab {{ padding: 8px 16px; border: 1px solid var(--border);
  background: var(--panel); cursor: pointer; font-size: 13px;
  border-radius: 4px; }}
.tabs button.tab.active {{ background: var(--accent); color: white;
  border-color: var(--accent); }}
.tabs button.tab:hover:not(.active) {{ background: #f0f0f0; }}
.tabs .label {{ margin-left: auto; font-size: 12px; color: var(--muted);
  font-style: italic; }}
.panel {{ background: var(--panel); border: 1px solid var(--border);
  border-radius: 4px; padding: 12px; margin-bottom: 12px; }}
.panel.graph {{ padding: 8px 6px; }}
.panel.graph > h3 {{ padding: 0 6px; }}
.panel h3 {{ margin: 0 0 8px 0; font-size: 14px; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.05em;
  display: flex; justify-content: space-between; align-items: baseline; }}
.panel h3 .hint {{ font-size: 11px; text-transform: none; letter-spacing: 0;
  color: #999; font-weight: normal; }}
.row.charts {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 16px;
  margin-bottom: 12px; }}
@media (max-width: 1500px) {{ .row.charts {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width: 800px)  {{ .row.charts {{ grid-template-columns: 1fr; }} }}
#kpis {{ display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px 28px; align-items: start; }}
.metric-section {{ margin: 0; min-width: 0; }}
.metric-section h4 {{ margin: 0 0 6px 0; padding: 0 2px 4px 2px;
  font-size: 11px; font-weight: 600; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.08em;
  border-bottom: 1px solid var(--border); }}
/* Caveat span (kept for parity with the per-play dashboard) drops to its
   own line so narrow columns don't truncate it. */
.metric-section h4 .caveat {{ display: block; font-weight: 400;
  text-transform: none; letter-spacing: 0; font-style: italic;
  color: #aaa; font-size: 10.5px; margin: 2px 0 0 0; }}
.metrics-list {{ display: flex; flex-direction: column;
  margin: 0; padding: 0; list-style: none; font-size: 14px; }}
.metrics-list .item {{ display: flex; justify-content: space-between;
  align-items: baseline; padding: 5px 4px; gap: 8px;
  border-bottom: 1px dotted #e0e0e0; }}
.metrics-list dt {{ color: var(--muted); font-weight: 400; margin: 0;
  flex: 1 1 auto; min-width: 0; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }}
.metrics-list dd {{ margin: 0; font-weight: 600; flex: 0 0 auto;
  font-variant-numeric: tabular-nums; color: var(--ink);
  text-align: right; white-space: nowrap; }}
.metrics-list dd .alt {{ display: block; font-size: 11px; font-weight: 400;
  color: #999; margin-top: -1px; }}
#sizing-chart, #scaling-chart, #typology-chart,
#esp-avgdeg-chart {{
  width: 100%; height: 360px; }}
#composition-chart {{ width: 100%; height: 360px; }}
#chorus-beat-chart {{ width: 100%; display: block; }}
/* Plays-included selector: chip grid + toolbar.  Compact, restrained
   palette -- the selector is a working control, not a focal element. */
.selector-bar {{ display: flex; gap: 12px; align-items: center;
  margin: 0 0 8px 0; font-size: 12px; color: var(--muted); flex-wrap: wrap; }}
.selector-bar .count {{ font-weight: 600; color: var(--ink);
  font-variant-numeric: tabular-nums; }}
.selector-bar .actions {{ display: flex; gap: 6px; margin-left: auto; }}
.selector-bar .actions button {{ font-size: 11px; padding: 2px 8px;
  border: 1px solid var(--border); background: var(--panel); cursor: pointer;
  border-radius: 3px; color: var(--ink); }}
.selector-bar .actions button:hover {{ background: #f0f0f0; }}
.selector-chips {{ display: flex; flex-wrap: wrap; gap: 5px; }}
.selector-chips .chip-toggle {{ display: inline-flex; align-items: center;
  gap: 4px; padding: 3px 9px; border-radius: 11px; font-size: 11.5px;
  cursor: pointer; border: 1px solid; user-select: none;
  transition: background 0.08s, color 0.08s, border-color 0.08s; }}
.selector-chips .chip-toggle.on {{ background: var(--accent); color: white;
  border-color: var(--accent); }}
.selector-chips .chip-toggle.off {{ background: #f4f4f4; color: #999;
  border-color: #e0e0e0; text-decoration: line-through;
  text-decoration-color: #c0c0c0; }}
.selector-chips .chip-toggle:hover.on {{ background: #1750a0; }}
.selector-chips .chip-toggle:hover.off {{ background: #ebebeb; color: #555;
  text-decoration: none; }}
.selector-chips .chip-toggle .mark {{ font-size: 10px; opacity: 0.8; }}
/* The highlight dot inside each chip: a hollow ring, filled with the
   highlight colour when the play is highlighted.  Click it to toggle the
   highlight without changing whether the play is included. */
.selector-chips .chip-toggle .hl-dot {{ display: inline-block;
  width: 9px; height: 9px; border-radius: 50%; margin: 0 4px 0 1px;
  cursor: pointer; border: 1.5px solid rgba(255,255,255,0.85);
  background: transparent; box-sizing: border-box;
  vertical-align: middle; transition: transform 0.08s; }}
.selector-chips .chip-toggle .hl-dot.on {{ background: var(--highlight);
  border-color: white; }}
.selector-chips .chip-toggle.off .hl-dot {{ border-color: #bbb; }}
.selector-chips .chip-toggle .hl-dot:hover {{ transform: scale(1.35); }}
/* Sticky behaviour for the Plays-included panel: pinned just below the
   segmentation-tabs row, so toggling stays in reach while the user
   scrolls through scatters, tables, and beat charts.  Background is
   solid (otherwise the content below would show through), and a
   subtle shadow visually separates the sticky region from the
   scrolling body.  Reduced internal padding while sticky keeps the
   vertical footprint compact for screen real estate. */
.sticky-selector {{ position: sticky;
  top: calc(var(--topbar-h, 0px) + var(--tabs-h, 0px));
  z-index: 80; background: var(--panel);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
  padding: 10px 12px; }}
.sticky-selector h3 {{ margin-bottom: 4px; }}
.sticky-selector .selector-bar {{ margin-bottom: 4px; }}
.chorus-controls {{ display: flex; gap: 16px; align-items: center;
  margin: 4px 0 8px 0; font-size: 12px; color: var(--muted); }}
.chorus-controls .legend-inline {{ display: flex; gap: 12px;
  margin-left: auto; align-items: center; }}
.chorus-controls .legend-inline .swatch-gradient {{ display: inline-block;
  width: 50px; height: 10px; vertical-align: middle; margin-right: 4px;
  background: linear-gradient(to right, #fcbba1, #a50f15);
  border: 1px solid #ddd; }}
.chorus-controls .legend-inline .swatch-grey {{ display: inline-block;
  width: 10px; height: 10px; vertical-align: middle; margin-right: 3px;
  background: #bbbbbb; border: 1px solid #ddd; }}
/* Same hatch as the chart's text-not-transmitted cells. */
.chorus-controls .legend-inline .swatch-hatch {{ display: inline-block;
  width: 10px; height: 10px; vertical-align: middle; margin-right: 3px;
  background: repeating-linear-gradient(45deg, #a50f15 0 1.5px,
                                        #fde0dd 1.5px 4px);
  border: 1px solid #ddd; }}
.small-multiples {{ display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 10px; }}
.small-multiples .sm {{ background: #fafafa; border: 1px solid #f0f0f0;
  border-radius: 3px; padding: 4px 6px; }}
.small-multiples .sm .title {{ font-size: 11px; color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  margin-bottom: 2px; }}
.small-multiples .sm svg {{ width: 100%; height: 110px; display: block; }}
table {{ width: 100%; border-collapse: separate; border-spacing: 0;
  font-size: 12px; }}
th, td {{ padding: 4px 8px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
th {{ background: #f8f8f8; font-weight: 600; cursor: pointer; user-select: none;
  position: sticky; top: 0; z-index: 1;
  box-shadow: inset 0 -1px 0 var(--border); }}
th:hover {{ background: #f0f0f0; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
/* Per-chart fullscreen toggle.  Pattern mirrors the per-play dashboard:
   a small button in the h3 of every .panel.graph; when clicked, adds the
   chart-fullscreen class which switches the panel to position:fixed
   filling the viewport.  Esc exits.  Dot radius and axis fonts in
   drawScatter scale up when the SVG width exceeds 900px (i.e., in
   fullscreen). */
.fullscreen-toggle {{ float: right; font-size: 11px; padding: 2px 10px;
  border: 1px solid var(--border); background: white; cursor: pointer;
  border-radius: 3px; margin-left: 8px; }}
.fullscreen-toggle:hover {{ background: #f0f0f0; }}
.panel.graph.chart-fullscreen {{ position: fixed; inset: 0; z-index: 1000;
  margin: 0; padding: 16px 24px; background: var(--panel);
  overflow: auto; max-width: none; }}
/* Scatters and composition: SVG fills the viewport (the chart has no
   intrinsic vertical content, so we set height explicitly). */
.panel.graph.chart-fullscreen #sizing-chart,
.panel.graph.chart-fullscreen #scaling-chart,
.panel.graph.chart-fullscreen #typology-chart,
.panel.graph.chart-fullscreen #esp-avgdeg-chart,
.panel.graph.chart-fullscreen #composition-chart {{
  width: 100%; height: calc(100vh - 270px); max-width: none; }}
/* Chorus-beat chart: set its own height in JS (rows × rowH), but let
   it fill the viewport width when fullscreened. */
.panel.graph.chart-fullscreen #chorus-beat-chart {{
  width: 100%; max-width: none; }}
.panel.graph.chart-fullscreen .chorus-controls {{ margin-bottom: 12px; }}
/* In fullscreen, the shared control strips are MOVED into the maximised
   panel (see _fsMoveControlsInto) and hosted here at the top, so the user
   can change segmentation / network model / aggregation / play selection
   without leaving fullscreen.  Override the strips' sticky positioning and
   cap the chip list so the chart keeps a predictable height. */
.fs-controls {{ margin: 4px 0 12px; display: flex; flex-direction: column;
  gap: 8px; }}
.chart-fullscreen #seg-tabs {{ position: static; top: auto; }}
.chart-fullscreen #plays-selector-panel {{ position: static; top: auto;
  box-shadow: none; margin: 0; padding: 8px 12px; }}
.chart-fullscreen #plays-selector-panel h3 .hint {{ display: none; }}
.chart-fullscreen #plays-selector {{ max-height: 64px; overflow-y: auto; }}
/* Beat-multiples grid expands naturally via grid auto-fit; the small
   svgs scale themselves via clientWidth.  Re-render on fullscreen
   toggle picks up the new container width.  In fullscreen we widen and
   heighten each cell substantially so every segment-transition is legible
   — important in word-position mode, where dense plays pack many vertices
   into the line. */
.panel.graph.chart-fullscreen .small-multiples {{
  grid-template-columns: repeat(auto-fit, minmax(520px, 1fr)); gap: 16px; }}
.panel.graph.chart-fullscreen .small-multiples .sm svg {{ height: 170px; }}
.panel.graph.chart-fullscreen .small-multiples .sm .title {{ font-size: 13px; }}

/* Network-model radio fieldset.  Compact, inline with the segmentation
   tabs.  Three options stacked horizontally with subtle group framing
   so the user can see the active network model at a glance. */
.mute-mode-radio {{ border: 1px solid var(--border); border-radius: 4px;
  padding: 2px 8px 4px 8px; margin: 0; display: inline-flex; gap: 10px;
  align-items: baseline; flex-wrap: wrap; font-size: 12px; }}
.mute-mode-radio legend {{ font-size: 11px; color: var(--muted);
  padding: 0 4px; font-weight: 500; }}
.mute-mode-radio label {{ display: inline-flex; align-items: baseline;
  gap: 3px; cursor: pointer; }}
.mute-mode-radio label input {{ margin: 0 2px 0 0; }}
.mute-mode-radio .detail {{ color: #999; font-size: 11px;
  font-style: italic; }}
/* Global partOf-aggregation toggle, sat inline beside the network-model
   fieldset in the seg-tabs strip.  Same type scale as the radio labels. */
.agg-toggle {{ display: inline-flex; align-items: baseline; gap: 3px;
  cursor: pointer; font-size: 12px; }}
.agg-toggle input {{ margin: 0 2px 0 0; }}
.agg-toggle .detail {{ color: #999; font-size: 11px; font-style: italic; }}
tr.row-link {{ cursor: pointer; }}
tr.row-link:hover td {{ background: #fffce8; }}
.scroll {{ max-height: 520px; overflow-y: auto; }}
text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
/* Default stroke / stroke-width come from drawScatter's attr() calls.
   The :hover rule still wins (CSS > presentation attribute) on hover. */
.dot {{ cursor: pointer; }}
.dot:hover {{ stroke: black !important; stroke-width: 1.8; }}
.legend {{ font-size: 11px; color: var(--muted); margin-top: 8px;
  display: flex; gap: 14px; flex-wrap: wrap; }}
.legend .swatch {{ display: inline-block; width: 10px; height: 10px;
  vertical-align: middle; margin-right: 3px; border-radius: 2px; }}
</style>
<!--FIGURE_EXPORT_CSS-->
</head>
<body>
<div class="topbar">
<header>
  <h1>{title}</h1>
  <div class="sub">{subtitle}</div>
  <div class="active-filters" id="active-filters"></div>
</header>
<nav class="view-tabs">
  <button class="view-tab active" data-view="analysis">Analysis</button>
  <button class="view-tab" data-view="methods">Methods &amp; formulas</button>
</nav>
</div>
<main class="view view-analysis" data-view="analysis">
  <div class="tabs" id="seg-tabs">
    <span class="label">all panels react to the segmentation tab</span>
    <fieldset class="mute-mode-radio" style="margin-left: 16px;">
      <legend>Network model:</legend>
      <label><input type="radio" name="mute-mode" value="full" checked>
        stage co-presence
        <span class="detail">(all on-stage characters as nodes)</span></label>
      <label><input type="radio" name="mute-mode" value="p-speaking">
        speaking cast on play level
        <span class="detail">(drop play-level mutes)</span></label>
      <label><input type="radio" name="mute-mode" value="s-speaking">
        speaking cast on segment level
        <span class="detail">(only segment-active speakers)</span></label>
    </fieldset>
    <label class="agg-toggle" style="margin-left: 12px;">
      <input type="checkbox" id="aggregate-chorus"> aggregate chorus halves
      <span class="detail">(partOf: collapse semi-choruses to one node, everywhere)</span>
    </label>
  </div>

  <div class="panel sticky-selector" id="plays-selector-panel">
    <h3>Plays included
      <span class="hint">toggle chips to include / exclude plays &middot;
        all panels, scatters, tables, and median crosshairs recompute against
        the active subset</span>
    </h3>
    <div class="selector-bar">
      <span>Selected: <span class="count" id="plays-count">&mdash;</span></span>
      <span class="actions">
        <button id="sel-all">select all</button>
        <button id="sel-none">select none</button>
        <button id="sel-invert">invert</button>
        <button id="clear-highlights" title="remove every highlight">clear highlights</button>
      </span>
    </div>
    <div id="plays-selector" class="selector-chips"></div>
  </div>

  <div class="panel" data-comparison-export>
    <h3>Corpus summary</h3>
    <div id="kpis"></div>
  </div>

  <div class="row charts">
    <div class="panel graph">
      <h3>Density &times; order
        <span class="hint">red lines = pairs with &Delta;n &le; 5 (local-neighbourhood density variation)
          <label style="margin-left: 8px;">
            <input type="checkbox" id="show-pair-lines"> show pair-lines
          </label>
          <label style="margin-left: 8px;"
                 title="tone = how many others a character shares the stage with, on average">
            <input type="checkbox" id="tone-by-degree"> colour by average degree
          </label>
        </span>
      </h3>
      <svg id="sizing-chart"></svg>
    </div>
    <div class="panel graph">
      <h3>Average degree &times; order
        <span class="hint">do interactions per character scale with the cast, or saturate?</span>
      </h3>
      <svg id="scaling-chart"></svg>
    </div>
    <div class="panel graph">
      <h3>Drama-dynamics typology
        <span class="hint">drama-change rate &times; &sigma; &middot; Fischer et al. 2017, Figs. 8&ndash;9 (high- vs low-dynamic plays)</span>
      </h3>
      <svg id="typology-chart"></svg>
    </div>
    <div class="panel graph">
      <h3>Effective speakers &times; average degree
        <span class="hint">how many voices carry the play &times; how many others a character meets</span>
      </h3>
      <svg id="esp-avgdeg-chart"></svg>
    </div>
  </div>

  <div class="panel graph">
    <h3>Cast composition
      <span class="hint">stacked bars per play &middot; sorted by total cast</span>
    </h3>
    <svg id="composition-chart"></svg>
    <div class="legend">
      <span><span class="swatch" style="background: var(--speaker)"></span>speakers</span>
      <span><span class="swatch" style="background: var(--mute)"></span>mutes</span>
    </div>
  </div>

  <div class="panel graph">
    <h3>Beat-chart small multiples
      <span class="hint">segment-change rate per play (orange line = drama-change rate)</span>
    </h3>
    <label style="font-size:11px; color:var(--muted); display:flex; align-items:center; gap:6px; cursor:pointer; margin: 0 0 10px;">
      <input type="checkbox" id="beat-xmode"> space x-axis by word position
      <span style="opacity:0.8;">(transitions placed at their stage-time, not evenly)</span>
    </label>
    <div id="beat-multiples" class="small-multiples"></div>
  </div>

  <div class="panel graph">
    <h3>Chorus presence across the play
      <span class="hint">one row per chorus &middot; x normalised per play so distribution shapes are comparable
      &middot; sorted genre &rarr; author &rarr; title</span>
    </h3>
    <div class="chorus-controls">
      <span class="legend-inline">
        <span><span class="swatch-grey" data-swatch="solid"></span>present, silent</span>
        <span><span class="swatch-hatch" data-swatch="hatch"
                    data-colors="#a50f15 #fde0dd"></span>performs, text not transmitted</span>
        <span><span class="swatch-gradient" data-swatch="ramp"
                    data-colors="#fcbba1 #a50f15"></span>speaking (words, &radic; scale)</span>
      </span>
    </div>
    <svg id="chorus-beat-chart"></svg>
  </div>

  <div class="panel">
    <h3>Plays
      <span class="hint">click any row to open the per-play dashboard
        &middot; <code>seg</code> = segments on the active model's spine
        (under sd the mutes-out models fold boundaries they cannot see, so
        it drops when you switch model; fixed for large-seq / middle-seq)</span>
    </h3>
    <div class="scroll"><table id="plays-table"></table></div>
  </div>
</main>

<main class="view view-methods hidden" data-view="methods">
  <!--METHODS_HTML-->
</main>

<script>
const DATA = {data_json};

// Dashboard-internal key for state Sets / Maps.  The drill-down href is
// the one field guaranteed distinct: the writer allocates each play a
// directory no other play holds, so two plays that share an English title
// -- one title used by two authors, say -- still get a chip, a dot and a
// colour of their own.  Keying off the title merged them into one.  Falls
// back to the titles and to p.id where no dashboard was written
// (--no-dashboard).
function _playKey(p) {{
  return p.dashboard_href || p.title_en || p.title_grc || p.id;
}}

const MODE_ORDER = ["sd", "large-seq", "middle-seq"];

// A mode is "available" if at least one play has it.
const AVAILABLE_MODES = MODE_ORDER.filter(m =>
  DATA.plays.some(p => p.segmentations && p.segmentations[m]));

// Labels and details for the three mute modes -- single source of truth
// for the active-filters chip strip, hint text, and the radio fieldset.
const MUTE_MODE_LABELS = {{
  "full":       {{ label: "stage co-presence",
                   detail: "all on-stage characters as nodes" }},
  "p-speaking": {{ label: "speaking cast on play level",
                   detail: "drop play-level mutes" }},
  "s-speaking": {{ label: "speaking cast on segment level",
                   detail: "only segment-active speakers" }},
}};

// Provenance for the figure exporter: the caption stamped into every exported
// SVG/PNG, and the slug that names the file.  A corpus chart depends on the
// segmentation, the network model, the aggregation state and -- unlike the
// per-play dashboard -- on which plays are currently selected, since the
// medians are defined relative to that subset.  An image
// carries none of it.  See figure_export.py.
const SEG_LABELS_LONG = {{
  "sd": "stage-direction segmentation",
  "large-seq": "large-sequence segmentation",
  "middle-seq": "middle-sequence segmentation",
}};
function figureProvenance(panel) {{
  const ml = MUTE_MODE_LABELS[STATE.muteMode] || MUTE_MODE_LABELS.full;
  const total = (DATA.plays || []).length;
  const shown = STATE.selectedPlays ? STATE.selectedPlays.size : total;
  const bits = [shown === total ? total + " plays"
                                : shown + " of " + total + " plays",
                SEG_LABELS_LONG[STATE.seg] || STATE.seg,
                ml.label,
                STATE.aggregateChorus ? "collectives aggregated"
                                      : "collectives not aggregated"];
  // The beat multiples can be spaced two ways, and the shapes differ enough
  // that a figure has to say which.
  if (panel && panel.querySelector("#beat-multiples")) {{
    bits.push(STATE.beatXMode === "word" ? "x-axis: word position"
                                         : "x-axis: transition index");
  }}
  // Coloured by average degree, the dots' fill is data; a figure must say so.
  if (panel && panel.querySelector("#sizing-chart") && STATE.toneByDegree) {{
    bits.push("dots coloured by average degree");
  }}
  // A ring on a scatter means the reader highlighted that play; the figure
  // names which, so the ring needs no legend.
  if (panel && panel.querySelector("svg.scatter")) {{
    const marked = activePlays().filter(isHighlighted).map(shortTitle);
    if (marked.length) bits.push("highlighted: " + marked.join(", "));
  }}
  return {{
    caption: bits.join(" \\u00b7 "),
    slug: ["corpus", STATE.seg, STATE.muteMode,
           STATE.aggregateChorus ? "agg" : "",
           shown === total ? "" : shown + "-plays"].filter(Boolean).join("-"),
  }};
}}

// Every play x segmentation x network model x aggregation state in the
// corpus, as one table.  This is the comparison the dashboard can only show
// one cell of at a time; the payload already carries all of it.  Consumed by
// figure_export.py.  Independent of the play selector on purpose: the file
// is the whole corpus as computed, and a subset is a question for the
// spreadsheet, not for the export.
function figureComparisonRows() {{
  // `id` first: the one column that tells two plays of one title apart, and
  // the key that joins a row to that play's metrics.json.
  const header = ["id", "play", "author", "segmentation", "model", "aggregated",
    "order", "edges", "density", "avg_degree", "max_degree", "diameter",
    "avg_path_length", "avg_clustering", "components", "segments",
    "drama_change_rate", "all_in_index", "final_segment_cast_share",
    "max_simultaneous_speakers", "gini_words", "effective_speakers",
    "top_speaker", "top_speaker_word_share", "top_speaker_temporal_gini"];
  const round = v => (typeof v === "number" && !Number.isInteger(v))
    ? +v.toFixed(6) : v;
  const rows = [];
  (DATA.plays || []).forEach(function (p) {{
    Object.keys(p.segmentations || {{}}).forEach(function (spine) {{
      const blk = p.segmentations[spine] || {{}};
      // Empty means "not aggregated" in both dashboards' exports, so the
      // column filters the same way in either file; the per-play export can
      // name the groups it collapsed, which the corpus payload does not
      // carry, so "all" stands for its global toggle.
      const entries = [["full", "", blk]];
      if (blk.agg) entries.push(["full", "all", blk.agg]);
      ["p-speaking", "s-speaking"].forEach(function (model) {{
        const b = blk[model];
        if (!b) return;
        entries.push([model, "", b]);
        if (b.agg) entries.push([model, "all", b.agg]);
      }});
      entries.forEach(function (e) {{
        const model = e[0], agg = e[1], b = e[2];
        const si = b.segment_indices || {{}};
        const sd = b.speech_distribution || {{}};
        rows.push([p.id || "", p.title_en || p.id, p.author || "", spine, model, agg,
          b.size, b.numEdges, round(b.density), round(b.averageDegree),
          b.maxDegree, b.diameter, round(b.averagePathLength),
          round(b.averageClustering), b.numConnectedComponents,
          b.num_segments, round(mean(b.change_rates || [])),
          round(si.all_in_index), round(si.final_segment_cast_share),
          si.max_simultaneous_speakers, round(sd.gini_words),
          round(sd.effective_speakers),
          (sd.top_speaker_ids || []).join(", "),
          round(sd.top_speaker_word_share),
          round(sd.top_speaker_temporal_gini)].map(v => v == null ? "" : v));
      }});
    }});
  }});
  return {{ name: (DATA.name || document.title || "corpus") + "-all-configurations",
           header: header, rows: rows }};
}}

const STATE = {{
  seg: AVAILABLE_MODES[0] || "sd",
  // Three-state network model.  See dashboard.py for the orthogonal
  // (include_mutes, segment_cast) axes underneath: stage = (T, presence);
  // p-speaking = (F, stage); s-speaking = (F, speaking).  The radio
  // group in the seg-tabs row drives this.
  muteMode: "full",
  // Beat-chart small-multiples x-axis mode.
  //   "segment" -> evenly spaced transition index (default)
  //   "word"   -> each transition placed at its cumulative word position
  //                (stage-time), so doorway flurries collapse and turnover
  //                between long scenes stands alone.  Per play.
  beatXMode: "segment",
  // Global partOf aggregation: True = collapse chorus halves (e.g.
  // Lysistrata's chorosGeronton + chorosGynaikon -> choros) into a single
  // node everywhere; False = treat each half separately.  Routed through
  // segOf(p), so it cascades through every scatter, the
  // pair-lines, the composition bars, the KPI ranges, the plays table and
  // the beat multiples -- not just the chorus heat-map.  Plays without
  // aggregable partOf groups are unaffected (segOf keeps their raw block).
  aggregateChorus: false,
  // Only consumed by the density x order chart: when True, draw thin
  // red lines connecting every pair of plays with similar order
  // (Delta n <= 5).  Methodologically these visualise the
  // local-neighbourhood density variation -- the corpus's natural
  // "noise floor" of density variation among plays of similar order.
  // Plays without nearby-order neighbours (e.g. Knights at n=8) have
  // no incident lines.  Lysistrata's lines are visibly taller than any
  // other pair's, which is the visual signature of the methodological
  // argument.  Off by default, like the tone below: the chart opens as
  // the plain density x order plot.
  showPairLines: false,
  // Density x order: fill the dots by average degree.
  toneByDegree: false,
  // Set of play ids currently included.  Initialised to the full
  // corpus on load.  Every consumer of activePlays() filters through
  // this -- so unticking a chip in the selector cascades through KPIs,
  // every scatter chart's median crosshair, the beat
  // multiples, the chorus chart, and the plays table at once.  This is
  // by design: the "corpus median" is defined relative to whatever
  // subset is held in mind, and it is always the subset on screen.
  selectedPlays: new Set(DATA.plays.map(p => _playKey(p))),
  // Plays marked by the reader, keyed like selectedPlays.  A highlighted
  // play gets a ring on every scatter and is always labelled, and the
  // caption of an exported scatter names it.  One mark, not a palette: a
  // colour code the reader invents has no legend and says nothing in an
  // exported figure, while "highlighted: Lys." says exactly what it is.
  highlighted: new Set(),
}};

function fmt(v, dp=3) {{
  if (v == null) return "";
  if (typeof v !== "number") return v;
  if (Number.isInteger(v)) return v.toLocaleString();
  return v.toFixed(dp);
}}
function mean(xs) {{
  if (!xs.length) return 0;
  return xs.reduce((s, x) => s + x, 0) / xs.length;
}}
function stdev(xs, mu) {{
  if (xs.length < 2) return 0;
  const m = mu == null ? mean(xs) : mu;
  return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / xs.length);
}}
function median(xs) {{
  if (!xs.length) return 0;
  const s = xs.slice().sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}}
function segOf(p) {{
  // Active segmentation block for the currently-selected network model.
  // Each non-default mode (p-speaking, s-speaking) lives in a parallel
  // sub-dict on the segmentation entry, with the same field shape as
  // the top-level (stage-mode) fields, so every consumer below (KPI,
  // scatter, bar chart, table, beat charts) works without case-splits.
  // Missing sub-dicts fall back to the top-level stage view.
  const base = (p.segmentations || {{}})[STATE.seg];
  if (!base) return null;
  const m = STATE.muteMode || "full";
  let block = base;
  // Bracket access: the model keys contain a hyphen.
  if (m === "p-speaking" && base["p-speaking"]) block = base["p-speaking"];
  else if (m === "s-speaking" && base["s-speaking"]) block = base["s-speaking"];
  // Global partOf aggregation: swap in the nested agg counterpart when the
  // "aggregate chorus halves" toggle is on and an aggregated view exists
  // for this play (semi-choruses collapsed to one node).  Plays without
  // aggregable groups have no `.agg`, so they keep the raw block.
  if (STATE.aggregateChorus && block.agg) block = block.agg;
  return block;
}}

// Active-filter chip strip in the header.  Always shows the current network
// model so any screenshot documents the methodological configuration.
function renderActiveFilters() {{
  const host = document.getElementById("active-filters");
  if (!host) return;
  const ml = MUTE_MODE_LABELS[STATE.muteMode] || MUTE_MODE_LABELS.full;
  const modelLabel = ml.label
    + ' <span class="detail">(' + ml.detail + ')</span>';
  let html = '<span class="filter-chip">' + modelLabel + '</span>';
  // Subset chip: shown only when the selection is non-full, so default
  // screenshots stay uncluttered but ad-hoc subsets document themselves.
  const total = DATA.plays.length;
  const sel = STATE.selectedPlays ? STATE.selectedPlays.size : total;
  if (sel !== total) {{
    html += ' <span class="filter-chip">subset '
         + '<span class="detail">' + sel + ' / ' + total + ' plays</span></span>';
  }}
  host.innerHTML = html;
  // Topbar may have grown / shrunk because of the chip strip wrap;
  // re-measure so the sticky tabs and selector pin at the right offsets.
  if (typeof updateStickyOffsets === "function") updateStickyOffsets();
}}

// The plays on screen -- and, the same set, the plays every reference
// quantity is computed from: the median crosshairs and the KPI ranges.
// There is deliberately no second set.  One existed, to show a play
// without letting it set the reference; a median ignores an outlier by
// itself, so it moved a crosshair by at most a few per cent of an axis.
function activePlays() {{
  return DATA.plays.filter(p => segOf(p)
    && (!STATE.selectedPlays || STATE.selectedPlays.has(_playKey(p))));
}}
function isHighlighted(p) {{
  return STATE.highlighted.has(_playKey(p));
}}

// -------------------------------------------------------------------- plays selector
//   Chip grid: one toggle per play.  Selected chips are coloured;
//   deselected chips are grey/strikethrough.  Quick actions: all / none /
//   invert.  Re-renders the whole dashboard on every toggle, which is
//   cheap since the SVGs are small and the data already lives client-side.
function renderPlaysSelector() {{
  const host = d3.select("#plays-selector");
  // Stable display order: DATA.plays' natural order (alphabetic by id
  // via the corpus assembler).  No genre/author sort here -- the chip
  // strip is a flat selector, not the chorus-chart's sorted view.
  const plays = DATA.plays.slice();
  host.selectAll("*").remove();
  // Click on the chip body includes or excludes the play.  Click on the
  // highlight dot (left inside the chip) toggles the highlight without
  // changing whether the play is included.
  function togglePlay(key) {{
    if (STATE.selectedPlays.has(key)) STATE.selectedPlays.delete(key);
    else STATE.selectedPlays.add(key);
  }}
  function toggleHighlight(key) {{
    if (STATE.highlighted.has(key)) STATE.highlighted.delete(key);
    else STATE.highlighted.add(key);
  }}

  const chips = host.selectAll(".chip-toggle").data(plays, p => _playKey(p))
    .enter().append("span")
    .attr("class", p => STATE.selectedPlays.has(_playKey(p))
                          ? "chip-toggle on" : "chip-toggle off")
    .attr("title", p => {{
      const state = STATE.selectedPlays.has(_playKey(p)) ? "included" : "excluded";
      return (p.author || "") + (p.author ? " - " : "")
           + (p.title_en || p.id) + " - " + state
           + (isHighlighted(p) ? ", highlighted" : "")
           + "\\n(click body: include / exclude; click dot: highlight)";
    }})
    .on("click", (event, p) => {{
      // Ignore clicks on the highlight dot -- that handler runs separately
      // and stops propagation.  Without this guard d3's binding would
      // also fire the chip body handler on a dot click.
      if (event.target.classList.contains("hl-dot")) return;
      togglePlay(_playKey(p));
      renderActiveFilters();
      render();
    }});

  // State mark (Unicode check / cross).
  chips.append("span").attr("class", "mark")
    .text(p => STATE.selectedPlays.has(_playKey(p)) ? "\\u2713" : "\\u2715");

  // Highlight dot: small clickable ring, filled when the play is
  // highlighted.  Propagation stopped so it does not also toggle the
  // play's inclusion.
  chips.append("span")
    .attr("class", p => "hl-dot" + (isHighlighted(p) ? " on" : ""))
    .on("click", (event, p) => {{
      event.stopPropagation();
      toggleHighlight(_playKey(p));
      render();
    }});

  chips.append("span").attr("class", "chip-label").text(p => shortTitle(p));

  // Counter: "N / total".
  document.getElementById("plays-count").textContent =
    STATE.selectedPlays.size + " / " + plays.length;
}}

// -------------------------------------------------------------------- tabs
function renderTabs() {{
  const tabs = d3.select("#seg-tabs");
  const labels = {{ sd: "Stage directions", "large-seq": "large-seq", "middle-seq": "middle-seq" }};
  tabs.selectAll("button.tab")
    .data(AVAILABLE_MODES, d => d)
    .join(
      enter => enter.insert("button", ".label").attr("class", "tab")
        .text(d => labels[d] || d)
        .on("click", (_, d) => {{ STATE.seg = d; render(); }}),
      update => update,
      exit => exit.remove()
    )
    .classed("active", d => d === STATE.seg);
}}

// -------------------------------------------------------------------- KPIs
function renderKPIs() {{
  const ps = activePlays();
  if (!ps.length) {{ d3.select("#kpis").selectAll("*").remove(); return; }}

  const get = (acc) => ps.map(p => acc(segOf(p))).filter(v => v != null && !Number.isNaN(v));
  const dens   = get(s => s.density);
  const aDeg   = get(s => s.averageDegree);
  // True drama-change rate from change_rates.  A play with no transitions
  // has no rate and is left out; one whose casts never change has a rate of
  // 0, which is a value and stays in the range, as it does in the table.
  const dcrs   = ps.map(p => segOf(p).change_rates || [])
                   .filter(r => r.length).map(mean);
  const finals = get(s => s.segment_indices && s.segment_indices.final_segment_cast_share);
  const sizes  = get(s => s.size);
  const speakers = get(s => (s.demographics && s.demographics.speakers) || 0);
  const mutes    = get(s => (s.demographics && s.demographics.mutes) || 0);
  const topShare = get(s => (s.speech_distribution && s.speech_distribution.top_speaker_word_share) || 0);
  const gini     = get(s => (s.speech_distribution && s.speech_distribution.gini_words) || 0);

  function range(xs) {{
    if (!xs.length) return "\\u2014";
    return fmt(d3.min(xs)) + " \\u2013 " + fmt(d3.max(xs)) + " (mean " + fmt(mean(xs)) + ")";
  }}

  const sections = [
    {{ title: "Overview", items: [
      {{ k: "plays",                v: ps.length }},
      {{ k: "total characters",     v: d3.sum(sizes) }},
      {{ k: "total segments",       v: d3.sum(get(s => s.num_segments)) }},
      {{ k: "total words spoken",  v: d3.sum(get(s => (s.speech_distribution || {{}}).total_words_spoken || 0)) }},
    ]}},
    {{ title: "Network", items: [
      {{ k: "order (range)",       v: range(sizes) }},
      {{ k: "density",             v: range(dens) }},
      {{ k: "average degree",      v: range(aDeg) }},
    ]}},
    {{ title: "Composition", items: [
      {{ k: "speakers (range)",    v: range(speakers) }},
      {{ k: "mutes (range)",       v: range(mutes) }},
      // No mutes, no ratio: both speaking models drop the mutes from every
      // count (Methods \\u00a73), and dividing by max(1, 0) printed the
      // corpus speaker total as if it were one.
      {{ k: "speaker / mute ratio",
        v: d3.sum(mutes) > 0 ? fmt(d3.sum(speakers) / d3.sum(mutes), 2)
                             : "\\u2014" }},
    ]}},
    {{ title: "Plot dynamics", items: [
      {{ k: "drama-change rate",   v: range(dcrs), beat: true }},
      {{ k: "final seg. cast share", v: range(finals), beat: true }},
      {{ k: "top-speaker share",   v: range(topShare) }},
      {{ k: "Gini (words)",       v: range(gini) }},
    ]}},
  ];

  const root = d3.select("#kpis");
  root.selectAll("*").remove();
  const secs = root.selectAll(".metric-section").data(sections).enter()
    .append("section").attr("class", "metric-section");
  secs.append("h4").text(d => d.title);
  const dls = secs.append("dl").attr("class", "metrics-list");
  const its = dls.selectAll(".item").data(d => d.items).enter()
    .append("div").attr("class", d => "item" + (d.beat ? " beat" : ""));
  its.append("dt").text(d => d.k);
  const dds = its.append("dd");
  dds.append("span").attr("class", "primary").text(d => d.v);
}}

// A pair-line as SVG path data: straight wherever a reader can follow it,
// bowed where a straight segment would be lost.  There are two ways to lose
// one.  It can run under a third play's marker: plays of equal order stack
// on one vertical, so the line from A to C passes through B, lies on top of
// the line from A to B, and its only distinguishing stretch disappears under
// the dots -- A-C reads as A-B.  Or it can be so short that its own two
// markers cover it.  In either case the line bows far enough to clear what
// hid it, and always to the left, away from the labels, which sit to the
// right of the dots.  P, Q and `others` are screen positions [x, y].
function pairLinePath(P, Q, others, dotR) {{
  const dx = Q[0] - P[0], dy = Q[1] - P[1];
  const len = Math.hypot(dx, dy);
  const straight = "M" + P[0] + "," + P[1] + "L" + Q[0] + "," + Q[1];
  if (len === 0) return straight;
  // Margin beyond the marker's edge.  Sized at the obstruction's projection,
  // the curve's true nearest approach falls a little short of it, so the
  // margin is generous enough to survive that and still read as a gap.
  const clear = dotR + 7;
  // A quadratic curve whose control point sits b off the chord's midpoint
  // stands 2t(1-t)b off the chord at parameter t; size b so that it clears
  // the worst obstruction where that obstruction actually is.
  let need = 0;
  for (const O of others) {{
    const t = ((O[0] - P[0]) * dx + (O[1] - P[1]) * dy) / (len * len);
    if (t <= 0 || t >= 1) continue;
    const dist = Math.abs((O[0] - P[0]) * dy - (O[1] - P[1]) * dx) / len;
    if (dist >= clear) continue;
    const tc = Math.min(0.85, Math.max(0.15, t));
    need = Math.max(need, (clear + dist) / (2 * tc * (1 - tc)));
  }}
  if (len - 2 * dotR < Math.max(8, dotR)) need = Math.max(need, 2 * clear);
  if (need === 0) return straight;
  let nx = -dy / len, ny = dx / len;
  if (nx > 0 || (nx === 0 && ny > 0)) {{ nx = -nx; ny = -ny; }}
  const b = Math.min(need, 6 * dotR);
  const cx = (P[0] + Q[0]) / 2 + nx * b, cy = (P[1] + Q[1]) / 2 + ny * b;
  return "M" + P[0] + "," + P[1] + "Q" + cx + "," + cy + " " + Q[0] + "," + Q[1];
}}

// One tone scale for every view of density x order coloured by average
// degree.  Anchored to the corpus's typical average degree over all spines,
// models and aggregation states -- not the active view's -- so a tone means
// the same number whichever view is showing, and a play that stands out in
// one view and not in another visibly does so.  Rounded to a power of two,
// so the legend reads 4 / 8 / 16 rather than 3.0 / 6.1 / 12.2.
const DEGREE_ANCHOR = (function() {{
  const ks = [];
  const take = b => {{
    if (b && typeof b.averageDegree === "number" && b.averageDegree > 0)
      ks.push(b.averageDegree);
  }};
  for (const p of DATA.plays || []) {{
    for (const s of Object.values(p.segmentations || {{}})) {{
      for (const b of [s, s && s["p-speaking"], s && s["s-speaking"]]) {{
        take(b);
        take(b && b.agg);
      }}
    }}
  }}
  if (!ks.length) return 8;
  return Math.pow(2, Math.round(Math.log2(median(ks))));
}})();

// -------------------------------------------------------------------- scatter helpers
//   `extras` (optional) is called as extras(svg, x, y, ps, geom) after the
//   axes and median crosshair are drawn but before the dots, so background
//   shapes (the pair-lines on density x order) sit behind the data.
//   Highlighted plays get a ring and are always labelled, in every mode.
//   `opts.tone` (optional) fills each dot by a third quantity instead of the
//   one accent colour:  {{value: s => number, domain: [lo, hi], legend:
//   [values marked on the legend's bar], caption: text, title: tooltip
//   name}}.  Dots keep one size either way.
function drawScatter(selector, accX, accY, labelX, labelY, extras, opts) {{
  const tone = (opts || {{}}).tone || null;
  const svg = d3.select(selector);
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.selectAll("*").remove();
  // Marked, so a figure's caption knows the panel is a scatter and names
  // any highlighted play.
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`).classed("scatter", true);
  const M = {{top: 16, right: 18, bottom: 36, left: 50}};
  // The plays on screen, which are also the plays the median crosshair is
  // computed from: activePlays() = selectedPlays.
  const ps = activePlays().map(p => ({{p, x: accX(segOf(p)), y: accY(segOf(p))}}))
                          .filter(d => d.x != null && d.y != null && !Number.isNaN(d.x) && !Number.isNaN(d.y));
  if (!ps.length) return;

  // Size-responsive constants: when the SVG is large (typically in
  // fullscreen mode the width exceeds ~900px), scale the dot radius,
  // axis labels, and play labels up proportionally so the chart reads
  // from a distance during a presentation.  In normal grid view
  // (w ~ 400 px) the existing compact values are used.
  const isBig = w > 900;
  const dotR = isBig ? 9 : 5;
  const axisLabelFont = isBig ? 14 : 11;
  const tickFont      = isBig ? 12 : 10;
  const playLabelFont = isBig ? 14 : 10;
  const axisTickCount = isBig ? 8 : 6;

  // Tone, when asked for, carries a quantity in the dots' fill, light to
  // dark, over a fixed domain -- never the active view's own range, which
  // would stretch whatever spread a view has, however small, across the
  // whole ramp.  The colours are viridis, reversed so that darker means
  // more.  Of the scales measured it changes at the most even perceptual
  // rate (CIEDE2000 8.1-12.4 per tenth of the domain), so equal differences
  // look alike wherever they fall, and over the same domain it shows about
  // twice the difference a single blue did: 20.6 against 9.5 between the
  // lowest and highest of the ten comedies below Lysistrata on the default
  // view.  Its yellowest tenth is left out, as too pale against the page.
  const toneFor = tone
    ? (v => {{
        const [lo, hi] = tone.domain;
        const t = Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
        return d3.interpolateViridis(0.9 * (1 - t));
      }})
    : null;

  const xExt = d3.extent(ps, d => d.x);
  const yExt = d3.extent(ps, d => d.y);
  const padX = Math.max(0.02, (xExt[1] - xExt[0]) * 0.08);
  const padY = Math.max(0.02, (yExt[1] - yExt[0]) * 0.08);
  const x = d3.scaleLinear().domain([xExt[0] - padX, xExt[1] + padX]).range([M.left, w - M.right]);
  const y = d3.scaleLinear().domain([yExt[0] - padY, yExt[1] + padY]).range([h - M.bottom, M.top]);

  const xAxisG = svg.append("g").attr("transform", `translate(0,${{h - M.bottom}})`)
     .call(d3.axisBottom(x).ticks(axisTickCount));
  xAxisG.selectAll("text").attr("font-size", tickFont);
  const yAxisG = svg.append("g").attr("transform", `translate(${{M.left}},0)`)
     .call(d3.axisLeft(y).ticks(axisTickCount));
  yAxisG.selectAll("text").attr("font-size", tickFont);
  svg.append("text").attr("x", w / 2).attr("y", h - 6).attr("text-anchor", "middle")
     .attr("fill", "var(--muted)").attr("font-size", axisLabelFont).text(labelX);
  svg.append("text").attr("x", -h / 2).attr("y", 14)
     .attr("transform", "rotate(-90)")
     .attr("text-anchor", "middle").attr("fill", "var(--muted)")
     .attr("font-size", axisLabelFont).text(labelY);

  // Median reference crosshair: descriptive, not a regression.  Drawn
  // before the dots so the points sit on top.  Lines only -- no labels,
  // so the chart stays uncluttered (medians are also reported in the KPI
  // panel and the plays table).  Computed over the plays on screen, so the
  // reference is always exactly what the reader sees.
  {{
    const medX = median(ps.map(d => d.x));
    const medY = median(ps.map(d => d.y));
    const refG = svg.append("g").attr("class", "median-ref");
    refG.append("line")
      .attr("x1", x(medX)).attr("x2", x(medX))
      .attr("y1", M.top).attr("y2", h - M.bottom)
      .attr("stroke", "#c8c8c8").attr("stroke-dasharray", "3,3").attr("stroke-width", 1);
    refG.append("line")
      .attr("x1", M.left).attr("x2", w - M.right)
      .attr("y1", y(medY)).attr("y2", y(medY))
      .attr("stroke", "#c8c8c8").attr("stroke-dasharray", "3,3").attr("stroke-width", 1);
  }}

  // Coincident-dot disambiguation.  Plays with identical (x, y) (e.g.,
  // Wealth and Thesmophoriazusae at order=13 / avg-deg=4.62 on
  // average-degree x order) would render as a single overlapping dot,
  // and only the topmost would receive mouse events.  Group ps by
  // rounded screen position; for each group of 2+, distribute the dots
  // radially around the original centre so each gets its own
  // clickable / hoverable area.  Each dot stores its offset in _dx/_dy
  // (read below when positioning circle and label).  Computed before
  // `extras`, so that anything drawn behind the dots -- the pair-lines --
  // ends on the dot the reader sees rather than on the undisplaced centre.
  const _coinGroups = new Map();
  for (const d of ps) {{
    const k = Math.round(x(d.x)) + "," + Math.round(y(d.y));
    if (!_coinGroups.has(k)) _coinGroups.set(k, []);
    _coinGroups.get(k).push(d);
  }}
  for (const grp of _coinGroups.values()) {{
    if (grp.length <= 1) {{
      if (grp.length === 1) {{ grp[0]._dx = 0; grp[0]._dy = 0; }}
      continue;
    }}
    // Distribute around a circle, starting from due north for stable
    // ordering.  Two coincident dots produce a vertical pair; three a
    // triangle; etc.  Visual radius _coinOffsetR scales with dot size.
    const _coinOffsetR = dotR * 1.4;
    for (let i = 0; i < grp.length; i++) {{
      const a = (2 * Math.PI * i) / grp.length - Math.PI / 2;
      grp[i]._dx = _coinOffsetR * Math.cos(a);
      grp[i]._dy = _coinOffsetR * Math.sin(a);
    }}
  }}

  if (typeof extras === "function") {{
    extras(svg, x, y, ps, {{w: w, h: h, M: M, dotR: dotR}});
  }}

  // Dot rendering.  One accent colour, unless the chart gives the fill to a
  // quantity; the fill is never the reader's to set, so colour on a scatter
  // either means nothing or means what the legend says.
  const dots = svg.append("g").selectAll("circle").data(ps).enter().append("circle")
    .attr("class", "dot")
    .attr("cx", d => x(d.x) + (d._dx || 0))
    .attr("cy", d => y(d.y) + (d._dy || 0))
    .attr("r", dotR)
    .attr("fill",   d => toneFor ? toneFor(tone.value(segOf(d.p))) : "var(--accent)")
    .attr("stroke", "white")
    .attr("stroke-width", isBig ? 1.8 : 1.2)
    .on("click", (_, d) => {{ if (d.p.dashboard_href) window.location.href = d.p.dashboard_href; }});

  // Highlight: a ring around the dot, so it reads the same whether the fill
  // is the accent or a tone that carries data.  Drawn over the dots, and not
  // hit-testable, so the dot beneath keeps its tooltip and its click.
  const hl = ps.filter(d => isHighlighted(d.p));
  svg.append("g").attr("class", "highlight-rings").attr("pointer-events", "none")
    .selectAll("circle").data(hl).enter().append("circle")
    .attr("cx", d => x(d.x) + (d._dx || 0))
    .attr("cy", d => y(d.y) + (d._dy || 0))
    .attr("r", dotR + (isBig ? 5 : 3.5))
    .attr("fill", "none")
    .attr("stroke", "var(--highlight)")
    .attr("stroke-width", isBig ? 3 : 2);
  dots.append("title").text(d => {{
    return playName(d.p) + "\\n" +
           labelX + " = " + fmt(d.x) + "\\n" +
           labelY + " = " + fmt(d.y) +
           (tone ? "\\n" + tone.title + " = " + fmt(tone.value(segOf(d.p))) : "");
  }});

  // Tone legend, top right: a bar over the whole tone range, continuous as
  // the tone is -- separate swatches would read as classes -- and marked at
  // the values in `tone.legend`.  That corner is empty on density x order by
  // construction: density falls as the cast grows, so no large cast sits
  // near the top.  Its box is kept, so no label is moved onto it.
  let legendBox = null;
  if (tone) {{
    const font = isBig ? 12 : 9;
    const barW = isBig ? 160 : 90, barH = isBig ? 10 : 7;
    const right = w - M.right - 6, left = right - barW;
    const top = M.top + font + 5;
    const [lo, hi] = tone.domain;
    const xOf = v => left + (v - lo) / (hi - lo) * barW;
    const gid = svg.attr("id") + "-tone";
    const grad = svg.append("defs").append("linearGradient").attr("id", gid);
    for (let i = 0; i <= 10; i++) {{
      grad.append("stop").attr("offset", i / 10)
        .attr("stop-color", toneFor(lo + (hi - lo) * i / 10));
    }}
    const lg = svg.append("g").attr("class", "tone-legend");
    lg.append("text").attr("x", right).attr("y", M.top + font)
      .attr("text-anchor", "end").attr("font-size", font)
      .attr("fill", "var(--muted)").text(tone.caption);
    lg.append("rect").attr("x", left).attr("y", top)
      .attr("width", barW).attr("height", barH)
      .attr("fill", `url(#${{gid}})`).attr("stroke", "#bbb").attr("stroke-width", 0.5);
    // A dot beyond either end takes that end's tone; the end then says so.
    const vals = ps.map(d => tone.value(segOf(d.p)));
    const below = vals.some(v => v < lo), above = vals.some(v => v > hi);
    tone.legend.forEach(v => {{
      lg.append("line").attr("x1", xOf(v)).attr("x2", xOf(v))
        .attr("y1", top + barH).attr("y2", top + barH + 3)
        .attr("stroke", "#999").attr("stroke-width", 1);
      lg.append("text").attr("x", xOf(v)).attr("y", top + barH + 3 + font)
        .attr("text-anchor", "middle").attr("font-size", font)
        .attr("fill", "var(--muted)")
        .text((v === lo && below ? "\\u2264" : v === hi && above ? "\\u2265" : "") + v);
    }});
    legendBox = boxOf(lg.node());
  }}

  // Labels beside points, every play's when the chart is not too crowded.
  // Above twenty plays only the highlighted ones are labelled -- which is
  // what the highlight is for in a corpus that large: the one way, short of
  // hovering, to find a play on every scatter.  A highlighted label is set
  // bold and clears its ring.  Inherit the coincidence offset so labels
  // track their displaced dots.  Each label is set right of its dot and
  // measured there; placeLabels then moves any that would cover another
  // label, come nearer another play's dot than its own, or run off the plot.
  const labelled = ps.length <= 20 ? ps : hl;
  const at = d => [x(d.x) + (d._dx || 0), y(d.y) + (d._dy || 0)];
  // What a label must clear around its dot: on a highlighted play, the ring
  // and half its stroke.  `clear` is the gap it leaves.
  const reach = d => isHighlighted(d.p)
    ? dotR + (isBig ? 5 : 3.5) + (isBig ? 1.5 : 1) : dotR;
  const clear = isBig ? 3 : 2;
  const labs = svg.append("g").selectAll("text.lab").data(labelled).enter().append("text")
    .attr("class", "lab")
    .attr("x", d => at(d)[0] + (isBig ? 12 : 7)
                   + (isHighlighted(d.p) ? (isBig ? 6 : 4) : 0))
    .attr("y", d => at(d)[1] + (isBig ? 5 : 3))
    .attr("font-size", playLabelFont).attr("fill", "#555")
    .attr("font-weight", d => isHighlighted(d.p) ? 700 : null)
    .text(d => shortTitle(d.p));
  const items = labs.nodes().map(node => {{
    const d = node.__data__, [cx, cy] = at(d);
    const sx = +node.getAttribute("x"), sy = +node.getAttribute("y");
    // A label the browser cannot measure (a hidden view) is estimated from
    // its length, so the pass still runs.
    const b = boxOf(node) || {{
      x0: sx, x1: sx + node.textContent.length * playLabelFont * 0.6,
      y0: sy - playLabelFont * 0.8, y1: sy + playLabelFont * 0.25}};
    return {{cx, cy, r: reach(d), gap: clear, dx: sx - cx, dy: sy - cy,
            w: b.x1 - b.x0, a: sy - b.y0, dsc: b.y1 - sy,
            dot: ps.indexOf(d), first: isHighlighted(d.p)}};
  }});
  // Every dot is kept clear by the gap a label leaves at its own, so no
  // label comes nearer another play than the play it names.
  const keepOff = ps.map(d => {{
    const [cx, cy] = at(d), r = reach(d) + clear;
    return {{x0: cx - r, y0: cy - r, x1: cx + r, y1: cy + r}};
  }});
  const spots = placeLabels(items, keepOff,
    {{x0: M.left + 2, y0: 0, x1: w, y1: h - M.bottom - 2}},
    legendBox ? [legendBox] : []);
  labs.attr("x", (_, i) => spots[i].x).attr("y", (_, i) => spots[i].y);
}}

// A drawn element's box, {{x0, y0, x1, y1}}, or null where the browser cannot
// measure it (an element in a hidden view).
function boxOf(node) {{
  let b = null;
  try {{ b = node.getBBox(); }} catch (e) {{ return null; }}
  if (!b || !(b.width > 0)) return null;
  return {{x0: b.x, y0: b.y, x1: b.x + b.width, y1: b.y + b.height}};
}}

// ---- label placement ----------------------------------------------------
// A play's label sits right of its dot.  Where that spot would cover text
// -- a label already placed, or a box in `taken` -- or a box to keep off
// -- on the scatters, every other play's dot, widened by the gap a label
// leaves at its own -- or run off the plot, the label takes the first free
// spot of seven others around the same dot: above right, below right,
// left, above left, below left, above, below.  Labels are placed in turn,
// highlighted plays first.  Where no spot is free, a label goes where it
// covers the least text and crosses the plot's edge least, since neither
// can then be read, and only between spots equal in that, where it covers
// the least of the boxes to keep off.  A label never leaves its own dot, so
// it needs no leader line, and a label with nothing in its way stays where
// it was.
//   items:   [{{cx, cy, r, gap, dx, dy, w, a, dsc, dot, first}}] -- the dot's
//            centre, the radius to clear around it and the gap to leave;
//            the default baseline start, relative to the centre; the text's
//            width, ascent and descent; the index of its own dot in
//            `keepOff`; whether it is placed first
//   keepOff: [{{x0, y0, x1, y1}}] -- one box per dot, none of which a label
//            covers but its own dot's
//   bounds:  {{x0, y0, x1, y1}} -- the area labels stay inside
//   taken:   [{{x0, y0, x1, y1}}] -- boxes already holding text (optional)
// Returns each label's baseline start, {{x, y}}, in the order of `items`.
function placeLabels(items, keepOff, bounds, taken) {{
  const overlap = (a, b) =>
    Math.max(0, Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0)) *
    Math.max(0, Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0));
  const order = items.map((_, i) => i).sort((i, j) =>
    (items[j].first ? 1 : 0) - (items[i].first ? 1 : 0) || i - j);
  const placed = (taken || []).slice();
  const out = new Array(items.length);
  for (const i of order) {{
    const it = items[i];
    // The corner spots touch the cleared circle at 45 degrees.
    const k = (it.r + it.gap) * Math.SQRT1_2;
    const spots = [
      [it.cx + it.dx,         it.cy + it.dy],
      [it.cx + k,             it.cy - k - it.dsc],
      [it.cx + k,             it.cy + k + it.a],
      [it.cx - it.dx - it.w,  it.cy + it.dy],
      [it.cx - k - it.w,      it.cy - k - it.dsc],
      [it.cx - k - it.w,      it.cy + k + it.a],
      [it.cx - it.w / 2,      it.cy - it.r - it.gap - it.dsc],
      [it.cx - it.w / 2,      it.cy + it.r + it.gap + it.a],
    ];
    let best = null;
    for (const [sx, sy] of spots) {{
      const box = {{x0: sx, y0: sy - it.a, x1: sx + it.w, y1: sy + it.dsc}};
      let text = (box.x1 - box.x0) * (box.y1 - box.y0) - overlap(box, bounds);
      for (const q of placed) text += overlap(box, q);
      if (text < 0.5) text = 0;    // half a square pixel is no overlap
      let near = 0;
      keepOff.forEach((q, j) => {{ if (j !== it.dot) near += overlap(box, q); }});
      if (!best || text < best.text || (text === best.text && near < best.near))
        best = {{x: sx, y: sy, box, text, near}};
      if (text === 0 && near < 0.5) break;
    }}
    placed.push(best.box);
    out[i] = {{x: best.x, y: best.y}};
  }}
  return out;
}}
// ---- play names ---------------------------------------------------------
// A title does not identify a play: Sophocles and Euripides both wrote an
// Electra, and both cite as "El.".  Where two plays of the corpus would carry
// the same label, the author's citation form is added to both.  Collisions
// are counted over the whole corpus, not the plays on screen, so a play keeps
// one label whatever is selected -- and a corpus without a shared title
// labels exactly as before.

// The short label a play would carry on its own: the Latin abbreviation
// (Ach., Av., Thesm.), the form used to cite these plays; failing that the
// English or Greek title, shortened; failing that the id.
function _ownShortTitle(p) {{
  const abbr = (p.title_lat_abbr || "").trim();
  if (abbr) return abbr;
  const t = (p.title_en || p.title_grc || p.id || "").trim();
  return t.length > 16 ? t.slice(0, 15) + "\\u2026" : t;
}}
function _ownLongTitle(p) {{
  return (p.title_en || p.title_grc || p.id || "").trim();
}}
// How a play's author is cited: the Latin abbreviation where the header
// gives one (Soph., Eur.), else the name as given.
function authorCite(p) {{
  return (p.author_lat_abbr || p.author || "").trim();
}}
function _sharedBy(labelOf) {{
  const n = {{}};
  for (const p of DATA.plays || []) {{
    const k = labelOf(p);
    n[k] = (n[k] || 0) + 1;
  }}
  return new Set(Object.keys(n).filter(k => n[k] > 1));
}}
const _SHARED_SHORT = _sharedBy(_ownShortTitle);
const _SHARED_LONG = _sharedBy(_ownLongTitle);

// Chart and chip labels: "El." alone, "Soph. El." where another El. exists.
function shortTitle(p) {{
  const base = _ownShortTitle(p), who = authorCite(p);
  return (_SHARED_SHORT.has(base) && who) ? who + " " + base : base;
}}
// Visible full titles: "Electra (Sophocles)" where another Electra exists.
function longTitle(p) {{
  const base = _ownLongTitle(p);
  return (_SHARED_LONG.has(base) && p.author) ? base + " (" + p.author + ")" : base;
}}
// Hover text always names the author, whatever the corpus holds.
function playName(p) {{
  const base = _ownLongTitle(p);
  return p.author ? base + " (" + p.author + ")" : base;
}}

// -------------------------------------------------------------------- composition stacked bar
function renderComposition() {{
  const svg = d3.select("#composition-chart");
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.selectAll("*").remove();
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);
  const M = {{top: 18, right: 14, bottom: 70, left: 40}};
  const ps = activePlays().slice().sort((a, b) =>
    (segOf(b).demographics.speakers + segOf(b).demographics.mutes) -
    (segOf(a).demographics.speakers + segOf(a).demographics.mutes));
  if (!ps.length) return;

  const x = d3.scaleBand().domain(ps.map(p => p.id)).range([M.left, w - M.right]).padding(0.18);
  const yMax = d3.max(ps, p => segOf(p).demographics.speakers + segOf(p).demographics.mutes);
  const y = d3.scaleLinear().domain([0, yMax]).nice().range([h - M.bottom, M.top]);

  svg.append("g").attr("transform", `translate(${{M.left}},0)`)
     .call(d3.axisLeft(y).ticks(5));
  svg.append("text").attr("x", -h / 2).attr("y", 12)
     .attr("transform", "rotate(-90)").attr("text-anchor", "middle")
     .attr("font-size", 11).attr("fill", "var(--muted)").text("characters");

  const bg = svg.append("g");
  for (const p of ps) {{
    const d = segOf(p).demographics;
    const x0 = x(p.id), bw = x.bandwidth();
    bg.append("rect")
      .attr("x", x0).attr("y", y(d.speakers + d.mutes))
      .attr("width", bw).attr("height", y(0) - y(d.speakers + d.mutes))
      .attr("fill", "var(--mute)")
      .on("click", () => {{ if (p.dashboard_href) window.location.href = p.dashboard_href; }})
      .append("title").text(`${{playName(p)}}: ${{d.speakers}} speakers + ${{d.mutes}} mutes`);
    bg.append("rect")
      .attr("x", x0).attr("y", y(d.speakers))
      .attr("width", bw).attr("height", y(0) - y(d.speakers))
      .attr("fill", "var(--speaker)")
      .on("click", () => {{ if (p.dashboard_href) window.location.href = p.dashboard_href; }})
      .append("title").text(`${{playName(p)}}: ${{d.speakers}} speakers`);
  }}
  // x labels rotated.
  const xLab = svg.append("g").attr("transform", `translate(0,${{h - M.bottom}})`)
    .selectAll("text").data(ps).enter().append("text")
    .attr("x", p => x(p.id) + x.bandwidth() / 2)
    .attr("y", 12).attr("text-anchor", "end")
    .attr("transform", p => `rotate(-40,${{x(p.id) + x.bandwidth() / 2}},12)`)
    .attr("font-size", 10).attr("fill", "#555")
    .text(p => shortTitle(p));
}}

// -------------------------------------------------------------------- beat-chart small multiples
function renderBeatMultiples() {{
  const root = d3.select("#beat-multiples");
  root.selectAll("*").remove();
  const ps = activePlays();
  const cells = root.selectAll(".sm").data(ps).enter()
    .append("div").attr("class", "sm")
    .style("cursor", "pointer")
    .on("click", (_, p) => {{ if (p.dashboard_href) window.location.href = p.dashboard_href; }});
  cells.append("div").attr("class", "title").text(p => longTitle(p));
  cells.each(function(p) {{
    const svg = d3.select(this).append("svg");
    requestAnimationFrame(() => drawBeatMini(svg, p));
  }});
}}
function drawBeatMini(svg, p) {{
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);
  const blk = segOf(p) || {{}};
  const rates = blk.change_rates || [];
  if (!rates.length) return;
  const M = {{top: 4, right: 4, bottom: 12, left: 14}};
  const y = d3.scaleLinear().domain([0, 1]).range([h - M.bottom, M.top]);

  // X mapping.  Default: evenly spaced transition index.  Word mode: place
  // each transition at its cumulative word position (stage-time).  The
  // series omits the bracket transitions (empty opener and empty terminal),
  // so its offset against words_per_segment cannot be recovered from the
  // lengths; the payload ships it as change_rates_start -- the index of the
  // segment the first transition departs from.
  const words = blk.words_per_segment || [];
  const startI = blk.change_rates_start || 0;
  let xpos = null;
  if (STATE.beatXMode === "word" && words.length >= rates.length + startI) {{
    const prefix = []; let acc = 0;
    for (let k = 0; k < words.length; k++) {{ acc += (words[k] || 0); prefix.push(acc); }}
    if (acc > 0) {{
      const x = d3.scaleLinear().domain([0, acc]).range([M.left, w - M.right]);
      xpos = i => x(prefix[startI + i]);
    }}
  }}
  if (!xpos) {{
    const x = d3.scaleLinear().domain([0, Math.max(1, rates.length - 1)]).range([M.left, w - M.right]);
    xpos = i => x(i);
  }}

  // Mean (drama-change rate).
  const mu = mean(rates);
  svg.append("line")
    .attr("x1", M.left).attr("x2", w - M.right)
    .attr("y1", y(mu)).attr("y2", y(mu))
    .attr("stroke", "var(--speaker)").attr("stroke-dasharray", "2,2").attr("stroke-width", 1);
  svg.append("path")
    .attr("fill", "none").attr("stroke", "var(--beat)").attr("stroke-width", w > 600 ? 1.5 : 1.1)
    .attr("d", d3.line().x((_, i) => xpos(i)).y(d => y(d))(rates));
  // A dot at every transition so individual segments stay locatable even
  // when the line packs them tightly (word mode).  Radius grows with cell
  // width so the dots remain visible in the enlarged fullscreen view.
  const r = w > 600 ? 2.4 : 1.5;
  svg.append("g").selectAll("circle").data(rates).enter().append("circle")
    .attr("cx", (_, i) => xpos(i)).attr("cy", d => y(d))
    .attr("r", r).attr("fill", "var(--beat)");
  svg.append("text").attr("x", w - M.right).attr("y", h - 2)
    .attr("text-anchor", "end").attr("font-size", w > 600 ? 11 : 9)
    .attr("fill", "var(--muted)").text("\\u03BC = " + fmt(mu));
}}

// -------------------------------------------------------------------- chorus beat chart
//   One row per chorus character per play, x-axis normalised to [0, 1] of
//   each play's segment range so distribution shapes are comparable across
//   plays of different lengths.  Three-state encoding:
//     transparent  -> chorus not in characters_present for that segment
//     light grey   -> chorus is on stage but silent (0 words)
//     red ramp     -> chorus speaks; intensity ~ sqrt(words), saturating
//                     at the corpus maximum (so cross-play comparison of
//                     intensity is honest).
//   Sort order: genre -> author -> title -> chorus name.
function renderChorusBeat() {{
  const svg = d3.select("#chorus-beat-chart");
  svg.selectAll("*").remove();
  const ps = activePlays();
  const muteKey = STATE.muteMode || "full";
  const aggKey  = STATE.aggregateChorus ? "agg" : "raw";
  const variantKey = muteKey + "_" + aggKey;

  // Build flat row list, one per chorus character.
  const rows = [];
  ps.forEach(p => {{
    const seg = (p.segmentations || {{}})[STATE.seg];
    if (!seg) return;
    const cd = (seg.chorus_data || {{}})[variantKey] || [];
    cd.forEach(ch => {{
      if (!ch || !ch.words || !ch.words.length) return;
      rows.push({{
        play: p,
        chorus: ch,
        nSegments: ch.words.length,
      }});
    }});
  }});

  if (!rows.length) {{
    svg.attr("height", 32).attr("viewBox", "0 0 600 32");
    svg.append("text").attr("x", 12).attr("y", 20)
      .attr("font-size", 12).attr("fill", "var(--muted)")
      .text("No chorus characters in the active segmentation / mute view.");
    return;
  }}

  // Sort: genre, then author, then title, then chorus name.  Comedies
  // first so the Aristophanic block reads as a single contiguous group;
  // alphabetical genre sort keeps the order stable across corpora.
  rows.sort((a, b) => {{
    const ga = a.play.genre || "zz", gb = b.play.genre || "zz";
    if (ga !== gb) return ga.localeCompare(gb);
    const aa = a.play.author || "", ab = b.play.author || "";
    if (aa !== ab) return aa.localeCompare(ab);
    const ta = a.play.title_en || a.play.id || "";
    const tb = b.play.title_en || b.play.id || "";
    if (ta !== tb) return ta.localeCompare(tb);
    return (a.chorus.name || "").localeCompare(b.chorus.name || "");
  }});

  // Layout.
  const rowH = 18;
  const labelW = 220;
  const padR = 20;
  const padTop = 26;
  const padBottom = 22;
  const w = svg.node().clientWidth || 800;
  const h = padTop + rows.length * rowH + padBottom;
  svg.attr("height", h).attr("viewBox", `0 0 ${{w}} ${{h}}`);

  // Colour scale: sqrt against the global max words across visible rows,
  // so a cell's saturation is directly comparable across the corpus.
  const allWords = rows.flatMap(r => r.chorus.words).filter(v => v > 0);
  const maxV = allWords.length ? d3.max(allWords) : 1;
  const color = d3.scaleSqrt().domain([1, maxV]).range(["#fcbba1", "#a50f15"]);
  const colorSilent = "#bbbbbb";
  // A song whose text is not transmitted: hatched in the ramp's darkest red
  // on a pale ground, so it reads as speech with nothing in it.
  const hatchId = "chorus-notext-hatch";
  svg.append("defs").append("pattern").attr("id", hatchId)
    .attr("patternUnits", "userSpaceOnUse").attr("width", 4).attr("height", 4)
    .attr("patternTransform", "rotate(45)")
    .call(p => {{
      p.append("rect").attr("width", 4).attr("height", 4).attr("fill", "#fde0dd");
      p.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 4)
        .attr("stroke", "#a50f15").attr("stroke-width", 1.5);
    }});

  // Genre/author bands: subtle horizontal stripes behind rows in the same
  // (genre, author) group so the eye can read sub-corpora at a glance.
  const bandG = svg.append("g").attr("class", "bands");
  let bandStart = 0;
  let bandKey = (rows[0].play.genre || "") + "|" + (rows[0].play.author || "");
  let bandShade = true;
  for (let i = 1; i <= rows.length; i++) {{
    const k = (i < rows.length)
      ? (rows[i].play.genre || "") + "|" + (rows[i].play.author || "")
      : null;
    if (k !== bandKey) {{
      if (bandShade) {{
        bandG.append("rect")
          .attr("x", 0).attr("y", padTop + bandStart * rowH)
          .attr("width", w).attr("height", (i - bandStart) * rowH)
          .attr("fill", "#f5f5f5");
      }}
      bandStart = i;
      bandKey = k;
      bandShade = !bandShade;
    }}
  }}

  // X-axis: normalised play progress [0, 1].
  const xScale = d3.scaleLinear().domain([0, 1]).range([labelW, w - padR]);
  const axisG = svg.append("g")
    .attr("transform", `translate(0, ${{padTop - 2}})`)
    .call(d3.axisTop(xScale).ticks(5).tickFormat(d3.format(".0%")));
  axisG.selectAll("text").attr("font-size", 10).attr("fill", "var(--muted)");
  axisG.selectAll("path, line").attr("stroke", "#ccc");
  svg.append("text")
    .attr("x", labelW + (w - padR - labelW) / 2)
    .attr("y", h - 6).attr("text-anchor", "middle")
    .attr("font-size", 10).attr("fill", "var(--muted)")
    .text("normalised play progress (segment index / total segments)");

  // Row labels + cells.
  rows.forEach((r, i) => {{
    const y0 = padTop + i * rowH;
    const yMid = y0 + rowH / 2 + 3;

    svg.append("text")
      .attr("x", labelW - 6).attr("y", yMid)
      .attr("text-anchor", "end").attr("font-size", 10.5)
      .attr("fill", "var(--ink)")
      .style("cursor", "pointer")
      .text(() => {{
        const t = shortTitle(r.play);
        const c = r.chorus.name || r.chorus.id;
        // Append chorus name only when the play has more than one row
        // here, to avoid noisy "Acharnians · Chorus" when there's only
        // one chorus anyway.
        const playRows = rows.filter(rr => rr.play === r.play).length;
        return playRows > 1 ? `${{t}} · ${{c}}` : t;
      }})
      .on("click", () => {{ if (r.play.dashboard_href) window.location.href = r.play.dashboard_href; }})
      .append("title").text(`${{playName(r.play)}} - ${{r.chorus.name}}`);

    // Row baseline: a thin line spanning the full cell area, so that
    // absent segments at the start/end of the row do not visually
    // truncate the row.  Without this, a chorus that exits before the
    // last segment looks like a shorter row -- conflating "chorus
    // absent at end" with "row ends early".  The baseline makes the
    // row's full extent always visible; cells overlay it.
    svg.append("line")
      .attr("x1", labelW).attr("x2", w - padR)
      .attr("y1", y0 + rowH / 2).attr("y2", y0 + rowH / 2)
      .attr("stroke", "#d8d8d8").attr("stroke-width", 1)
      .attr("shape-rendering", "crispEdges");

    const n = r.chorus.words.length;
    const cellSpan = (w - padR - labelW) / n;
    for (let s = 0; s < n; s++) {{
      const v = r.chorus.words[s];
      const pres = !!r.chorus.present[s];
      const speaks = !!(r.chorus.speaks || [])[s];
      // Four states.  A speech without transmitted words is kept apart from
      // silence: the chorus performs there, and the manuscripts record only
      // that it did (the XOPOY interludes).
      let fill, what;
      if (v > 0) {{
        fill = color(v); what = v + " word" + (v === 1 ? "" : "s");
      }} else if (speaks) {{
        fill = "url(#" + hatchId + ")"; what = "performs, text not transmitted";
      }} else if (pres) {{
        fill = colorSilent; what = "present, silent";
      }} else continue;  // transparent: skip drawing entirely
      svg.append("rect")
        .attr("x", labelW + s * cellSpan)
        .attr("y", y0 + 1)
        .attr("width", Math.max(0.6, cellSpan))
        .attr("height", rowH - 2)
        .attr("fill", fill)
        .style("cursor", "pointer")
        .on("click", () => {{ if (r.play.dashboard_href) window.location.href = r.play.dashboard_href; }})
        .append("title").text(
          `${{playName(r.play)}} - ${{r.chorus.name}}\\n` +
          `segment ${{s + 1}} / ${{n}}\\n` + what);
    }}
  }});
}}

// -------------------------------------------------------------------- plays table
function renderPlaysTable() {{
  const cols = [
    ["play",     p => p.title_en + (p.title_grc ? " (" + p.title_grc + ")" : "")],
    ["author",   p => p.author || "\\u2014"],
    ["order",    p => segOf(p).size, true],
    ["spk",      p => (segOf(p).demographics || {{}}).speakers || 0, true],
    ["mute",     p => (segOf(p).demographics || {{}}).mutes || 0, true],
    // Three play-level composition ratios.  Both mute modes are
    // pre-computed in `composition.in` and `composition.out`; the JS
    // picks whichever the mute toggle currently selects, so the columns
    // shift along with the rest of the dashboard.  Under `out` the
    // mutes are excluded from the demographics, which makes spk/cast
    // trivially 1.0 (every visible character speaks) and shifts the
    // female-share to count only sexed *speakers*.
    ["spk/cast", p => {{
      const c = (p.composition || {{}})[STATE.muteMode || "full"] || {{}};
      return fmt(c.speakers_share, 3);
    }}, true],
    ["col/spk", p => {{
      const c = (p.composition || {{}})[STATE.muteMode || "full"] || {{}};
      return fmt(c.collective_speakers_share, 3);
    }}, true],
    ["f/(f+m)", p => {{
      const c = (p.composition || {{}})[STATE.muteMode || "full"] || {{}};
      return fmt(c.female_share, 3);
    }}, true],
    ["edges",    p => segOf(p).numEdges, true],
    ["density",  p => fmt(segOf(p).density, 3), true],
    // Sorted on the raw value: this is the one column here whose formatted
    // text can reach two digits, and "12.74" precedes "3.67" as a string.
    ["avg deg",  p => fmt(segOf(p).averageDegree, 2), true,
      p => segOf(p).averageDegree || 0],
    // Segment count is model-specific under the sd spine: the two
    // speaking models fold away boundaries triggered only by non-nodes (e.g. a
    // mute's entrance), so this column drops when you switch the model.
    // For large-seq / middle-seq it is fixed (textual divisions).
    ["seg",      p => segOf(p).num_segments, true],
    ["DCR",      p => fmt(mean(segOf(p).change_rates || []), 3), true],
    ["all-in",   p => fmt((segOf(p).segment_indices || {{}}).all_in_index || 0, 3), true],
    ["final share", p => fmt((segOf(p).segment_indices || {{}}).final_segment_cast_share || 0, 3), true],
    // Sorted by the share, not by the name the cell happens to start with:
    // the question this column answers is how dominant the leading speaker
    // is, and Aristophanic speaker ids are in no useful order.
    ["top spk",  p => {{
      const sd = segOf(p).speech_distribution || {{}};
      const who = (sd.top_speaker_ids || []).join(", ") || "\\u2014";
      return who + " (" + fmt((sd.top_speaker_word_share || 0) * 100, 1) + "%)";
    }}, false,
      p => (segOf(p).speech_distribution || {{}}).top_speaker_word_share || 0],
    ["Gini",     p => fmt((segOf(p).speech_distribution || {{}}).gini_words || 0, 3), true],
    // Effective speakers (1 / sum of squared shares).  Beside the Gini
    // because the two answer the same question differently: the Gini
    // weights by rank and so responds to how finely the cast list is cut,
    // this weights by share and barely notices a one-line role.  Read
    // together, a gap between them is a long tail of small parts.
    ["eff spk",  p => fmt((segOf(p).speech_distribution || {{}}).effective_speakers || 0, 2), true],
    // Top-speaker temporal Gini: how concentrated their speech is
    // across the play's segments.  Steady leads (Dikaiopolis, Trygaios)
    // sit low; burst leads (Lysistrate, Praxagora) sit high.
    ["top spk tGini", p => fmt((segOf(p).speech_distribution || {{}}).top_speaker_temporal_gini, 3), true],
    ["max sim sp", p => (segOf(p).segment_indices || {{}}).max_simultaneous_speakers || 0, true],
  ];
  const rows = activePlays();
  drawTable("#plays-table", cols, rows, "play", 1, (p) => {{
    if (p && p.dashboard_href) window.location.href = p.dashboard_href;
  }});
}}
function drawTable(sel, cols, rows, sortKey, sortDir, onClickRow) {{
  const t = d3.select(sel);
  t.selectAll("*").remove();
  const thead = t.append("thead").append("tr");
  thead.selectAll("th").data(cols).enter().append("th")
    // Mirror the numeric-column flag onto the header so right-aligned
    // numeric columns get right-aligned headers, not floating-left
    // labels above their data.
    .attr("class", c => c[2] ? "num" : null)
    .text(c => c[0])
    .on("click", (_, c) => {{
      if (sortKey === c[0]) sortDir = -sortDir; else {{ sortKey = c[0]; sortDir = 1; }}
      drawTable(sel, cols, rows, sortKey, sortDir, onClickRow);
    }});
  const sortCol = cols.find(c => c[0] === sortKey) || cols[0];
  // A column may carry a 4th element: the value to order by, for when the
  // cell's text is not what the reader wants to sort on.  Without it the
  // sort is lexicographic on whatever is displayed, so "allantopoles
  // (31.9%)" orders by the speaker's name, and a formatted number orders by
  // its digits -- putting "12.74" before "3.67".
  const keyOf = sortCol[3] || sortCol[1];
  const sorted = rows.slice().sort((a, b) => {{
    const va = keyOf(a), vb = keyOf(b);
    if (typeof va === "number" && typeof vb === "number") return sortDir * (va - vb);
    return sortDir * String(va).localeCompare(String(vb));
  }});
  const tb = t.append("tbody");
  tb.selectAll("tr").data(sorted).enter().append("tr")
    .attr("class", "row-link")
    // Pass the data object itself, not an index.  The previous version
    // passed `sorted.indexOf(p)` -- the index in the *sorted* array -- but
    // every caller then looked it up in the original (unsorted) `rows`,
    // which silently selected the wrong play whenever the table sort
    // differed from the original order (e.g. Birds -> Knights).
    .on("click", (_, p) => onClickRow && onClickRow(p))
    .selectAll("td").data((p, i) => cols.map(c => ({{c, p, i}}))).enter().append("td")
    .attr("class", o => o.c[2] ? "num" : null)
    .html(o => {{ const v = o.c[1](o.p, o.i); return v == null ? "" : v; }});
}}

// -------------------------------------------------------------------- render
function render() {{
  renderTabs();
  renderPlaysSelector();
  renderKPIs();
  // Density vs order.  Density falls with cast size mechanically --
  // d = k / (n - 1) is an identity -- so a large play reads sparse beside a
  // small one whatever its connectivity.  An iso-degree curve once answered
  // that here and was removed for its premises.  What answers it now is k
  // itself, which the chart holds only implicitly: on request the dots are
  // coloured by it, computed from the chart's own two coordinates and so
  // adding no premise, and a play whose characters share the stage with
  // unusually many others shows as an unusually dark dot in whichever view
  // is active, and only there.  The pair-lines compare each play with its
  // nearest-order neighbours without assuming anything.
  const toneByDegree = STATE.toneByDegree ? {{tone: {{
    value: s => s.averageDegree,
    // From a quarter of the corpus anchor to twice it: 2 to 16 for the
    // comedies, whose values run 2.7 to 15.5 across every view.  The legend
    // marks the two ends and the anchor.
    domain: [DEGREE_ANCHOR / 4, DEGREE_ANCHOR * 2],
    legend: [DEGREE_ANCHOR / 4, DEGREE_ANCHOR, DEGREE_ANCHOR * 2],
    caption: "characters met, on average",
    title: "average degree",
  }}}} : null;
  drawScatter("#sizing-chart",
    s => s.size, s => s.density,
    "order (number of nodes/characters)", "density",
    (svg, x, y, ps, geom) => {{
      // ─── Pair lines (drawn first, so the dots overlay them) ───────
      // For every pair of plays with order difference <= 5, draw a
      // thin red segment between them.  Short lines = local-neighbourhood
      // density variation; tall lines = a play whose density does not
      // match its nearest-order companions.  Lysistrata's incident
      // lines stand out visibly because there is no nearby-order play
      // with comparable density.
      //
      // A line's height is NOT the connectivity gap.  Since d = k/(n-1),
      //     d_hi / d_lo = (k_hi / k_lo) * ((n_lo - 1) / (n_hi - 1)),
      // so the residual size difference inside the window is still in
      // there: Thesmophoriazusae and Wealth have k = 6.93 and 6.94 -- the
      // same connectivity -- and are joined by a line 14% tall, which is
      // exactly their 16/14.  The tooltip therefore carries both excesses,
      // so a reader can see which of the two a line is showing.
      if (STATE.showPairLines) {{
        // fill none: the lines are paths, and a bowed path would otherwise
        // be filled black.
        const pairG = svg.append("g").attr("class", "pair-lines")
          .attr("stroke", "#d62728")
          .attr("stroke-width", 1.5)
          .attr("fill", "none")
          .attr("opacity", 0.75);
        const excess = (a, b) => {{
          const hi = Math.max(a, b), lo = Math.min(a, b);
          return lo > 0 ? ((hi / lo - 1) * 100).toFixed(1) + "%" : "n/a";
        }};
        // Where each dot is actually drawn, coincidence offset included.
        const at = d => [x(d.x) + (d._dx || 0), y(d.y) + (d._dy || 0)];
        const screen = ps.map(at);
        for (let i = 0; i < ps.length; i++) {{
          for (let j = i + 1; j < ps.length; j++) {{
            if (Math.abs(ps[i].x - ps[j].x) > 5) continue;
            const kI = segOf(ps[i].p).averageDegree || 0;
            const kJ = segOf(ps[j].p).averageDegree || 0;
            const others = screen.filter((_, k) => k !== i && k !== j);
            const ln = pairG.append("path")
              .attr("d", pairLinePath(screen[i], screen[j], others,
                                      geom.dotR));
            ln.append("title").text(
              playName(ps[i].p) + " (n=" + ps[i].x + ", d=" + ps[i].y.toFixed(3) + ", k=" + kI.toFixed(2) + ")\\n" +
              "\\u2194 " +
              playName(ps[j].p) + " (n=" + ps[j].x + ", d=" + ps[j].y.toFixed(3) + ", k=" + kJ.toFixed(2) + ")\\n" +
              "\\u0394n=" + Math.abs(ps[i].x - ps[j].x).toFixed(0) +
              "  \\u2022  density excess " + excess(ps[i].y, ps[j].y) +
              "  \\u2022  avg-degree excess " + excess(kI, kJ));
          }}
        }}
      }}
    }}, toneByDegree);
  drawScatter("#scaling-chart",
    s => s.size, s => s.averageDegree,
    "order (number of nodes/characters)", "average degree");
  // No density x average-degree chart: density is fixed by order and
  // average degree (d = k / (n - 1)), so it would redraw the two charts
  // above from a third angle.
  drawScatter("#typology-chart",
    s => mean(s.change_rates || []),
    s => stdev(s.change_rates || []),
    "drama-change rate", "\\u03C3 (change-rate stdev)");
  // Effective speakers x average degree -- how many voices carry the play
  // against how many others a character meets.  One speech axis, where
  // there were two charts: Gini, top-speaker share and effective speakers
  // summarise one word distribution and move together across the comedies
  // (share and effective speakers at rank correlation -0.84), so pairing
  // each with average degree drew much the same picture again.  Effective
  // speakers reads the whole distribution, where the share reads one
  // character, and unlike the Gini it does not track order (-0.33 to -0.07
  // over the eighteen views, against +0.73 to +0.84), which is already the
  // x-axis of two charts.  The y-axis responds to the spine and the model;
  // the x-axis moves only with the aggregation toggle, which merges
  // speakers.
  drawScatter("#esp-avgdeg-chart",
    s => (s.speech_distribution || {{}}).effective_speakers || 0,
    s => s.averageDegree,
    "effective speakers", "average degree");
  renderComposition();
  renderBeatMultiples();
  renderChorusBeat();
  renderPlaysTable();
}}

// ----------------------------------------------------------- view tabs
let _mathRendered = false;
function showView(name) {{
  document.querySelectorAll(".view-tab").forEach(b =>
    b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach(p =>
    p.classList.toggle("hidden", p.dataset.view !== name));
  if (name === "methods" && !_mathRendered) {{
    if (typeof renderMathInElement !== "undefined") {{
      renderMathInElement(document.querySelector(".view-methods"), {{
        delimiters: [
          {{left: "$$", right: "$$", display: true}},
          {{left: "$", right: "$", display: false}},
        ],
        throwOnError: false,
      }});
      _mathRendered = true;
    }}
  }}
}}
document.querySelectorAll(".view-tab").forEach(b =>
  b.addEventListener("click", () => showView(b.dataset.view)));

// Corpus-level three-state network model radio: same semantics as the
// per-play dashboards.  All scatter charts, KPI block, table, and beat
// charts redraw against the active model.
document.querySelectorAll('input[name="mute-mode"]').forEach(r => {{
  r.addEventListener("change", (e) => {{
    if (!e.target.checked) return;
    STATE.muteMode = e.target.value;
    renderActiveFilters();
    render();
  }});
}});

// Beat-multiples x-axis mode toggle (word-position vs segment index).
const _beatXBox = document.getElementById("beat-xmode");
if (_beatXBox) _beatXBox.addEventListener("change", (e) => {{
  STATE.beatXMode = e.target.checked ? "word" : "segment";
  renderBeatMultiples();
}});

// Global partOf aggregation toggle.  Now drives segOf(p), so every chart,
// the pair-lines, the KPI ranges and the plays table react --
// a full render() keeps the whole dashboard in sync.
const _aggBox = document.getElementById("aggregate-chorus");
if (_aggBox) _aggBox.addEventListener("change", (e) => {{
  STATE.aggregateChorus = e.target.checked;
  render();
}});

// Density x order: toggle for the pair-line overlay.  Scoped to that
// single chart (only the density x order sizing-chart draws them), so
// we re-render only that chart.  However the cleanest re-render route
// is to call render() (cheap) and it keeps the rest of the dashboard
// in sync if anything else depends on the toggle state.
const _pairBox = document.getElementById("show-pair-lines");
if (_pairBox) _pairBox.addEventListener("change", (e) => {{
  STATE.showPairLines = e.target.checked;
  render();
}});
// Density x order: colour the dots by average degree, or by the chip colours.
const _toneBox = document.getElementById("tone-by-degree");
if (_toneBox) _toneBox.addEventListener("change", (e) => {{
  STATE.toneByDegree = e.target.checked;
  render();
}});

// Plays-selector quick actions.  Each rewrites STATE.selectedPlays.
document.getElementById("sel-all").addEventListener("click", () => {{
  STATE.selectedPlays = new Set(DATA.plays.map(p => _playKey(p)));
  renderActiveFilters();
  render();
}});
document.getElementById("sel-none").addEventListener("click", () => {{
  STATE.selectedPlays = new Set();
  renderActiveFilters();
  render();
}});
document.getElementById("sel-invert").addEventListener("click", () => {{
  const next = new Set();
  for (const p of DATA.plays) {{
    const k = _playKey(p);
    if (!STATE.selectedPlays.has(k)) next.add(k);
  }}
  STATE.selectedPlays = next;
  renderActiveFilters();
  render();
}});
document.getElementById("clear-highlights").addEventListener("click", () => {{
  STATE.highlighted = new Set();
  render();
}});

// Inject a fullscreen-toggle button into every .panel.graph and wire up
// the toggle.  The pattern mirrors the per-play dashboard.  Toggling
// adds/removes the `chart-fullscreen` class and re-renders the whole
// dashboard so the chart picks up the new container dimensions.  Esc
// exits whichever panel is currently fullscreen.  Cheap on re-render
// since all chart data lives client-side.
// Keep the shared control strips usable while a chart is maximised:
// #seg-tabs (segmentation tabs + network-model radios + aggregate toggle)
// and #plays-selector-panel (play selection / exclusion).  We MOVE the
// real elements into the fullscreen panel -- not clones -- so their
// existing event wiring keeps driving render(); a hidden placeholder marks
// each origin so exit restores the exact DOM position.
const FS_CONTROL_IDS = ["seg-tabs", "plays-selector-panel"];
function _fsMoveControlsInto(panel) {{
  let host = panel.querySelector(".fs-controls");
  if (!host) {{
    host = document.createElement("div");
    host.className = "fs-controls";
    const h3 = panel.querySelector("h3");
    if (h3) h3.insertAdjacentElement("afterend", host);
    else panel.insertBefore(host, panel.firstChild);
  }}
  FS_CONTROL_IDS.forEach(id => {{
    const el = document.getElementById(id);
    if (!el || host.contains(el)) return;
    const ph = document.createElement("div");
    ph.className = "fs-placeholder";
    ph.style.display = "none";
    ph.dataset.fsFor = id;
    el.parentNode.insertBefore(ph, el);
    host.appendChild(el);
  }});
}}
function _fsRestoreControls() {{
  document.querySelectorAll(".fs-placeholder").forEach(ph => {{
    const el = document.getElementById(ph.dataset.fsFor);
    if (el) ph.parentNode.insertBefore(el, ph);
    ph.remove();
  }});
  document.querySelectorAll(".fs-controls").forEach(h => h.remove());
}}

function setupChartFullscreen() {{
  document.querySelectorAll('.panel.graph').forEach(panel => {{
    if (panel.querySelector('.fullscreen-toggle')) return;  // already wired
    const h3 = panel.querySelector('h3');
    if (!h3) return;
    const btn = document.createElement('button');
    btn.className = 'fullscreen-toggle';
    btn.innerHTML = '\\u26F6 fullscreen';
    btn.addEventListener('click', () => {{
      // One panel maximised at a time: exit any other first.
      document.querySelectorAll('.panel.graph.chart-fullscreen').forEach(p => {{
        if (p !== panel) {{
          p.classList.remove('chart-fullscreen');
          const b = p.querySelector('.fullscreen-toggle');
          if (b) b.innerHTML = '\\u26F6 fullscreen';
        }}
      }});
      const isFs = panel.classList.toggle('chart-fullscreen');
      _fsRestoreControls();                 // clear any prior placement
      if (isFs) _fsMoveControlsInto(panel); // host controls in this panel
      btn.innerHTML = isFs ? '\\u274C exit fullscreen' : '\\u26F6 fullscreen';
      // Re-render after the layout settles so the new container size is
      // available to clientWidth / clientHeight.
      requestAnimationFrame(() => {{
        render();
        if (typeof updateStickyOffsets === "function") updateStickyOffsets();
      }});
    }});
    h3.appendChild(btn);
  }});
}}
document.addEventListener('keydown', (e) => {{
  if (e.key !== 'Escape') return;
  let changed = false;
  document.querySelectorAll('.panel.graph.chart-fullscreen').forEach(panel => {{
    panel.classList.remove('chart-fullscreen');
    const btn = panel.querySelector('.fullscreen-toggle');
    if (btn) btn.innerHTML = '\\u26F6 fullscreen';
    changed = true;
  }});
  if (changed) {{
    _fsRestoreControls();
    requestAnimationFrame(() => {{
      render();
      if (typeof updateStickyOffsets === "function") updateStickyOffsets();
    }});
  }}
}});

renderActiveFilters();
render();
setupChartFullscreen();

// Measure the heights of all sticky elements so the next sticky below
// can offset itself precisely.  Layered stickiness:
//   - .topbar (header + view-tabs)             pinned at top: 0
//   - .tabs   (segmentation tabs)              pinned at top: --topbar-h
//   - .sticky-selector (Plays-included panel)  pinned at --topbar-h + --tabs-h
// Each layer reads the variables set here.  Re-measured on resize and
// after renderActiveFilters() (which is what changes the topbar's
// height by adding / removing the subset chip when selection toggles).
function updateStickyOffsets() {{
  const root = document.documentElement;
  const tb = document.querySelector('.topbar');
  if (tb) root.style.setProperty('--topbar-h', tb.offsetHeight + 'px');
  const tabs = document.querySelector('.view-analysis .tabs');
  if (tabs) root.style.setProperty('--tabs-h', tabs.offsetHeight + 'px');
}}
updateStickyOffsets();
window.addEventListener('resize', updateStickyOffsets);
</script>
<!--FIGURE_EXPORT_JS-->
</body>
</html>
"""




def write_corpus_dashboard(corpus_data: Dict, out_path: Path) -> Path:
    title = corpus_data.get("name") or "Corpus dashboard"
    authors = corpus_data.get("authors") or []
    sub_parts = [f"{len(corpus_data.get('plays', []))} plays"]
    # The author names come from the TEI headers; escape them, as the title is.
    if authors:
        sub_parts.append(_html_escape(", ".join(authors)) if len(authors) <= 5
                         else f"{len(authors)} authors")
    sub_parts.append("dashboard generated by SkeneGraph-Net")
    subtitle = " &middot; ".join(sub_parts)
    data_json = _json_for_script(corpus_data)
    html = _TEMPLATE.format(
        title=_html_escape(title),
        subtitle=subtitle,
        data_json=data_json,
    )
    # Inject the Methods tab via plain replace so KaTeX's literal `{` and
    # `}` don't collide with `str.format` placeholders.  The figure exporter
    # and the inlined d3/KaTeX ride the same mechanism, for the same reason;
    # the libraries go in last, so no later replace scans them.
    html = html.replace("<!--METHODS_HTML-->", methods_panel_html())
    html = html.replace(CSS_PLACEHOLDER, figure_export_css())
    html = html.replace(JS_PLACEHOLDER, figure_export_js())
    html = html.replace(VENDOR_PLACEHOLDER, vendor_assets_html())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


__all__ = ["write_corpus_dashboard", "extract_play_summary"]
