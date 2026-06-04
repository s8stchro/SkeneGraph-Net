"""Corpus-level dashboard.

Bundles a one-row-per-play summary (metrics + cast composition + segment
indices + a compact per-segment beat-rate / size / verse array for overlay
plots) into a single self-contained HTML page.

Layout
------
   ┌─────────────────────────────────────────────────────────┐
   │ Header (corpus name, plays, authors, segmentation tabs)  │
   ├─────────────────────────────────────────────────────────┤
   │ Corpus summary KPIs (totals + means + ranges)            │
   ├──────────────────────────┬──────────────────────────────┤
   │ Network-topology scatter │ Trilcke/Fischer typology     │
   │ density × avg degree     │ drama-change × final-scene   │
   ├─────────────────────────────────────────────────────────┤
   │ Cast composition stacked bars (speakers / mutes …)       │
   ├─────────────────────────────────────────────────────────┤
   │ Beat-chart small multiples (one per play)                │
   ├─────────────────────────────────────────────────────────┤
   │ Sortable plays table -- click a row to open per-play     │
   │ dashboard                                                 │
   └─────────────────────────────────────────────────────────┘

Departures from the per-play dashboard (small but meaningful):
* No mute-toggle, no force controls, no dynamic graph: this is a
  comparative view, not a per-play exploration tool.
* All five panels react to the segmentation tab.
* Click a play row -> opens its per-play dashboard in the same tab,
  so the corpus dashboard works as a navigation hub.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import networkx as nx  # noqa: F401  (re-export of types used by callers)

from methods_content import methods_panel_html


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
    def _pick_demographics(mute_mode: str) -> Dict:
        if not results:
            return {}
        any_mode = next(iter(results.values()))
        groups = sorted({r.passive for r in play.relations
                         if r.name == "partOf" and r.passive in play.characters})
        target_key = f"{mute_mode}:" + ",".join(groups) if groups else None
        variants = any_mode.get("variants") or {}
        if target_key and target_key in variants:
            return variants[target_key]["metrics"].get("demographics", {})
        # No partOf aggregation possible.  Fall back to the appropriate
        # top-level demographics: for "stage" that's the raw metrics;
        # for "dialogic" / "cospeech" that's variants["dialogic:"] /
        # variants["cospeech:"] respectively.
        if mute_mode != "stage":
            v = variants.get(f"{mute_mode}:")
            if v is not None:
                return v["metrics"].get("demographics", {})
        return any_mode["metrics"].get("demographics", {})

    def _ratios(dem: Dict) -> Dict:
        speakers = dem.get("speakers", 0)
        mutes = dem.get("mutes", 0)
        total = speakers + mutes
        coll_spk = dem.get("collective_speakers", 0)
        sx = dem.get("sex", {"male": 0, "female": 0, "unspecified": 0})
        female = sx.get("female", 0)
        male = sx.get("male", 0)
        return {
            "speakers_share":            (speakers / total) if total else None,
            "collective_speakers_share": (coll_spk / speakers) if speakers else None,
            "female_share":              (female / (female + male)) if (female + male) else None,
        }

    composition = {
        "stage":    _ratios(_pick_demographics("stage")),
        "dialogic": _ratios(_pick_demographics("dialogic")),
        "cospeech": _ratios(_pick_demographics("cospeech")),
    }

    # Genre heuristic by author + play id (the id carries the Latin
    # transliteration even when <author> is in Greek script).  Stand-in
    # for a TEI <classCode> until the corpus annotates genre explicitly.
    # Used by the corpus chorus beat chart to sort plays as
    # genre -> author -> title.  Recognises both Latin transliterations
    # and the Greek-script canonical forms; unknown authors collapse to
    # "other", sorted last.
    def _genre_of(author: str, play_id: str) -> str:
        a = ((author or "") + " " + (play_id or "")).lower()
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
        "author": play.author or "",
        "genre": _genre_of(play.author or "", play.play_id or ""),
        "dashboard_href": dashboard_href,
        "composition": composition,
        "segmentations": {},
    }
    for mode, r in results.items():
        m = r["metrics"]
        segs = r["segments"]

        # Beat-chart rates (Jaccard distance between consecutive casts).
        # Skip the artificial transition from an empty pre-play segment 0
        # (always 1.0 by definition, omitted in Fischer/Trilcke 2017 Fig. 4).
        def jaccard_series(cast_fn):
            start_i = (1 if (segs and segs[0].is_initial and not cast_fn(segs[0])) else 0)
            out: List[float] = []
            for i in range(start_i, len(segs) - 1):
                a, b = cast_fn(segs[i]), cast_fn(segs[i + 1])
                u = a | b
                out.append((len(a ^ b) / len(u)) if u else 0.0)
            return out

        rates_stage = jaccard_series(lambda s: s.characters_present)
        verses_per_segment = [s.verse_count for s in segs]

        # partOf groups for this play (chorus semi-choruses etc.).  The
        # fully-aggregated variant key joins every group id; an empty
        # agg_key means the play has no aggregable groups, so no agg view
        # exists.  Computed once here because both the demographics picker
        # and the mode blocks below need it.
        groups = sorted({rel.passive for rel in play.relations
                         if rel.name == "partOf" and rel.passive in play.characters})
        agg_key = ",".join(groups) if groups else ""

        # Build one "mode block" per (mute mode, aggregation state) -- same
        # field shape as the top-level (stage-mode raw) fields, so the JS
        # segOf(p) just returns the appropriate sub-dict.  `agg=True` reads
        # the partOf-aggregated variant (semi-choruses collapsed to one
        # node); change rates, per-segment series, speech distribution and
        # segment indices are all taken from that variant so order,
        # density, DCR, Gini and the beat-chart series reflect the
        # collapse.  For the raw blocks speech_distribution / segment_indices
        # are play-level constants shared from the stage view (the cast
        # filter does not change which characters speak), preserving the
        # existing dialogic / cospeech behaviour exactly.
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
            if mute_mode == "cospeech":
                cast = lambda s: s.speakers
            elif mute_mode == "dialogic":
                kept = {n["id"] for n in mo.get("nodes", [])}
                cast = lambda s: s.characters_present & kept
            else:  # stage
                cast = lambda s: s.characters_present
            start_i = (1 if (mo_segs and mo_segs[0].is_initial
                             and not cast(mo_segs[0])) else 0)
            seg_change = []
            for i in range(start_i, len(mo_segs) - 1):
                a, b = cast(mo_segs[i]), cast(mo_segs[i + 1])
                u = a | b
                seg_change.append((len(a ^ b) / len(u)) if u else 0.0)
            size_per_seg = [len(cast(s)) for s in mo_segs]
            # Aggregation merges chorus-half speaker identities, so the
            # verse distribution and segment-occupancy indices change; take
            # them from the variant.  Raw blocks keep the shared stage view.
            if agg:
                speech_dist = mo.get("speech_distribution", m.get("speech_distribution", {}))
                seg_idx     = mo.get("segment_indices", m.get("segment_indices", {}))
            else:
                speech_dist = m.get("speech_distribution", {})
                seg_idx     = m.get("segment_indices", {})
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
                "size_per_segment":   size_per_seg,
                "verses_per_segment": [s.verse_count for s in mo_segs],
            }

        # Chorus beat-chart data for the corpus chart.  One row per
        # chorus character per (mute_mode, agg_state) combination.  Read
        # the chorus character list from each variant's character set
        # (filtered by is_chorus), then for each chorus character emit
        # its per-segment verses + presence within that variant's segments.
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
            n_all = len(variant_segments)
            lo, hi = 0, n_all
            while lo < hi and not variant_segments[lo].characters_present:
                lo += 1
            while hi > lo and not variant_segments[hi - 1].characters_present:
                hi -= 1
            active = variant_segments[lo:hi]
            out = []
            for cid, ch in chorus_chars:
                verses = []
                present = []
                for s in active:
                    vbs = {}
                    for sp in s.speeches:
                        if sp.verse_count > 0:
                            for who in sp.who:
                                vbs[who] = vbs.get(who, 0) + sp.verse_count
                    verses.append(vbs.get(cid, 0))
                    present.append(cid in s.characters_present)
                out.append({
                    "id":      cid,
                    "name":    ch.display_name,
                    "verses":  verses,
                    "present": present,
                })
            return out

        # Resolve the six (mute_mode, agg_state) variants.  Top-level
        # results carry the stage-mode raw view; r["variants"] carries
        # dialogic, cospeech, and all partOf-aggregated variants.  When
        # a play has no partOf groups, the agg view falls back to the
        # raw view of the same mute mode.
        v = r.get("variants") or {}
        def _resolve(mute, agg):
            if mute == "stage" and not agg:
                return {"characters": play.characters, "segments": segs}
            key = f"{mute}:{agg_key}" if agg else f"{mute}:"
            entry = v.get(key)
            if entry:
                return {"characters": entry["play"].characters,
                        "segments":   entry["segments"]}
            # Fall back to raw view at this mute mode (if not stage).
            if mute != "stage":
                fb = v.get(f"{mute}:")
                if fb:
                    return {"characters": fb["play"].characters,
                            "segments":   fb["segments"]}
            return {"characters": play.characters, "segments": segs}

        chorus_data = {}
        for mute in ("stage", "dialogic", "cospeech"):
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
            "size_per_segment":   [len(s.characters_present) for s in segs],
            "verses_per_segment": verses_per_segment,
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
            "dialogic":           _attach_agg(_build_mode_block("dialogic"),
                                              _build_mode_block("dialogic", agg=True)),
            "cospeech":           _attach_agg(_build_mode_block("cospeech"),
                                              _build_mode_block("cospeech", agg=True)),
            "agg":                _build_mode_block("stage", agg=True),
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
<script src="https://d3js.org/d3.v7.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
<style>
:root {{
  --bg: #fafafa; --panel: #ffffff; --border: #e0e0e0;
  --ink: #1a1a1a; --muted: #666; --accent: #1a5fb4;
  --speaker: #e07a5f; --mute: #aaa; --chorus: #4daf4a;
  --collective: #377eb8; --beat: #b73779;
  --tragedy: #1f78b4; --comedy: #e31a1c;
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
#sizing-chart, #scaling-chart, #topology-chart, #typology-chart,
#gini-avgdeg-chart, #share-gini-chart, #share-avgdeg-chart {{
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
/* Anchor / display-only / color-dot extensions to the chip control.
   An "anchor" chip contributes to the corpus median computations;
   a "display-only" chip is visible on the chart but is excluded from
   the median and the iso-curve.  Visual distinction: display-only is
   italic + light opacity + no anchor glyph.  The colour dot inside
   each chip controls the play's dot colour in the scatters; click it
   to cycle through the palette without changing the chip's state. */
.selector-chips .chip-toggle .anchor-mark {{ font-size: 9.5px;
  margin-right: 2px; opacity: 0.85; }}
.selector-chips .chip-toggle.display-only {{ background: #f4f4f4;
  color: #6b6b6b; border-color: #d4d4d4; font-style: italic; }}
.selector-chips .chip-toggle.display-only:hover {{ background: #ebebeb;
  color: #4a4a4a; }}
.selector-chips .chip-toggle.display-only .anchor-mark {{ display: none; }}
.selector-chips .chip-toggle .color-dot {{ display: inline-block;
  width: 9px; height: 9px; border-radius: 50%; margin: 0 4px 0 1px;
  cursor: pointer; border: 1px solid rgba(0,0,0,0.25);
  vertical-align: middle; transition: transform 0.08s; }}
.selector-chips .chip-toggle .color-dot:hover {{ transform: scale(1.35);
  border-color: #000; }}
/* Subset toolbar appendix: anchor-only quick action */
.selector-bar .actions button.anchors-btn {{ background: #f5f5f5; }}
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
.small-multiples {{ display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px; }}
.small-multiples .sm {{ background: #fafafa; border: 1px solid #f0f0f0;
  border-radius: 3px; padding: 4px 6px; }}
.small-multiples .sm .title {{ font-size: 11px; color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  margin-bottom: 2px; }}
.small-multiples .sm svg {{ width: 100%; height: 80px; display: block; }}
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
.panel.graph.chart-fullscreen #topology-chart,
.panel.graph.chart-fullscreen #typology-chart,
.panel.graph.chart-fullscreen #gini-avgdeg-chart,
.panel.graph.chart-fullscreen #share-gini-chart,
.panel.graph.chart-fullscreen #share-avgdeg-chart,
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
   toggle picks up the new container width. */

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
/* Default stroke / stroke-width come from drawScatter's attr() calls so that
   flagged (out-of-iso-domain) points can stroke themselves in --accent.
   The :hover rule still wins (CSS > presentation attribute) on hover. */
.dot {{ cursor: pointer; }}
.dot:hover {{ stroke: black !important; stroke-width: 1.8; }}
.legend {{ font-size: 11px; color: var(--muted); margin-top: 8px;
  display: flex; gap: 14px; flex-wrap: wrap; }}
.legend .swatch {{ display: inline-block; width: 10px; height: 10px;
  vertical-align: middle; margin-right: 3px; border-radius: 2px; }}
</style>
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
      <label><input type="radio" name="mute-mode" value="stage" checked>
        stage co-presence
        <span class="detail">(all on-stage characters as nodes)</span></label>
      <label><input type="radio" name="mute-mode" value="dialogic">
        dialogic cast on play level
        <span class="detail">(drop play-level mutes)</span></label>
      <label><input type="radio" name="mute-mode" value="cospeech">
        dialogic cast on segment level
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
        all panels, scatters, tables, and reference curves recompute against
        the active subset</span>
    </h3>
    <div class="selector-bar">
      <span>Selected: <span class="count" id="plays-count">&mdash;</span></span>
      <span class="actions">
        <button id="sel-all">select all</button>
        <button id="sel-none">select none</button>
        <button id="sel-invert">invert</button>
        <button id="reset-colors" title="reset all per-play dot colours to default">reset colours</button>
      </span>
    </div>
    <div id="plays-selector" class="selector-chips"></div>
  </div>

  <div class="panel">
    <h3>Corpus summary</h3>
    <div id="kpis"></div>
  </div>

  <div class="row charts">
    <div class="panel graph">
      <h3>Density &times; order
        <span class="hint">dashed deep red = iso-degree curve at the corpus median &lang;k&rang;
          &middot; red lines = pairs with &Delta;n &le; 5 (local-neighbourhood density variation)
          <label style="margin-left: 8px;">
            <input type="checkbox" id="show-pair-lines" checked> show pair-lines
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
      <h3>Density &times; average degree
        <span class="hint">density = avg-deg / (n &minus; 1); the curve = order</span>
      </h3>
      <svg id="topology-chart"></svg>
    </div>
    <div class="panel graph">
      <h3>Drama-dynamics typology
        <span class="hint">drama-change rate &times; &sigma; &middot; Fischer / Trilcke 2017, Fig. 8-9 (high- vs low-dynamic plays)</span>
      </h3>
      <svg id="typology-chart"></svg>
    </div>
    <div class="panel graph">
      <h3>Gini &times; average degree
        <span class="hint">speech inequality &times; network density &middot; star vs ensemble dramaturgies</span>
      </h3>
      <svg id="gini-avgdeg-chart"></svg>
    </div>
    <div class="panel graph">
      <h3>Top-speaker share &times; Gini
        <span class="hint">lead dominance &times; full-distribution inequality &middot; star vs coalitional vs ensemble</span>
      </h3>
      <svg id="share-gini-chart"></svg>
    </div>
    <div class="panel graph">
      <h3>Top-speaker share &times; average degree
        <span class="hint">lead dominance &times; network density &middot; do single-hero plays sit on sparser networks?</span>
      </h3>
      <svg id="share-avgdeg-chart"></svg>
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
    <div id="beat-multiples" class="small-multiples"></div>
  </div>

  <div class="panel graph">
    <h3>Chorus presence across the play
      <span class="hint">one row per chorus &middot; x normalised per play so distribution shapes are comparable
      &middot; sorted genre &rarr; author &rarr; title</span>
    </h3>
    <div class="chorus-controls">
      <span class="legend-inline">
        <span><span class="swatch-grey"></span>present, silent</span>
        <span><span class="swatch-gradient"></span>speaking (verses, &radic; scale)</span>
      </span>
    </div>
    <svg id="chorus-beat-chart"></svg>
  </div>

  <div class="panel">
    <h3>Plays
      <span class="hint">click any row to open the per-play dashboard
        &middot; <code>seg</code> = segments on the active model's spine
        (under sd the mutes-out models fold boundaries they cannot see, so
        it drops when you switch model; fixed for div2 / div3)</span>
    </h3>
    <div class="scroll"><table id="plays-table"></table></div>
  </div>
</main>

<main class="view view-methods hidden" data-view="methods">
  <!--METHODS_HTML-->
</main>

<script>
const DATA = {data_json};

// Dashboard-internal key for state Sets / Maps.  Uses the play's
// English title (<title xml:lang="en">) as the unique key, since
// p.id (play_id, derived from the TEI header) is not guaranteed unique
// when the corpus contains rigged variants of the same play.  The
// methodological contract is that each play in the corpus carries a
// distinct <title xml:lang="en">; with that contract held, every chip
// and every dot keys cleanly off the title.  Fallback to p.id then
// p.title_grc when title_en is absent.
function _playKey(p) {{
  return p.title_en || p.title_grc || p.id;
}}

const MODE_ORDER = ["sd", "div2", "div3"];

// A mode is "available" if at least one play has it.
const AVAILABLE_MODES = MODE_ORDER.filter(m =>
  DATA.plays.some(p => p.segmentations && p.segmentations[m]));

// Labels and details for the three mute modes -- single source of truth
// for the active-filters chip strip, hint text, and the radio fieldset.
const MUTE_MODE_LABELS = {{
  stage:    {{ label: "stage co-presence",
               detail: "all on-stage characters as nodes" }},
  dialogic: {{ label: "dialogic cast on play level",
               detail: "drop play-level mutes" }},
  cospeech: {{ label: "dialogic cast on segment level",
               detail: "only segment-active speakers" }},
}};

const STATE = {{
  seg: AVAILABLE_MODES[0] || "sd",
  // Three-state network model.  See dashboard.py for the orthogonal
  // (include_mutes, edge_rule) axes underneath: stage = (T, presence);
  // dialogic = (F, presence); cospeech = (F, co_speech).  The radio
  // group in the seg-tabs row drives this.
  muteMode: "stage",
  // Global partOf aggregation: True = collapse chorus halves (e.g.
  // Lysistrata's chorosAndron + chorosGynaikon -> choros) into a single
  // node everywhere; False = treat each half separately.  Routed through
  // segOf(p), so it cascades through every scatter, the iso-curve and
  // pair-lines, the composition bars, the KPI ranges, the plays table and
  // the beat multiples -- not just the chorus heat-map.  Plays without
  // aggregable partOf groups are unaffected (segOf keeps their raw block).
  aggregateChorus: false,
  // Only consumed by the density x order chart: when True, draw thin
  // grey lines connecting every pair of plays with similar order
  // (Delta n <= 5).  Methodologically these visualise the
  // local-neighbourhood density variation -- the corpus's natural
  // "noise floor" against which iso-curve deviations can be calibrated.
  // Plays without nearby-order neighbours (e.g. Knights at n=8) have
  // no incident lines.  Lysistrata's lines are visibly taller than any
  // other pair's, which is the visual signature of the methodological
  // argument.
  showPairLines: true,
  // Set of play ids currently included.  Initialised to the full
  // corpus on load.  Every consumer of activePlays() filters through
  // this -- so unticking a chip in the selector cascades through KPIs,
  // every scatter chart's iso-curve and median crosshair, the beat
  // multiples, the chorus chart, and the plays table at once.  This is
  // by design: the "corpus median" is defined relative to whatever
  // subset is held in mind.
  selectedPlays: new Set(DATA.plays.map(p => _playKey(p))),
  // Anchor set: the plays that contribute to corpus aggregates (median,
  // iso-curve k_median, KPI ranges).  Always a subset of selectedPlays.
  // A play in selectedPlays but NOT in anchorPlays is "display-only":
  // visible on the chart, but excluded from the reference calculation.
  // The methodological motive: rigged variants (e.g. partOf-aggregated
  // versions of one play) are not independent observations and should
  // not pollute the corpus median.  Initialised to the full corpus.
  anchorPlays: new Set(DATA.plays.map(p => _playKey(p))),
  // Per-play color override for scatter dots.  Maps play id -> palette
  // index (0..PLAY_COLOR_PALETTE.length - 1).  Unset plays use index 0
  // (the default accent colour).  The chip's small colour dot is
  // clickable and cycles through the palette.
  playColors: {{}},
}};

// Compact qualitative palette for per-play dot recolouring.  Index 0 is
// the default (matches the original accent blue).  The remaining
// entries are chosen for distinguishability under sequential cycling
// and reasonable contrast against the white plot background.
const PLAY_COLOR_PALETTE = [
  "var(--accent)",   // 0 - default blue (matches everything else in the dashboard)
  "#e07a5f",         // 1 - coral / orange-red  (useful for highlighting one play)
  "#4daf4a",         // 2 - green
  "#b73779",         // 3 - magenta
  "#ff7f00",         // 4 - bright orange
  "#984ea3",         // 5 - purple
  "#525252",         // 6 - dark grey (de-emphasis)
];

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
  // Each non-default mode (dialogic, cospeech) lives in a parallel
  // sub-dict on the segmentation entry, with the same field shape as
  // the top-level (stage-mode) fields, so every consumer below (KPI,
  // scatter, bar chart, table, beat charts) works without case-splits.
  // Missing sub-dicts fall back to the top-level stage view.
  const base = (p.segmentations || {{}})[STATE.seg];
  if (!base) return null;
  const m = STATE.muteMode || "stage";
  let block = base;
  if (m === "dialogic" && base.dialogic) block = base.dialogic;
  else if (m === "cospeech" && base.cospeech) block = base.cospeech;
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
  const ml = MUTE_MODE_LABELS[STATE.muteMode] || MUTE_MODE_LABELS.stage;
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
  // Anchor chip: shown only when anchors != selection (i.e. some plays
  // are display-only).  Lets screenshots document not just "which plays
  // we're looking at" but "which plays count as the reference set".
  const anch = STATE.anchorPlays ? STATE.anchorPlays.size : total;
  if (anch !== sel) {{
    html += ' <span class="filter-chip">anchors '
         + '<span class="detail">' + anch + ' / ' + sel + ' selected</span></span>';
  }}
  host.innerHTML = html;
  // Topbar may have grown / shrunk because of the chip strip wrap;
  // re-measure so the sticky tabs and selector pin at the right offsets.
  if (typeof updateStickyOffsets === "function") updateStickyOffsets();
}}

function activePlays() {{
  return DATA.plays.filter(p => segOf(p)
    && (!STATE.selectedPlays || STATE.selectedPlays.has(_playKey(p))));
}}
// Plays that contribute to the corpus reference computations.  This is
// the intersection of selectedPlays and anchorPlays (the latter never
// extends beyond the former in normal operation, but the intersection
// is defensive in case of state drift).  Reference quantities -- the
// iso-degree curve's k_median, the median crosshair on every scatter,
// the KPI ranges in the corpus summary panel -- should all be computed
// against this set, not against activePlays().
function anchorPlays() {{
  return DATA.plays.filter(p => {{
    const k = _playKey(p);
    return segOf(p)
        && STATE.selectedPlays && STATE.selectedPlays.has(k)
        && STATE.anchorPlays    && STATE.anchorPlays.has(k);
  }});
}}
// Resolve the colour for a play's scatter dot.  Defaults to palette[0]
// (the accent blue) when the play has no explicit override.
function playColor(p) {{
  const idx = STATE.playColors[_playKey(p)];
  if (idx == null || idx < 0 || idx >= PLAY_COLOR_PALETTE.length) {{
    return PLAY_COLOR_PALETTE[0];
  }}
  return PLAY_COLOR_PALETTE[idx];
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
  // Tri-state per chip:
  //   "off"          = not selected, not visible, not in reference
  //   "anchor"       = selected, visible, AND counts in corpus median
  //   "display-only" = selected, visible, but NOT in median
  // Click on the chip body cycles off -> anchor -> display-only -> off.
  // Click on the colour dot (left inside the chip) cycles the play's
  // dot colour through PLAY_COLOR_PALETTE without changing state.
  function chipStateOf(key) {{
    if (!STATE.selectedPlays.has(key)) return "off";
    return STATE.anchorPlays.has(key) ? "anchor" : "display-only";
  }}
  function cycleChipState(key) {{
    const s = chipStateOf(key);
    if (s === "off") {{
      STATE.selectedPlays.add(key);
      STATE.anchorPlays.add(key);
    }} else if (s === "anchor") {{
      // demote: keep selected but drop from anchor set
      STATE.anchorPlays.delete(key);
    }} else {{ // display-only
      STATE.selectedPlays.delete(key);
      STATE.anchorPlays.delete(key);
    }}
  }}
  function cyclePlayColor(key) {{
    const cur = STATE.playColors[key] || 0;
    STATE.playColors[key] = (cur + 1) % PLAY_COLOR_PALETTE.length;
  }}

  const chips = host.selectAll(".chip-toggle").data(plays, p => _playKey(p))
    .enter().append("span")
    .attr("class", p => {{
      const s = chipStateOf(_playKey(p));
      // .on for the anchor state; .off for off; .display-only adds the
      // "selected but not in reference" italic / lighter styling.
      if (s === "off") return "chip-toggle off";
      if (s === "anchor") return "chip-toggle on";
      return "chip-toggle on display-only";
    }})
    .attr("title", p => {{
      const s = chipStateOf(_playKey(p));
      const stateLabel = (s === "anchor" ? "in reference"
                        : s === "display-only" ? "display only (not in reference)"
                        : "excluded");
      return (p.author || "") + (p.author ? " - " : "")
           + (p.title_en || p.id) + " - " + stateLabel
           + "\\n(click body: cycle state; click dot: cycle colour)";
    }})
    .on("click", (event, p) => {{
      // Ignore clicks on the colour dot -- that handler runs separately
      // and stops propagation.  Without this guard d3's binding would
      // also fire the chip body handler on a colour-dot click.
      if (event.target.classList.contains("color-dot")) return;
      cycleChipState(_playKey(p));
      renderActiveFilters();
      render();
    }});

  // State / anchor mark (Unicode check / cross).  Display-only chips
  // drop the anchor glyph via CSS rule on .display-only .anchor-mark.
  chips.append("span").attr("class", "mark")
    .text(p => STATE.selectedPlays.has(_playKey(p)) ? "\\u2713" : "\\u2715");
  chips.append("span").attr("class", "anchor-mark")
    .text(p => STATE.anchorPlays.has(_playKey(p)) ? "\\u2693" : "");

  // Colour dot: small clickable circle.  Click cycles the palette index
  // for this play's dot colour in every scatter chart.  Propagation
  // stopped so it does not also cycle the chip state.
  chips.append("span").attr("class", "color-dot")
    .style("background", p => playColor(p))
    .on("click", (event, p) => {{
      event.stopPropagation();
      cyclePlayColor(_playKey(p));
      render();
    }});

  chips.append("span").attr("class", "chip-label").text(p => shortTitle(p));

  // Counter: "anchors / selected / total" when those differ, else just "N / total"
  const sel = STATE.selectedPlays.size;
  const anch = STATE.anchorPlays.size;
  const tot = plays.length;
  let countText;
  if (anch === sel) countText = sel + " / " + tot;
  else              countText = anch + " anchor + " + (sel - anch) + " display-only / " + tot;
  document.getElementById("plays-count").textContent = countText;
}}

// -------------------------------------------------------------------- tabs
function renderTabs() {{
  const tabs = d3.select("#seg-tabs");
  const labels = {{ sd: "Stage directions", div2: "div2", div3: "div3" }};
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
  const dcr    = get(s => s.segment_indices && s.segment_indices.all_in_index);  // placeholder
  // True drama-change rate from change_rates:
  const dcrs   = ps.map(p => mean(segOf(p).change_rates || [])).filter(x => x > 0);
  const finals = get(s => s.segment_indices && s.segment_indices.final_scene_size);
  const sizes  = get(s => s.size);
  const speakers = get(s => (s.demographics && s.demographics.speakers) || 0);
  const mutes    = get(s => (s.demographics && s.demographics.mutes) || 0);
  const topShare = get(s => (s.speech_distribution && s.speech_distribution.top_speaker_verse_share) || 0);
  const gini     = get(s => (s.speech_distribution && s.speech_distribution.gini_verses) || 0);

  function range(xs) {{
    if (!xs.length) return "\\u2014";
    return fmt(d3.min(xs)) + " \\u2013 " + fmt(d3.max(xs)) + " (mean " + fmt(mean(xs)) + ")";
  }}

  const sections = [
    {{ title: "Overview", items: [
      {{ k: "plays",                v: ps.length }},
      {{ k: "total characters",     v: d3.sum(sizes) }},
      {{ k: "total segments",       v: d3.sum(get(s => s.num_segments)) }},
      {{ k: "total verses spoken",  v: d3.sum(get(s => (s.speech_distribution || {{}}).total_verses_spoken || 0)) }},
    ]}},
    {{ title: "Network", items: [
      {{ k: "order (range)",       v: range(sizes) }},
      {{ k: "density",             v: range(dens) }},
      {{ k: "average degree",      v: range(aDeg) }},
    ]}},
    {{ title: "Composition", items: [
      {{ k: "speakers (range)",    v: range(speakers) }},
      {{ k: "mutes (range)",       v: range(mutes) }},
      {{ k: "speaker / mute ratio",
        v: fmt(d3.sum(speakers) / Math.max(1, d3.sum(mutes)), 2) }},
    ]}},
    {{ title: "Plot dynamics", items: [
      {{ k: "drama-change rate",   v: range(dcrs), beat: true }},
      {{ k: "final-scene size",    v: range(finals), beat: true }},
      {{ k: "top-speaker share",   v: range(topShare) }},
      {{ k: "Gini (verses)",       v: range(gini) }},
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

// -------------------------------------------------------------------- scatter helpers
//   `extras` (optional) is called as extras(svg, x, y, ps, geom) after the
//   axes and median crosshair are drawn but before the dots, so background
//   reference shapes (e.g. the iso-degree curve) sit behind the data.
//   `showMedian` (default true) controls whether the median crosshair is
//   drawn; pass false when an `extras` shape already supplies a better
//   reference (e.g. the iso-degree curve on density-vs-size).
//   `outOfDomain` (optional) is a predicate (d) => boolean.  When true,
//   that point lies outside the iso-curve / reference domain and is drawn
//   as a hollow ring with a tooltip note, signalling the comparison
//   doesn't apply there.
function drawScatter(selector, accX, accY, labelX, labelY,
                     extras, showMedian, outOfDomain) {{
  if (showMedian == null) showMedian = true;
  const flagged = (typeof outOfDomain === "function") ? outOfDomain : null;
  const svg = d3.select(selector);
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.selectAll("*").remove();
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);
  const M = {{top: 16, right: 18, bottom: 36, left: 50}};
  // All visible plays: activePlays() = selectedPlays (display set).
  // Reference computations (median crosshair, iso-curve k_median): use
  // the anchor subset, which excludes "display-only" plays.
  const ps = activePlays().map(p => ({{p, x: accX(segOf(p)), y: accY(segOf(p))}}))
                          .filter(d => d.x != null && d.y != null && !Number.isNaN(d.x) && !Number.isNaN(d.y));
  if (!ps.length) return;
  const anchorKeys = STATE.anchorPlays || new Set();
  const refPs = ps.filter(d => anchorKeys.has(_playKey(d.p)));

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

  // Median reference crosshair: descriptive anchor, not a regression.  Drawn
  // before the dots so the points sit on top.  Lines only -- no labels,
  // so the chart stays uncluttered (medians are also reported in the KPI
  // panel and the plays table).  Computed over the ANCHOR set, so
  // display-only plays do not perturb the reference.  If anchor set is
  // empty, fall back to all displayed plays (graceful degradation).
  if (showMedian) {{
    const refForMed = refPs.length ? refPs : ps;
    const medX = median(refForMed.map(d => d.x));
    const medY = median(refForMed.map(d => d.y));
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

  if (typeof extras === "function") extras(svg, x, y, ps, {{w: w, h: h, M: M, refPs: refPs}});

  // Coincident-dot disambiguation.  Plays with identical (x, y) (e.g.,
  // Wealth and Thesmophoriazusae at order=13 / avg-deg=4.62 on
  // average-degree x order) would render as a single overlapping dot,
  // and only the topmost would receive mouse events.  Group ps by
  // rounded screen position; for each group of 2+, distribute the dots
  // radially around the original centre so each gets its own
  // clickable / hoverable area.  Each dot stores its offset in _dx/_dy
  // (read below when positioning circle and label).
  const _coinGroups = new Map();
  for (const d of ps) {{
    const k = Math.round(x(d.x)) + "," + Math.round(y(d.y));
    if (!_coinGroups.has(k)) _coinGroups.set(k, []);
    _coinGroups.get(k).push(d);
  }}
  const _coinOffsetR = dotR * 1.4;
  for (const grp of _coinGroups.values()) {{
    if (grp.length <= 1) {{
      if (grp.length === 1) {{ grp[0]._dx = 0; grp[0]._dy = 0; }}
      continue;
    }}
    // Distribute around a circle, starting from due north for stable
    // ordering.  Two coincident dots produce a vertical pair; three a
    // triangle; etc.  Visual radius _coinOffsetR scales with dot size.
    for (let i = 0; i < grp.length; i++) {{
      const a = (2 * Math.PI * i) / grp.length - Math.PI / 2;
      grp[i]._dx = _coinOffsetR * Math.cos(a);
      grp[i]._dy = _coinOffsetR * Math.sin(a);
    }}
  }}

  // Dot rendering.  Each play gets:
  //   - fill colour = palette[STATE.playColors[id] || 0] (the chip's dot)
  //   - opacity 1.0 if anchor, 0.55 if display-only (visible but
  //     visibly distinct from the reference set)
  //   - hollow ring when flagged out-of-domain (preserves the existing
  //     iso-curve flagging convention)
  const dots = svg.append("g").selectAll("circle").data(ps).enter().append("circle")
    .attr("class", d => "dot" + (anchorKeys.has(_playKey(d.p)) ? "" : " display-only"))
    .attr("cx", d => x(d.x) + (d._dx || 0))
    .attr("cy", d => y(d.y) + (d._dy || 0))
    .attr("r", dotR)
    .attr("fill",   d => (flagged && flagged(d)) ? "white"      : playColor(d.p))
    .attr("stroke", d => (flagged && flagged(d)) ? playColor(d.p) : "white")
    .attr("stroke-width", d => (flagged && flagged(d)) ? (isBig ? 2.4 : 1.6) : (isBig ? 1.8 : 1.2))
    .attr("opacity", d => anchorKeys.has(_playKey(d.p)) ? 1.0 : 0.55)
    .on("click", (_, d) => {{ if (d.p.dashboard_href) window.location.href = d.p.dashboard_href; }});
  dots.append("title").text(d => {{
    let t = (d.p.title_en || d.p.id) + "\\n" +
            labelX + " = " + fmt(d.x) + "\\n" +
            labelY + " = " + fmt(d.y);
    if (flagged && flagged(d)) t += "\\n(outside iso-curve domain: n \\u2264 k + 1)";
    return t;
  }});

  // Labels above points (compact, only if not too crowded).
  // Inherit the coincidence offset so labels track their displaced dots.
  if (ps.length <= 20) {{
    svg.append("g").selectAll("text.lab").data(ps).enter().append("text")
      .attr("class", "lab")
      .attr("x", d => x(d.x) + (d._dx || 0) + (isBig ? 12 : 7))
      .attr("y", d => y(d.y) + (d._dy || 0) + (isBig ? 5 : 3))
      .attr("font-size", playLabelFont).attr("fill", "#555")
      .text(d => shortTitle(d.p));
  }}
}}
function shortTitle(p) {{
  // Play title only -- not poet name.  `p.id` includes the author prefix
  // ("Aristophanes' Acharnians") so we prefer title_en / title_grc and only
  // fall back to a trimmed id.
  let t = (p.title_en || p.title_grc || "").trim();
  if (!t && p.id) {{
    // Strip a leading "Author's " or "Author-" prefix from the id.
    t = p.id.replace(/^[^'\\-\\s]+[\\s\\-']+/, "").trim();
  }}
  return t.length > 16 ? t.slice(0, 15) + "\\u2026" : t;
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
      .append("title").text(`${{p.title_en || p.id}}: ${{d.speakers}} speakers + ${{d.mutes}} mutes`);
    bg.append("rect")
      .attr("x", x0).attr("y", y(d.speakers))
      .attr("width", bw).attr("height", y(0) - y(d.speakers))
      .attr("fill", "var(--speaker)")
      .on("click", () => {{ if (p.dashboard_href) window.location.href = p.dashboard_href; }})
      .append("title").text(`${{p.title_en || p.id}}: ${{d.speakers}} speakers`);
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
  cells.append("div").attr("class", "title").text(p => p.title_en || p.id);
  cells.each(function(p) {{
    const svg = d3.select(this).append("svg");
    requestAnimationFrame(() => drawBeatMini(svg, p));
  }});
}}
function drawBeatMini(svg, p) {{
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);
  const rates = (segOf(p) || {{}}).change_rates || [];
  if (!rates.length) return;
  const M = {{top: 4, right: 4, bottom: 12, left: 14}};
  const x = d3.scaleLinear().domain([0, rates.length - 1]).range([M.left, w - M.right]);
  const y = d3.scaleLinear().domain([0, 1]).range([h - M.bottom, M.top]);
  // Mean (drama-change rate).
  const mu = mean(rates);
  svg.append("line")
    .attr("x1", M.left).attr("x2", w - M.right)
    .attr("y1", y(mu)).attr("y2", y(mu))
    .attr("stroke", "var(--speaker)").attr("stroke-dasharray", "2,2").attr("stroke-width", 1);
  svg.append("path")
    .attr("fill", "none").attr("stroke", "var(--beat)").attr("stroke-width", 1.1)
    .attr("d", d3.line().x((_, i) => x(i)).y(d => y(d))(rates));
  svg.append("text").attr("x", w - M.right).attr("y", h - 2)
    .attr("text-anchor", "end").attr("font-size", 9)
    .attr("fill", "var(--muted)").text("\\u03BC = " + fmt(mu));
}}

// -------------------------------------------------------------------- chorus beat chart
//   One row per chorus character per play, x-axis normalised to [0, 1] of
//   each play's segment range so distribution shapes are comparable across
//   plays of different lengths.  Three-state encoding:
//     transparent  -> chorus not in characters_present for that segment
//     light grey   -> chorus is on stage but silent (0 verses)
//     red ramp     -> chorus speaks; intensity ~ sqrt(verses), saturating
//                     at the corpus maximum (so cross-play comparison of
//                     intensity is honest).
//   Sort order: genre -> author -> title -> chorus name.
function renderChorusBeat() {{
  const svg = d3.select("#chorus-beat-chart");
  svg.selectAll("*").remove();
  const ps = activePlays();
  const muteKey = STATE.muteMode || "stage";
  const aggKey  = STATE.aggregateChorus ? "agg" : "raw";
  const variantKey = muteKey + "_" + aggKey;

  // Build flat row list, one per chorus character.
  const rows = [];
  ps.forEach(p => {{
    const seg = (p.segmentations || {{}})[STATE.seg];
    if (!seg) return;
    const cd = (seg.chorus_data || {{}})[variantKey] || [];
    cd.forEach(ch => {{
      if (!ch || !ch.verses || !ch.verses.length) return;
      rows.push({{
        play: p,
        chorus: ch,
        nSegments: ch.verses.length,
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

  // Colour scale: sqrt against the global max verses across visible rows,
  // so a cell's saturation is directly comparable across the corpus.
  const allVerses = rows.flatMap(r => r.chorus.verses).filter(v => v > 0);
  const maxV = allVerses.length ? d3.max(allVerses) : 1;
  const color = d3.scaleSqrt().domain([1, maxV]).range(["#fcbba1", "#a50f15"]);
  const colorSilent = "#bbbbbb";

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
      .append("title").text(`${{r.play.title_en || r.play.id}} - ${{r.chorus.name}}`);

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

    const n = r.chorus.verses.length;
    const cellSpan = (w - padR - labelW) / n;
    for (let s = 0; s < n; s++) {{
      const v = r.chorus.verses[s];
      const pres = !!r.chorus.present[s];
      let fill;
      if (v > 0)      fill = color(v);
      else if (pres)  fill = colorSilent;
      else continue;  // transparent: skip drawing entirely
      svg.append("rect")
        .attr("x", labelW + s * cellSpan)
        .attr("y", y0 + 1)
        .attr("width", Math.max(0.6, cellSpan))
        .attr("height", rowH - 2)
        .attr("fill", fill)
        .style("cursor", "pointer")
        .on("click", () => {{ if (r.play.dashboard_href) window.location.href = r.play.dashboard_href; }})
        .append("title").text(
          `${{r.play.title_en || r.play.id}} - ${{r.chorus.name}}\\n` +
          `segment ${{s + 1}} / ${{n}}\\n` +
          (v > 0 ? `${{v}} verse${{v === 1 ? "" : "s"}}` : "present, silent"));
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
      const c = (p.composition || {{}})[STATE.muteMode || "stage"] || {{}};
      return fmt(c.speakers_share, 3);
    }}, true],
    ["col/spk", p => {{
      const c = (p.composition || {{}})[STATE.muteMode || "stage"] || {{}};
      return fmt(c.collective_speakers_share, 3);
    }}, true],
    ["f/(f+m)", p => {{
      const c = (p.composition || {{}})[STATE.muteMode || "stage"] || {{}};
      return fmt(c.female_share, 3);
    }}, true],
    ["edges",    p => segOf(p).numEdges, true],
    ["density",  p => fmt(segOf(p).density, 3), true],
    ["avg deg",  p => fmt(segOf(p).averageDegree, 2), true],
    // Segment count is model-specific under the sd spine: dialogic /
    // cospeech fold away boundaries triggered only by non-nodes (e.g. a
    // mute's entrance), so this column drops when you switch the model.
    // For div2 / div3 it is fixed (textual divisions).
    ["seg",      p => segOf(p).num_segments, true],
    ["DCR",      p => fmt(mean(segOf(p).change_rates || []), 3), true],
    ["all-in",   p => fmt((segOf(p).segment_indices || {{}}).all_in_index || 0, 3), true],
    ["final",    p => fmt((segOf(p).segment_indices || {{}}).final_scene_size || 0, 3), true],
    ["top spk",  p => {{
      const sd = segOf(p).speech_distribution || {{}};
      return (sd.top_speaker_id || "\\u2014") + " (" + fmt((sd.top_speaker_verse_share || 0) * 100, 1) + "%)";
    }}],
    ["Gini",     p => fmt((segOf(p).speech_distribution || {{}}).gini_verses || 0, 3), true],
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
  const sorted = rows.slice().sort((a, b) => {{
    const va = sortCol[1](a), vb = sortCol[1](b);
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
  // Density vs size, with an iso-degree reference curve at the corpus median
  // avg-degree (`density = k / (n - 1)`).  Plays on the curve have the
  // median per-character interaction count; plays above are denser than
  // expected for their size, plays below are sparser.  This is the trace
  // of "constant avg-degree" -- a descriptive reference, not a regression.
  //
  // The curve is undefined where n <= k (it would require density > 1).
  // Dots in that domain are drawn hollow + a tooltip note so the eye
  // doesn't accidentally compare them to a curve that isn't there.
  // k_median for the iso-curve: ANCHOR set only, so display-only
  // plays (rigged variants, ad-hoc additions the user wants to compare
  // against a stable reference) do not pollute the median.  Falls back
  // to activePlays if no anchors are set (graceful degradation).
  const _anchorForK = anchorPlays();
  const _kSource = _anchorForK.length ? _anchorForK : activePlays();
  const kSize = median(_kSource.map(p => segOf(p).averageDegree || 0));
  drawScatter("#sizing-chart",
    s => s.size, s => s.density,
    "order (kept characters)", "density",
    (svg, x, y, ps, geom) => {{
      // ─── Pair lines (drawn first, so iso-curve and dots overlay) ──
      // For every pair of plays with order difference <= 5, draw a
      // thin grey segment between them.  This is the model-free
      // complement to the iso-curve: short lines = local-neighbourhood
      // density variation; tall lines = a play whose density does not
      // match its nearest-order companions.  Lysistrata's incident
      // lines stand out visibly because there is no nearby-order play
      // with comparable density.
      if (STATE.showPairLines) {{
        const pairG = svg.append("g").attr("class", "pair-lines")
          .attr("stroke", "#d62728")
          .attr("stroke-width", 1.5)
          .attr("opacity", 0.75);
        for (let i = 0; i < ps.length; i++) {{
          for (let j = i + 1; j < ps.length; j++) {{
            if (Math.abs(ps[i].x - ps[j].x) > 5) continue;
            // Compute pairwise density excess (symmetric: max/min - 1)
            // for the tooltip so the line is interrogable.
            const dHi = Math.max(ps[i].y, ps[j].y);
            const dLo = Math.min(ps[i].y, ps[j].y);
            const pct = dLo > 0 ? ((dHi / dLo - 1) * 100).toFixed(1) : "n/a";
            const ln = pairG.append("line")
              .attr("x1", x(ps[i].x)).attr("y1", y(ps[i].y))
              .attr("x2", x(ps[j].x)).attr("y2", y(ps[j].y));
            ln.append("title").text(
              (ps[i].p.title_en || ps[i].p.id) + " (n=" + ps[i].x + ", d=" + ps[i].y.toFixed(3) + ")\\n" +
              "\\u2194 " +
              (ps[j].p.title_en || ps[j].p.id) + " (n=" + ps[j].x + ", d=" + ps[j].y.toFixed(3) + ")\\n" +
              "\\u0394n=" + Math.abs(ps[i].x - ps[j].x).toFixed(0) +
              "  \\u2022  density excess " + pct + "%");
          }}
        }}
      }}
      // ─── Iso-degree curve (existing) ───────────────────────────────
      const xDom = x.domain(), yDom = y.domain();
      const step = Math.max(0.25, (xDom[1] - xDom[0]) / 240);
      const pts = [];
      for (let n = Math.max(2, xDom[0]); n <= xDom[1]; n += step) {{
        const d = kSize / (n - 1);
        if (d >= yDom[0] && d <= yDom[1]) pts.push([n, d]);
      }}
      if (pts.length < 2) return;
      const lineGen = d3.line().x(p => x(p[0])).y(p => y(p[1]));
      svg.append("path")
        .attr("d", lineGen(pts))
        .attr("fill", "none")
        .attr("stroke", "#8b0000")
        .attr("stroke-width", 3)
        .attr("stroke-dasharray", "8,5")
        .attr("opacity", 1)
        .append("title").text("iso-degree curve at k = " + kSize.toFixed(2));
    }},
    /*showMedian=*/false,
    /*outOfDomain=*/(d) => d.x <= kSize + 1);
  drawScatter("#scaling-chart",
    s => s.size, s => s.averageDegree,
    "order (kept characters)", "average degree");
  drawScatter("#topology-chart",
    s => s.density, s => s.averageDegree,
    "density", "average degree");
  drawScatter("#typology-chart",
    s => mean(s.change_rates || []),
    s => stdev(s.change_rates || []),
    "drama-change rate", "\\u03C3 (change-rate stdev)");
  // Gini (verses) x average degree -- speech-inequality x network-density.
  // High Gini + high avg-deg = star-topology play (a few dominant speakers
  // also serve as connective hubs).  Low Gini + high avg-deg = ensemble.
  drawScatter("#gini-avgdeg-chart",
    s => (s.speech_distribution || {{}}).gini_verses || 0,
    s => s.averageDegree,
    "Gini (verses)", "average degree");
  // Top-speaker share x Gini -- lead dominance x full-distribution
  // inequality.  Both are speech-corpus metrics (independent of the
  // network model), so the chart is invariant under the mute toggle.
  // The two diverge when the lead does not dominate but the rest of
  // the cast is steeply distributed: that quadrant (low share + high
  // Gini) is the "coalitional protagonist" pattern -- a leader
  // amplified by strong deuteragonists rather than a sole hero.
  drawScatter("#share-gini-chart",
    s => (s.speech_distribution || {{}}).top_speaker_verse_share || 0,
    s => (s.speech_distribution || {{}}).gini_verses || 0,
    "top-speaker share", "Gini (verses)");
  // Top-speaker share x average degree -- lead dominance x network
  // density.  The third pairwise plot over share, Gini, and avg-deg;
  // share and Gini are speech metrics, avg-deg is the network metric,
  // so this chart responds to the mute toggle through the avg-deg
  // axis while the share axis stays fixed.  Methodologically the most
  // diagnostic of the three: under mutes-in, single-hero plays
  // (high share) cluster at moderate density while the
  // coalitional/ensemble plays scatter into both denser (Lysistrata)
  // and sparser regions; under mutes-out the anti-correlation
  // attenuates as the staging-density artefact in Lysistrata
  // dissolves.  The chart is therefore where the two-model
  // methodology becomes visually legible on a single scatter.
  drawScatter("#share-avgdeg-chart",
    s => (s.speech_distribution || {{}}).top_speaker_verse_share || 0,
    s => s.averageDegree,
    "top-speaker share", "average degree");
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

// Global partOf aggregation toggle.  Now drives segOf(p), so every chart,
// the iso-curve / pair-lines, the KPI ranges and the plays table react --
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

// Plays-selector quick actions.  Each rewrites STATE.selectedPlays and
// STATE.anchorPlays in lock-step (anchor = selected for sel-all / -none
// / -invert) so the buttons produce predictable states without leaving
// orphan display-only chips.  Per-chip refinement still works as before.
document.getElementById("sel-all").addEventListener("click", () => {{
  const all = new Set(DATA.plays.map(p => _playKey(p)));
  STATE.selectedPlays = all;
  STATE.anchorPlays   = new Set(all);
  renderActiveFilters();
  render();
}});
document.getElementById("sel-none").addEventListener("click", () => {{
  STATE.selectedPlays = new Set();
  STATE.anchorPlays   = new Set();
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
  STATE.anchorPlays   = new Set(next);
  renderActiveFilters();
  render();
}});
document.getElementById("reset-colors").addEventListener("click", () => {{
  STATE.playColors = {{}};
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
</body>
</html>
"""


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def write_corpus_dashboard(corpus_data: Dict, out_path: Path) -> Path:
    title = corpus_data.get("name") or "Corpus dashboard"
    authors = corpus_data.get("authors") or []
    sub_parts = [f"{len(corpus_data.get('plays', []))} plays"]
    if authors:
        sub_parts.append(", ".join(authors) if len(authors) <= 5 else f"{len(authors)} authors")
    sub_parts.append("dashboard generated by SkeneGraph-Net")
    subtitle = " &middot; ".join(sub_parts)
    data_json = json.dumps(corpus_data, ensure_ascii=False, sort_keys=True)
    html = _TEMPLATE.format(
        title=_html_escape(title),
        subtitle=subtitle,
        data_json=data_json,
    )
    # Inject the Methods tab via plain replace so KaTeX's literal `{` and
    # `}` don't collide with `str.format` placeholders.
    html = html.replace("<!--METHODS_HTML-->", methods_panel_html())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


__all__ = ["write_corpus_dashboard", "extract_play_summary"]
