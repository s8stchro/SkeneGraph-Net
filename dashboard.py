"""Self-contained HTML dashboard for one play.

The dashboard bundles results from all chosen segmentations into a single
HTML file that opens directly in any browser (no server needed).  The
segmentation tabs switch the view between `sd`, `large_seq`, `middle_seq`.

Layout
------
   ┌─────────────────────────────────────────────────────────┐
   │ Header (title, author, departures)                       │
   ├─────────────────────────────────────────────────────────┤
   │ KPI strip (incl. drama-change rate)                      │
   ├─────────────────────────────────────────────────────────┤
   │ Static network (force, full width, zoomable)             │
   ├──────────────────────────┬──────────────────────────────┤
   │ Size over segments       │ Beat chart (Trilcke/Fischer  │
   │                          │ 2017): segment-change rate   │
   ├─────────────────────────────────────────────────────────┤
   │ Dynamic network (segment slider, full width)             │
   ├──────────────────────────┬──────────────────────────────┤
   │ Character table          │ Segment table                │
   └─────────────────────────────────────────────────────────┘

D3 and KaTeX are inlined from `vendor/` (see vendor_assets.py) and all play
data is embedded as a JSON literal, so the file is fully self-contained and
opens offline.

The "drama-change rate" follows Fischer/Göbel/Kampkaspar/Kittel/Trilcke,
"Network Dynamics, Plot Analysis", DH2017.  At each transition between
two consecutive segments S_i and S_{i+1} we compute

    segment_change_rate(i) = |S_i Δ S_{i+1}| / |S_i ∪ S_{i+1}|

(the symmetric-difference / Jaccard distance of the two casts; this is the
add+delete-only Levenshtein distance the paper uses, normalised by union).
The drama-change rate is the mean of those segment-change rates.  Both are
recomputed in the browser when the user toggles mute characters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import networkx as nx

from aggregation import aggregatable_groups
from parser import PlayData
from segmentation import Segment
from figure_export import (CSS_PLACEHOLDER, JS_PLACEHOLDER,
                           figure_export_css, figure_export_js)
from methods_content import methods_panel_html
from vendor_assets import PLACEHOLDER as VENDOR_PLACEHOLDER, vendor_assets_html


def _edges_payload(G: nx.Graph) -> List[Dict]:
    out = []
    for u, v, d in G.edges(data=True):
        out.append({
            "source": u,
            "target": v,
            "weight": d.get("weight", 1),
            "segments_shared": d.get("segments_shared", d.get("weight", 1)),
            "segment_ids": d.get("segment_ids", []),
        })
    return out


def _segments_payload(segments: List[Segment]) -> List[Dict]:
    # First pass: each segment's *start* line in the TEI = min source_line
    # over its trigger moves and its speeches.
    starts: List[Optional[int]] = []
    for s in segments:
        lines: List[int] = []
        for m in s.trigger_moves:
            ln = m.stage_line or m.source_line   # start at the enclosing <stage>, not the <move>
            if ln:
                lines.append(ln)
        for sp in s.speeches:
            if sp.source_line:
                lines.append(sp.source_line)
        starts.append(min(lines) if lines else None)

    # Second pass: segment N's *end* line = the line before segment N+1
    # begins.  For the last segment, fall back to max(source_line) of its
    # contents.  Segments with no source lines (purely synthetic) get None.
    payloads: List[Dict] = []
    for i, s in enumerate(segments):
        start = starts[i]
        end: Optional[int] = None
        if start is not None:
            for j in range(i + 1, len(segments)):
                if starts[j] is not None:
                    end = starts[j] - 1
                    break
            if end is None:
                tail = [m.source_line for m in s.trigger_moves if m.source_line]
                tail += [sp.source_line for sp in s.speeches if sp.source_line]
                end = max(tail) if tail else start
        speakers = sorted(s.speakers)
        silent = sorted(s.silent_present)
        # Per-segment word counts attributed to each speaker (sum over the
        # segment's non-empty speeches, full count credited to every id in
        # @who).  words_by_speaker drives the dynamic-graph node-size
        # encoding (log-scaled) and the character x segment heatmap cell
        # intensity.  Empty placeholder <sp><l/></sp> speeches contribute
        # zero and are skipped.
        words_by_speaker: Dict[str, int] = {}
        for sp in s.speeches:
            if sp.word_count <= 0:
                continue
            for cid in sp.who:
                words_by_speaker[cid] = words_by_speaker.get(cid, 0) + sp.word_count
        payloads.append({
            "id": s.id,
            "label": s.label,
            "large_seq_id": s.large_seq_id,
            "large_seq_type": s.large_seq_type,
            "middle_seq_id": s.middle_seq_id,
            "is_initial": s.is_initial,
            "is_final": s.is_final,
            # `characters` = stage-present cast (used by mutes-in view).
            # `speakers` = the subset this segment attributes an utterance to
            # (`Segment.speakers`: the <sp>, not the word count, so a speech
            # whose text is lost still credits its speaker).  This is the cast
            # the segment-level model draws its edges and its plot-dynamics
            # indices from; the rest are shown as silent.
            "characters": sorted(s.characters_present),
            "speakers": speakers,
            "silent_present": silent,
            "words_by_speaker": words_by_speaker,
            "word_count": s.word_count,
            # Every <sp>, including one whose text is lost: such a speech
            # happened, and counting it is what lets a XOPOY interlude read
            # "1 speech, 0 words" instead of an empty segment.
            "num_speeches": len(s.speeches),
            # Zero-duration round trips (move type="crossing") inside the
            # segment: stage traffic deliberately absent from the graph.
            "num_crossings": s.num_crossings,
            "tei_start": start,
            "tei_end":   end,
        })
    return payloads


def _character_payload(play: PlayData, static_g: nx.Graph, metrics: Dict) -> List[Dict]:
    by_id = {n["id"]: n for n in metrics.get("nodes", [])}
    rows: List[Dict] = []
    for cid, ch in play.characters.items():
        m = by_id.get(cid)
        rows.append({
            "id": cid,
            "name": ch.display_name,
            "name_grc": ch.name_grc,
            "is_mute": ch.is_mute,
            "is_collective": ch.is_collective,
            "is_chorus": ch.is_chorus,
            "sex": ch.sex or "",
            # The collectives this character is a part of: the per-segment
            # cliques drawn in the browser skip a part and its whole, as
            # network._pairs does for every exported graph.
            "part_of": sorted(ch.part_of),
            "in_network": static_g.has_node(cid),
            "degree": (m["degree"] if m else 0),
            "weightedDegree": (m["weightedDegree"] if m else 0),
            "betweenness": (m["betweenness"] if m else 0.0),
            "closeness": (m["closeness"] if m else 0.0),
            "eigenvector": (m["eigenvector"] if m else 0.0),
            "clustering":  (m.get("clustering", 0.0) if m else 0.0),
            "triangles":   (m.get("triangles", 0) if m else 0),
            # Speech-time fields populated by compute_temporal_gini in
            # app.py; missing on pure mutes and on listPerson entries
            # who never speak.  Rendered in the per-character "speech
            # concentration" panel inside Plot Dynamics, not in the
            # centralities table.
            "total_words":        (m.get("total_words")        if m else None),
            "speaking_segments":  (m.get("speaking_segments")  if m else None),
            "n_onstage_segments": (m.get("n_onstage_segments") if m else None),
            "temporal_gini":      (m.get("temporal_gini")      if m else None),
        })
    rows.sort(key=lambda r: (-r["degree"], r["id"]))
    return rows


def build_dashboard_payload(
    play: PlayData,
    results: Dict[str, Dict],
) -> Dict:
    """Assemble the JSON blob the dashboard JS will consume."""
    payload = {
        "play": {
            "id": play.play_id,
            "title_grc": play.title_grc,
            "title_en": play.title_en,
            "author": play.author,
            # partOf relations declared in <listRelation>.  The dashboard
            # uses this to (a) decide whether to show the aggregator toggle
            # at all and (b) list the relations in the Methods tab.
            "relations": [
                {"name": r.name, "active": r.active, "passive": r.passive}
                for r in play.relations if r.name == "partOf"
            ],
            # The groups the writer generated variants for.  The checkboxes
            # are drawn from this rather than from the relations above, so a
            # box cannot name a combination that was never built -- which
            # the view would have had to resolve by showing some other one.
            "aggregate_groups": aggregatable_groups(play),
        },
        # Raw TEI source for the new "TEI source" view tab.  Larger than the
        # rest of the payload combined for Aristophanic plays (~300-500 KB
        # per play), but worth it for a self-contained dashboard.
        "tei_source": play.source_xml or "",
        "segmentations": {},
    }
    for mode, r in results.items():
        G = r["static_graph"]
        segments = r["segments"]
        metrics = r["metrics"]
        dyn_rows = r.get("dynamic_rows", [])
        entry = {
            "metrics": metrics,
            "edges": _edges_payload(G),
            "characters": _character_payload(play, G, metrics),
            "segments": _segments_payload(segments),
            "dynamic_rows": dyn_rows,
            "variants": {},
        }
        # One precomputed variant per non-empty subset of partOf groups.
        # The JS picks the variant whose key matches the currently-checked
        # group set; empty set falls back to the top-level (raw) fields.
        for key, v in (r.get("variants") or {}).items():
            entry["variants"][key] = {
                "metrics": v["metrics"],
                "edges": _edges_payload(v["static_graph"]),
                "characters": _character_payload(v["play"], v["static_graph"], v["metrics"]),
                "segments": _segments_payload(v["segments"]),
                "dynamic_rows": v["dynamic_rows"],
            }
        payload["segmentations"][mode] = entry
    return payload


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title} - SkeneGraph-Net</title>
<!--VENDOR_ASSETS-->
<style>
:root {{
  --bg: #fafafa; --panel: #ffffff; --border: #e0e0e0;
  --ink: #1a1a1a; --muted: #666; --accent: #1a5fb4;
  --speaker: #e07a5f; --mute: #aaa; --chorus: #4daf4a;
  --collective: #377eb8; --beat: #b73779;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px; line-height: 1.4; }}
/* Sticky topbar wraps the page header AND the view-tabs nav so that the
   play title, departures line, and the Analysis / TEI / Methods tabs stay
   pinned to the top while the body scrolls.  Solid background prevents
   the underlying content from bleeding through. */
.topbar {{ position: sticky; top: 0; z-index: 100;
  background: var(--panel); }}
header {{ background: var(--panel); border-bottom: 1px solid var(--border);
  padding: 16px 24px; }}
header h1 {{ margin: 0 0 4px 0; font-size: 24px; }}
header .sub {{ color: var(--muted); font-size: 13px; }}
header .departures {{ margin-top: 6px; font-size: 12px; color: var(--muted); }}
header .departures b {{ color: var(--accent); }}
main {{ padding: 12px 16px; }}
/* Top-level view tabs (Analysis | Methods).  Distinct from `.tabs`
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
/* General-purpose hider used by the partOf-aggregate toggle (only shown
   when the play actually has partOf relations) and any future chip. */
.toggles label.hidden {{ display: none; }}
/* Status chips below the departures line; visible only when something
   non-default is on (currently: partOf aggregation).  Keeping the strip
   in the header means the chip is captured by any screenshot. */
.active-filters {{ margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap;
  font-size: 11px; min-height: 0; }}
.active-filters .filter-chip {{ display: inline-flex; align-items: baseline;
  gap: 4px; padding: 1px 8px; border-radius: 10px; background: #f0e8d4;
  color: #6b5d2e; border: 1px solid #d6c87a; font-weight: 500; }}
.active-filters .filter-chip i {{ font-style: italic; }}
.active-filters .filter-chip .detail {{ color: #9b8b46; font-weight: 400;
  font-size: 10.5px; }}
.methods-content {{ padding: 8px 8px 24px 8px; max-width: 980px;
  font-size: 14px; line-height: 1.55; }}
.methods-content .methods-intro {{ background: var(--panel);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 12px 16px; margin-bottom: 24px; color: var(--ink); }}
.methods-section {{ margin-bottom: 28px; }}
.methods-section h3 {{ margin: 0 0 12px 0; font-size: 16px;
  color: var(--accent); padding-bottom: 4px;
  border-bottom: 2px solid var(--accent); }}
.metric {{ margin: 0 0 18px 0; padding: 0; }}
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
/* ---------- TEI source view ---------- */
.view-tei .panel {{ padding: 10px 8px 12px 8px; }}
.tei-toolbar {{ display: flex; align-items: center; gap: 14px;
  padding: 0 4px 8px 4px; font-size: 13px; color: var(--muted); }}
.tei-toolbar label {{ display: inline-flex; align-items: center; gap: 6px; }}
.tei-toolbar select {{ font-size: 13px; padding: 4px 8px;
  border: 1px solid var(--border); border-radius: 3px; background: white;
  font-family: inherit; max-width: 360px; }}
.tei-toolbar .seg-range {{ font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11.5px; color: #777; }}
.tei-source-wrap {{ height: 78vh; overflow: auto; background: #fafafa;
  border: 1px solid var(--border); border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px; line-height: 1.45; }}
.tei-source {{ display: block; min-width: 100%; }}
.tei-line {{ display: flex; align-items: flex-start; }}
.tei-line .ln {{ display: inline-block; width: 56px; min-width: 56px;
  padding: 0 8px; text-align: right; color: #b8b8b8; user-select: none;
  border-right: 1px solid #e6e6e6; background: #f3f3f3; }}
.tei-line .content {{ padding: 0 8px; white-space: pre; flex: 1;
  color: var(--ink); }}
/* Markup is demoted to grey; the actual text (everything outside `<...>`)
   keeps the default ink colour, so a reader unfamiliar with TEI/XML can
   skim the play text and treat the tags as scaffolding. */
.tei-line .content .xml-tag {{ color: #a0a0a0; }}
.tei-line .content .xml-comment {{ color: #8aa884; font-style: italic; }}
/* <move> elements drive the stage-direction segmentation, so they get
   a distinct colour to stand out against the demoted grey markup. */
.tei-line .content .xml-move {{ color: #2d8c4a; font-weight: 600; }}
.tei-line.highlight {{ background: #fff4c8; }}
.tei-line.highlight .ln {{ background: #ffe699; color: #6a5a00; }}
.tei-line.highlight.first .content {{ border-left: 3px solid #d4a200;
  padding-left: 5px; }}
.tei-source-empty {{ padding: 16px; color: var(--muted); font-style: italic; }}
/* The segmentation tabs row (Stage directions / large-seq / middle-seq) and the
   toggles pin just below the topbar.  `--topbar-h` is measured in JS on
   load and on resize.  Only takes effect inside the Analysis view; when
   that view is `.hidden`, the element doesn't render so sticky is moot. */
.tabs {{ display: flex; gap: 4px; margin: 0; padding: 8px 0 12px 0;
  align-items: center;
  position: sticky; top: var(--topbar-h, 0px); z-index: 90;
  background: var(--bg); }}
.tabs button.tab {{ padding: 8px 16px; border: 1px solid var(--border);
  background: var(--panel); cursor: pointer; font-size: 13px;
  border-radius: 4px; }}
.tabs button.tab.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
.tabs button.tab:hover:not(.active) {{ background: #f0f0f0; }}
.toggles {{ margin-left: auto; display: flex; gap: 12px; align-items: center;
  font-size: 12px; color: var(--muted); flex-wrap: wrap; }}
/* Network-model radio fieldset.  Compact, in-line with the other
   toggles.  The fieldset border is the only place we use a fieldset
   on the page; styled to look like an unobtrusive grouped control. */
.mute-mode-radio {{ border: 1px solid var(--border); border-radius: 4px;
  padding: 2px 8px 4px 8px; margin: 0; display: inline-flex; gap: 10px;
  align-items: baseline; flex-wrap: wrap; }}
.mute-mode-radio legend {{ font-size: 11px; color: var(--muted);
  padding: 0 4px; font-weight: 500; }}
.mute-mode-radio label {{ display: inline-flex; align-items: baseline;
  gap: 3px; cursor: pointer; }}
.mute-mode-radio label input {{ margin: 0 2px 0 0; }}
.mute-mode-radio .detail {{ color: #999; font-size: 11px;
  font-style: italic; }}
/* Horizontal columns: each metric section is its own column inside #kpis. */
#kpis {{ display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 8px 28px; align-items: start; }}
.metric-section {{ margin: 0; min-width: 0; }}
.metric-section h4 {{ margin: 0 0 6px 0; padding: 0 2px 4px 2px;
  font-size: 11px; font-weight: 600; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.08em;
  border-bottom: 1px solid var(--border); }}
/* The caveat (the "— spk = …" / "— respects the mute toggle" hint that
   sits next to the section name) is forced onto its own line below the
   uppercase title so narrow columns don't truncate it. */
.metric-section h4 .caveat {{ display: block; font-weight: 400;
  text-transform: none; letter-spacing: 0; font-style: italic;
  color: #aaa; font-size: 10.5px; margin: 2px 0 0 0; }}
/* Diameter, path length, clustering and component count were once greyed
   here as a demoted sub-group.  They are exact values on the graph shown,
   not estimates, and greying reads as a warning about their truth rather
   than about their resolution -- which also invited the reader to discount
   the metrics beside them.  What is worth saying about them is said in the
   section footnote and in Methods 1, not in the colour. */
.metric-section .section-footnote {{ font-size: 11px; font-style: italic;
  color: #aaa; margin: 10px 0 0 0; padding: 6px 4px 0 4px;
  border-top: 1px dotted #e0e0e0; }}
/* Within a section, metrics stack vertically (one per row). */
.metrics-list {{ display: flex; flex-direction: column;
  margin: 0; padding: 0; list-style: none;
  font-size: 14px; }}
.metrics-list .item {{ display: flex; justify-content: space-between;
  align-items: baseline; padding: 5px 4px; gap: 8px;
  border-bottom: 1px dotted #e0e0e0; }}
.metrics-list dt {{ color: var(--muted); font-weight: 400; margin: 0;
  flex: 1 1 auto; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.metrics-list dd {{ margin: 0; font-weight: 600; flex: 0 0 auto;
  font-variant-numeric: tabular-nums; color: var(--ink);
  text-align: right; white-space: nowrap; }}
.metrics-list dd .alt {{ display: block; font-size: 11px; font-weight: 400;
  color: #999; margin-top: -1px; }}
.metrics-list .item.beat {{ background: #fbf3f7; }}
.metrics-list .item.beat dt,
.metrics-list .item.beat dd {{ color: var(--beat); }}
.row.split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  margin-bottom: 16px; }}
.row.charts {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px;
  margin-bottom: 16px; }}
@media (max-width: 1100px) {{
  .row.charts {{ grid-template-columns: 1fr; }}
}}
.panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
  padding: 12px; margin-bottom: 12px; }}
.panel.graph {{ padding: 8px 6px; }}
.panel.graph > h3 {{ padding: 0 6px; }}
.panel.graph > .legend, .panel.graph > .force-controls {{ padding: 0 6px; }}
.panel h3 {{ margin: 0 0 8px 0; font-size: 14px; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.05em;
  display: flex; justify-content: space-between; align-items: baseline; }}
.panel h3 .hint {{ font-size: 11px; text-transform: none; letter-spacing: 0;
  color: #999; font-weight: normal; }}
#static-graph {{ width: 100%; height: 800px; cursor: grab; }}
#static-graph:active {{ cursor: grabbing; }}
/* Dynamic graph: narrower than the static panel (per-segment graphs have
   far fewer nodes and don't need the full width).  The word-proportional
   timeline below it spans the same max-width so the two align visually. */
#dynamic-graph {{ width: 100%; max-width: 820px; height: 460px;
  display: block; margin: 0 auto; }}
#segment-timeline {{ width: 100%; max-width: 820px; height: 32px;
  display: block; margin: 0 auto 6px auto; }}
#segment-timeline rect {{ cursor: pointer; }}
#segment-timeline rect.current {{ stroke: var(--accent); stroke-width: 2; }}
#segment-timeline rect.empty-marker {{ fill: #f0f0f0; }}
#segment-timeline rect:hover {{ stroke: #888; stroke-width: 1; }}

/* Fullscreen mode for the graph panels: a fixed overlay covering the
   viewport.  The graph expands to fill the available space; the rest
   of the dashboard remains in the underlying page and becomes visible
   again on exit.  Toggled via the "fullscreen" button in each panel
   header (or the Escape key). */
.panel.graph.dyn-fullscreen,
.panel.graph.static-fullscreen,
.panel.graph.heatmap-fullscreen {{ position: fixed; inset: 0; z-index: 1000;
  margin: 0; padding: 16px 24px; background: var(--panel);
  overflow: auto; max-width: none; }}
.panel.graph.dyn-fullscreen #dynamic-graph {{ max-width: none;
  width: 100%; height: calc(100vh - 230px); }}
.panel.graph.dyn-fullscreen #segment-timeline {{ max-width: none;
  width: 100%; height: 48px; }}
.panel.graph.static-fullscreen #static-graph {{ width: 100%;
  height: calc(100vh - 140px); }}
.panel.graph.heatmap-fullscreen #character-segment-heatmap {{
  width: 100%; height: calc(100vh - 300px); }}
.panel.size-fullscreen,
.panel.word-fullscreen,
.panel.beat-fullscreen {{ position: fixed; inset: 0; z-index: 1000;
  margin: 0; padding: 16px 24px; background: var(--panel);
  overflow: auto; max-width: none; }}
.panel.size-fullscreen #size-chart,
.panel.word-fullscreen #word-chart {{ height: calc(100vh - 120px); }}
.panel.beat-fullscreen #beat-chart {{ height: calc(100vh - 150px); }}
/* In fullscreen, the cell-composition summary needs to remain visible
   under the heatmap (the heatmap itself shrinks to leave room).  Also
   bump the font slightly so the percentages read on a projector. */
.panel.graph.heatmap-fullscreen .heatmap-stats {{
  font-size: 14px; padding: 14px 18px; margin-top: 16px; }}
.panel.graph.heatmap-fullscreen .heatmap-stats .group-title {{ font-size: 12px; }}
.fullscreen-toggle {{ float: right; font-size: 11px; padding: 2px 10px;
  border: 1px solid var(--border); background: white; cursor: pointer;
  border-radius: 3px; margin-left: 8px; }}
.fullscreen-toggle:hover {{ background: #f0f0f0; }}

/* Character x segment heatmap.  Each cell is one (character, segment)
   pair: transparent = absent, light grey = present but silent in
   segment, red hatch = speaks but the text is not transmitted,
   pale-to-dark red ramp = speaking (intensity rising with words).
   Click a cell to scrub the dynamic graph to that segment. */
#character-segment-heatmap {{ width: 100%; height: 480px; display: block; }}
#character-segment-heatmap rect.cell {{ cursor: pointer; }}
#character-segment-heatmap rect.cell:hover {{ stroke: var(--accent);
  stroke-width: 1.5; }}
#character-segment-heatmap rect.cell.current-segment-strip {{ stroke: var(--accent);
  stroke-width: 1; stroke-opacity: 0.35; }}
#character-segment-heatmap .row-label {{ font-size: 10px; fill: var(--ink);
  cursor: default; transition: fill 0.08s, font-weight 0.08s; }}
/* Row-label hover highlight: applied via JS when the pointer is over
   any cell in the row.  `.highlight` = the hovered character (accent +
   bold); `.same-col` = other characters present in the same column
   (muted bold), so the column reads as "stage-mates of the hovered
   character at this segment". */
#character-segment-heatmap .row-label.highlight {{ fill: var(--accent);
  font-weight: 700; }}
#character-segment-heatmap .row-label.same-col {{ fill: var(--ink);
  font-weight: 700; }}
/* Faint column stripe behind the cells of the hovered segment. */
#character-segment-heatmap rect.col-stripe {{ fill: var(--accent);
  fill-opacity: 0.06; pointer-events: none; }}
#character-segment-heatmap .axis-label {{ font-size: 10px; fill: var(--muted); }}
/* Cell-composition summary panel beneath the heatmap.  Two grouped blocks
   in a flex row: cell counts (with red / grey / empty + gray:red ratio)
   and the would-be edge counts under both readings (on-stage cast and
   speaking cast).  Updates on every heatmap re-render so it follows the
   mute-mode radio and the partOf aggregation toggle. */
.heatmap-stats {{ margin: 8px 0 0; padding: 10px 14px;
  background: #f7f7f5; border: 1px solid var(--border);
  border-radius: 3px; font-size: 12px; color: var(--ink);
  display: flex; gap: 32px; flex-wrap: wrap;
  font-variant-numeric: tabular-nums; }}
.heatmap-stats .group {{ display: flex; flex-direction: column; gap: 2px;
  min-width: 200px; }}
.heatmap-stats .group-title {{ color: var(--muted); font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 4px; font-weight: 500; }}
.heatmap-stats .row {{ display: flex; justify-content: space-between;
  gap: 12px; }}
.heatmap-stats .row .key {{ color: var(--muted); }}
.heatmap-stats .row .key .swatch {{ display: inline-block; width: 10px;
  height: 10px; border-radius: 2px; vertical-align: middle;
  margin-right: 6px; border: 1px solid var(--border); }}
.heatmap-stats .row .val {{ font-weight: 500; }}
.heatmap-stats .row.summary {{ border-top: 1px dashed var(--border);
  padding-top: 3px; margin-top: 2px; }}
.heatmap-controls {{ display: flex; gap: 16px; align-items: center;
  padding: 0 6px 8px 6px; font-size: 12px; color: var(--muted); }}
.heatmap-controls select {{ font-size: 12px; padding: 2px 6px;
  border: 1px solid var(--border); border-radius: 3px; background: white;
  font-family: inherit; margin-left: 6px; }}
#size-chart, #word-chart, #beat-chart {{ width: 100%; height: 240px; }}
#beat-chart circle.beat-hit:hover {{ fill: rgba(183, 55, 121, 0.12); }}
.controls {{ display: flex; gap: 8px; align-items: center; padding: 8px 12px;
  background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
  margin-bottom: 12px; flex-wrap: wrap; }}
.controls input[type=range] {{ flex: 1; min-width: 120px; }}
.controls button {{ padding: 4px 12px; border: 1px solid var(--border);
  background: white; cursor: pointer; border-radius: 3px; }}
.controls .seg-info {{ font-size: 12px; color: var(--muted); min-width: 320px;
  font-family: ui-monospace, SFMono-Regular, monospace; }}
.controls .speed-group {{ display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--muted); min-width: 220px; }}
.controls .speed-group input[type=range] {{ flex: 0 1 120px; min-width: 90px; }}
.force-controls {{ display: flex; gap: 14px; align-items: center; flex-wrap: wrap;
  margin: 6px 0 8px 0; padding: 6px 8px; border: 1px solid var(--border);
  border-radius: 3px; background: #fafafa; font-size: 11px; color: var(--muted); }}
.force-controls .grp {{ display: flex; align-items: center; gap: 6px; }}
.force-controls input[type=range] {{ width: 130px; }}
.force-controls .val {{ font-variant-numeric: tabular-nums; min-width: 36px;
  text-align: right; color: var(--ink); }}
.force-controls button {{ padding: 2px 10px; font-size: 11px; border: 1px solid var(--border);
  background: white; border-radius: 3px; cursor: pointer; }}
table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }}
th, td {{ padding: 4px 8px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
/* `position: sticky` keeps the header pinned to the top of the .scroll
   container while the body scrolls.  Needs `border-collapse: separate`
   (above) and a solid background, otherwise rows bleed through. */
th {{ background: #f8f8f8; font-weight: 600; cursor: pointer; user-select: none;
  position: sticky; top: 0; z-index: 1;
  box-shadow: inset 0 -1px 0 var(--border); }}
th:hover {{ background: #f0f0f0; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tr:hover td {{ background: #fffce8; }}
/* Segments-table cast column: under mutes-out, present-but-silent
   characters appear in italic grey under the primary speakers list. */
.silent-present {{ font-size: 11px; color: #999; font-style: italic;
  margin-top: 2px; }}
.chip {{ display: inline-block; padding: 1px 6px; border-radius: 8px;
  font-size: 10px; background: #eee; color: #555; margin-right: 2px; }}
.chip.mute {{ background: #f0f0f0; color: #888; }}
.chip.chorus {{ background: #e2f0db; color: #2d6a1e; }}
.chip.collective {{ background: #dbe7f3; color: #1a4a7a; }}
.scroll {{ max-height: 360px; overflow-y: auto; }}
text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
.node circle {{ stroke: white; stroke-width: 1.5; cursor: pointer; }}
.node.absent circle {{ opacity: 0.08; }}
.node.absent text {{ opacity: 0.10; }}
/* Labels are clickable too (cursor:pointer instead of pointer-events:none)
   so that clicking on a character's name selects the node, not the empty
   space behind it.  This is required for the node-focus feature. */
.node text {{ font-size: 11px; cursor: pointer; user-select: none; }}
.link {{ stroke: #aaa; stroke-opacity: 0.4; }}
.legend {{ font-size: 11px; color: var(--muted); margin-top: 8px;
  display: flex; gap: 12px; flex-wrap: wrap; }}
.legend span.swatch {{ display: inline-block; width: 10px; height: 10px;
  border-radius: 50%; vertical-align: middle; margin-right: 3px; }}
/* The heatmap's key: square swatches painted as its cells are -- grey for a
   silent presence, the cells' own hatch where the text is not transmitted,
   the cells' own ramp for words. */
.legend span.swatch-silent {{ border-radius: 2px; background: #bbbbbb; }}
.legend span.swatch-hatch {{ border-radius: 2px;
  background: repeating-linear-gradient(45deg, #a50f15 0 1.5px,
                                        #fde0dd 1.5px 4px); }}
.legend span.swatch-ramp {{ border-radius: 2px; width: 50px;
  background: linear-gradient(to right, #fcbba1, #a50f15); }}
.zoom-hint {{ font-size: 11px; color: #999; }}
</style>
<!--FIGURE_EXPORT_CSS-->
</head>
<body>
<div class="topbar">
<header>
  <h1>{title}</h1>
  <div class="sub">{subtitle}</div>
  <div class="departures">Model: <b>three segmentations</b>
     (sd / large-seq / middle-seq) &middot; <b>per-segment speaking cast</b> alongside the
     stage-presence cast (toggleable) &middot; <b>dynamic graph</b> alongside static</div>
  <div class="active-filters" id="active-filters"></div>
</header>
<nav class="view-tabs">
  <button class="view-tab active" data-view="analysis">Analysis</button>
  <button class="view-tab" data-view="tei">TEI source</button>
  <button class="view-tab" data-view="methods">Methods &amp; formulas</button>
</nav>
</div>
<main class="view view-analysis" data-view="analysis">
  <div class="tabs" id="seg-tabs">
    <div class="toggles">
      <fieldset class="mute-mode-radio">
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
      <label><input type="checkbox" id="show-labels" checked> show labels</label>
      <span id="aggregate-toggles"></span>
    </div>
  </div>

  <div class="panel" data-comparison-export>
    <h3>Network metrics</h3>
    <div id="kpis"></div>
  </div>

  <div class="panel">
    <h3>Speech concentration per character
      <span class="hint">plot-dynamics companion to the play-level Gini &middot;
        steady vs burst speech distribution &middot;
        threshold &ge; 40 words; click a row to scrub to that character's loudest segment</span>
    </h3>
    <div class="scroll" style="max-height: 360px;">
      <table id="tgini-table"></table>
    </div>
  </div>

  <div class="panel graph" id="static-panel">
    <h3>Static co-presence network
      <button class="fullscreen-toggle" id="static-fullscreen-btn"
              title="Toggle fullscreen (Esc to exit)">&#x26F6; fullscreen</button>
      <span class="hint">click a node to highlight its neighbourhood &middot; drag to move &middot; scroll to zoom &middot; double-click to reset</span>
    </h3>
    <div class="force-controls">
      <div class="grp">
        <label for="f-repulsion">repulsion</label>
        <input type="range" id="f-repulsion" min="50" max="2000" step="10" value="340">
        <span class="val" id="f-repulsion-v">340</span>
      </div>
      <div class="grp">
        <label for="f-link">edge length</label>
        <input type="range" id="f-link" min="20" max="300" step="5" value="90">
        <span class="val" id="f-link-v">90</span>
      </div>
      <div class="grp">
        <label for="f-gravity">gravity</label>
        <input type="range" id="f-gravity" min="0" max="0.30" step="0.005" value="0.05">
        <span class="val" id="f-gravity-v">0.05</span>
      </div>
      <button id="f-reset" type="button">reset</button>
      <button id="f-fit"   type="button">fit</button>
      <span style="margin-left:auto">live update &middot; click <b>fit</b> to re-frame</span>
    </div>
    <svg id="static-graph"></svg>
    <div class="legend">
      <span><span class="swatch" style="background: var(--speaker)"></span>individual</span>
      <span><span class="swatch" style="background: var(--mute)"></span>mute</span>
      <span><span class="swatch" style="background: var(--chorus)"></span>chorus</span>
      <span><span class="swatch" style="background: var(--collective)"></span>collective</span>
      <span style="margin-left: auto">node area &prop; degree &middot; edge width &prop; weight</span>
    </div>
  </div>

  <div class="row charts">
    <div class="panel" id="size-panel" style="margin-bottom: 0;">
      <h3>Order over segments
        <button class="fullscreen-toggle" id="size-fullscreen-btn"
                title="Toggle fullscreen (Esc to exit)">&#x26F6; fullscreen</button>
        <span class="hint">characters present per segment</span>
      </h3>
      <svg id="size-chart"></svg>
    </div>
    <div class="panel" id="word-panel" style="margin-bottom: 0;">
      <h3>Words over segments
        <button class="fullscreen-toggle" id="word-fullscreen-btn"
                title="Toggle fullscreen (Esc to exit)">&#x26F6; fullscreen</button>
        <span class="hint">words spoken per segment</span>
      </h3>
      <svg id="word-chart"></svg>
    </div>
    <div class="panel" id="beat-panel" style="margin-bottom: 0;">
      <h3>Beat chart (drama-change rate)
        <button class="fullscreen-toggle" id="beat-fullscreen-btn"
                title="Toggle fullscreen (Esc to exit)">&#x26F6; fullscreen</button>
        <span class="hint">Fischer et al. 2017 &middot; |S_i &Delta; S_{{i+1}}| / |S_i &cup; S_{{i+1}}|</span>
      </h3>
      <label style="font-size:11px; color:var(--muted); display:flex; align-items:center; gap:6px; cursor:pointer; margin: -2px 0 4px;">
        <input type="checkbox" id="chart-xmode"> space x-axis by word position
        <span style="opacity:0.8;">(transitions placed at their stage-time, not evenly)</span>
      </label>
      <svg id="beat-chart"></svg>
    </div>
  </div>

  <div class="panel graph" id="dynamic-panel">
    <h3>Dynamic network (per segment)
      <button class="fullscreen-toggle" id="dyn-fullscreen-btn"
              title="Toggle fullscreen (Esc to exit)">&#x26F6; fullscreen</button>
      <span class="hint">click a segment on the timeline, a beat-chart node, or a table row; use &lt; / &gt; / play</span>
    </h3>
    <!-- Controls live inside the dynamic panel so they go fullscreen
         along with it.  The hidden seg-slider keeps the existing
         updateSlider() wiring functional; the visible scrubber is the
         word-proportional #segment-timeline. -->
    <div class="controls">
      <button id="seg-prev">&lt;</button>
      <button id="seg-play">play</button>
      <button id="seg-next">&gt;</button>
      <input type="range" id="seg-slider" min="1" max="1" value="1" style="display:none;">
      <div class="speed-group">
        <label for="play-speed">pace</label>
        <input type="range" id="play-speed" min="300" max="4000" step="100" value="1500">
        <span class="val" id="play-speed-v">1.5s</span>
      </div>
      <div class="seg-info" id="seg-info">static (all segments)</div>
    </div>
    <svg id="segment-timeline"></svg>
    <svg id="dynamic-graph"></svg>
  </div>

  <div class="panel graph" id="heatmap-panel">
    <h3>Character &times; segment heatmap
      <button class="fullscreen-toggle" id="heatmap-fullscreen-btn"
              title="Toggle fullscreen (Esc to exit)">&#x26F6; fullscreen</button>
      <span class="hint">click a cell to jump to its segment</span>
    </h3>
    <div class="heatmap-controls">
      <label>row order
        <select id="heatmap-sort">
          <option value="loudest" selected>loudest first (default)</option>
          <option value="appearance">appearance order</option>
          <option value="mobility">most stage entrances/exits</option>
          <option value="alphabetical">alphabetical</option>
        </select>
      </label>
    </div>
    <svg id="character-segment-heatmap"></svg>
    <!-- The cells' four states as a key, so the chart carries its own
         reading and an exported figure carries it too; it was prose in the
         heading, which no figure takes with it. -->
    <div class="legend">
      <span><span class="swatch swatch-silent" data-swatch="solid"></span>present, silent</span>
      <span><span class="swatch swatch-hatch" data-swatch="hatch"
                  data-colors="#a50f15 #fde0dd"></span>performs, text not transmitted</span>
      <span><span class="swatch swatch-ramp" data-swatch="ramp"
                  data-colors="#fcbba1 #a50f15"></span>speaking (words, &radic; scale)</span>
    </div>
    <div id="heatmap-stats" class="heatmap-stats"></div>
  </div>

  <div class="row split">
    <div class="panel" style="margin-bottom: 0;">
      <h3>Characters</h3>
      <div class="scroll"><table id="char-table"></table></div>
    </div>
    <div class="panel" style="margin-bottom: 0;">
      <h3>Segments</h3>
      <div class="scroll"><table id="seg-table"></table></div>
    </div>
  </div>
</main>

<main class="view view-tei hidden" data-view="tei">
  <div class="panel">
    <h3>TEI source
      <span class="hint">raw XML of the play with line numbers &middot;
        pick a segment to jump to and highlight its lines</span>
    </h3>
    <div class="tei-toolbar">
      <label>jump to:
        <select id="tei-segment-select">
          <option value="-1">&mdash; whole play &mdash;</option>
        </select>
      </label>
      <span class="seg-range" id="tei-range-info"></span>
    </div>
    <div class="tei-source-wrap" id="tei-source-wrap">
      <div id="tei-content" class="tei-source"></div>
    </div>
  </div>
</main>

<main class="view view-methods hidden" data-view="methods">
  <!--METHODS_HTML-->
</main>

<script>
const DATA = {data_json};

const FORCE_DEFAULTS = {{ repulsion: 340, link: 90, gravity: 0.05 }};

// Canonical tab order; defaults to "sd" when present.  JSON keys are
// alphabetised (sort_keys=True for byte-stable output) so we cannot rely on
// insertion order from Object.keys().
const MODE_ORDER = ["sd", "large-seq", "middle-seq"];
const AVAILABLE_MODES = MODE_ORDER.filter(m => m in DATA.segmentations)
  .concat(Object.keys(DATA.segmentations).filter(m => MODE_ORDER.indexOf(m) === -1));

const STATE = {{
  seg: AVAILABLE_MODES[0] || "sd",
  segmentIdx: -1,    // -1 means "static aggregate"
  // Three-state network model.  Replaces the older binary showMutes.
  // Mapping to the underlying (include_mutes, segment_cast) axes:
  //   "full"       -> (True,  stage) -- all on-stage characters as nodes,
  //                  per-segment co-presence edges (default)
  //   "p-speaking" -> (False, stage) -- drop play-level mute characters
  //                  from the node set, edges still per-segment co-presence
  //   "s-speaking" -> (False, speaking) -- speakers-only cast; a character
  //                  counts as in a segment only by speaking in it
  // The first axis answers "who counts as a node?" (play level), the
  // second answers "what makes an edge?" (segment level).  See methods §0.
  muteMode: "full",
  showLabels: true,
  // X-axis mode for the beat chart.
  //   "segment" -> equal-width segment index (default)
  //   "word"   -> transitions placed at their cumulative word position
  //                (stage-time), so doorway flurries collapse and turnover
  //                between long scenes stands alone.
  chartXMode: "segment",
  // Set of group ids (the `passive` side of partOf relations) currently
  // being aggregated.  Empty = raw view.  One entry per checked group.
  aggregateGroups: new Set(),
  playing: false,
  playTimer: null,
  playSpeed: 1500,
  forceSim: null,
  forceParams: Object.assign({{}}, FORCE_DEFAULTS),
  positions: null,
  zoomTransform: d3.zoomIdentity,
  staticZoom: null,
  pendingAutoFit: false,  // ONLY the manual "fit" button sets this.
  focusNode: null,        // id of the character whose ego-network is highlighted
}};

// The groups this dashboard actually carries variants for, as the writer
// enumerated them.  One checkbox per entry in the toolbar; an empty list
// means no aggregation control at all.  Derived from the payload rather
// than from the relations, so every box has a block behind it.
const AGGREGATE_GROUPS = ((DATA.play && DATA.play.aggregate_groups) || []).slice();

// Click-to-focus on a static-graph node: dim everything except that node,
// its direct neighbours, and the edges connecting them.  The focus state
// lives on STATE.focusNode and persists across force-slider / fit
// interactions; it is cleared by render() on tab / mute toggle and by
// clicking the SVG background.
function applyStaticFocus() {{
  const root = d3.select("#static-graph g.zoom-root");
  if (root.empty()) return;
  const focusId = STATE.focusNode;
  if (!focusId) {{
    root.selectAll(".node").style("opacity", null);
    root.selectAll(".node circle")
      .style("stroke", null).style("stroke-width", null);
    root.selectAll(".link")
      .style("opacity", null).style("stroke", null).style("stroke-opacity", null);
    return;
  }}
  const neighbors = new Set([focusId]);
  root.selectAll(".link").each(function(d) {{
    const s = (d.source && d.source.id) || d.source;
    const t = (d.target && d.target.id) || d.target;
    if (s === focusId) neighbors.add(t);
    else if (t === focusId) neighbors.add(s);
  }});
  root.selectAll(".node")
    .style("opacity", d => neighbors.has(d.id) ? 1 : 0.12);
  root.selectAll(".node").filter(d => d.id === focusId).select("circle")
    .style("stroke", "var(--accent)")
    .style("stroke-width", 3);
  root.selectAll(".link")
    .style("opacity", function(d) {{
      const s = (d.source && d.source.id) || d.source;
      const t = (d.target && d.target.id) || d.target;
      return (s === focusId || t === focusId) ? 0.9 : 0.05;
    }})
    .style("stroke", function(d) {{
      const s = (d.source && d.source.id) || d.source;
      const t = (d.target && d.target.id) || d.target;
      return (s === focusId || t === focusId) ? "var(--accent)" : null;
    }})
    .style("stroke-opacity", function(d) {{
      const s = (d.source && d.source.id) || d.source;
      const t = (d.target && d.target.id) || d.target;
      return (s === focusId || t === focusId) ? 0.85 : null;
    }});
}}

function autoFitZoom(animate=true) {{
  if (!STATE.forceSim || !STATE.staticZoom) return;
  const svg = d3.select("#static-graph");
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  const nodes = STATE.forceSim.nodes();
  if (!nodes.length) return;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const n of nodes) {{
    if (n.x < x0) x0 = n.x;
    if (n.x > x1) x1 = n.x;
    if (n.y < y0) y0 = n.y;
    if (n.y > y1) y1 = n.y;
  }}
  const PAD = 50;
  const bw = Math.max(1, x1 - x0), bh = Math.max(1, y1 - y0);
  const scale = Math.min((w - 2 * PAD) / bw, (h - 2 * PAD) / bh, 4);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const t = d3.zoomIdentity
    .translate(w / 2 - cx * scale, h / 2 - cy * scale)
    .scale(scale);
  const target = animate ? svg.transition().duration(450) : svg;
  target.call(STATE.staticZoom.transform, t);
}}

// -------------------------------------------------------------------- helpers
function fmt(v, dp=4) {{
  if (v == null) return "";
  if (typeof v !== "number") return v;
  if (Number.isInteger(v)) return v.toLocaleString();
  return v.toFixed(dp);
}}
// Node fill, same categories as the role chips and in the same precedence:
// muteness first, so a silent crowd reads grey rather than blue, then the
// collectivity of the rest.  `--speaker` is the palette's name for the
// fourth colour, which the legend calls "individual"; the variable is also
// used for unrelated chart series, hence the mismatch.
function nodeColor(c) {{
  if (c.is_mute) return "var(--mute)";
  if (c.is_chorus) return "var(--chorus)";
  if (c.is_collective) return "var(--collective)";
  return "var(--speaker)";
}}
// Labels and details for the three mute modes -- single source of truth
// for the active-filters chip strip, segment-table headers, and any
// hint text that needs to mention the current network model.
const MUTE_MODE_LABELS = {{
  "full":       {{ label: "stage co-presence",
                   detail: "all on-stage characters as nodes" }},
  "p-speaking": {{ label: "speaking cast on play level",
                   detail: "drop play-level mutes" }},
  "s-speaking": {{ label: "speaking cast on segment level",
                   detail: "only segment-active speakers" }},
}};

// Provenance for the figure exporter: the caption stamped into every
// exported SVG/PNG, and the slug that names the file.  The point is that one
// panel shows different numbers under different spines and models, and an
// image carries none of that on its own; a figure in an article should say
// what it is a figure of.  See figure_export.py.
const SEG_LABELS_LONG = {{
  "sd": "stage-direction segmentation",
  "large-seq": "large-sequence segmentation",
  "middle-seq": "middle-sequence segmentation",
}};
function figureProvenance(panel) {{
  const play = DATA.play || {{}};
  const name = play.title_en || play.title_grc || document.title;
  const ml = MUTE_MODE_LABELS[STATE.muteMode] || MUTE_MODE_LABELS.full;
  const groups = Array.from(STATE.aggregateGroups).sort();
  const metrics = (currentSegData() || {{}}).metrics || {{}};
  const bits = [name, SEG_LABELS_LONG[STATE.seg] || STATE.seg, ml.label];
  if (AGGREGATE_GROUPS.length) {{
    bits.push(groups.length ? "aggregated: " + groups.join(", ")
                            : "not aggregated");
  }}
  if (metrics.edge_weight) bits.push("edges weighted by " + metrics.edge_weight);
  // The dynamic graph shows one segment at a time; a figure of it is
  // meaningless without saying which.
  if (panel && panel.querySelector("#dynamic-graph") && STATE.segmentIdx >= 0) {{
    const segs = (currentSegData() || {{}}).segments || [];
    const seg = segs.find(s => s.id === STATE.segmentIdx);
    if (seg) bits.push("segment " + (seg.label || seg.id));
  }}
  return {{
    caption: bits.join(" \\u00b7 "),
    slug: [name, STATE.seg, STATE.muteMode,
           groups.length ? "agg" : ""].filter(Boolean).join("-"),
  }};
}}
// Every segmentation x network model x aggregation state this play was
// computed under, as one table.  Comparing configurations otherwise means
// switching the controls, reading, switching back and remembering; the
// numbers are all in the payload already.  Consumed by figure_export.py.
function figureComparisonRows() {{
  const play = DATA.play || {{}};
  const name = play.title_en || play.title_grc || document.title;
  // `id` first, as in the corpus export, so the two files join on it.
  const header = ["id", "play", "segmentation", "model", "aggregated", "order",
    "edges", "density", "avg_degree", "max_degree", "diameter",
    "avg_path_length", "avg_clustering", "components", "segments",
    "all_in_index", "all_in_segment_label", "final_segment_cast_share",
    "max_simultaneous_speakers", "gini_words", "effective_speakers",
    "top_speaker", "top_speaker_word_share", "top_speaker_temporal_gini",
    "edge_weight"];
  const round = v => (typeof v === "number" && !Number.isInteger(v))
    ? +v.toFixed(6) : v;
  const rows = [];
  Object.keys(DATA.segmentations || {{}}).forEach(function (spine) {{
    const blk = DATA.segmentations[spine] || {{}};
    // The base block is the unaggregated stage view; `variants` holds the
    // rest, keyed "<model>:<comma-joined groups>".
    const entries = [["full", "", blk.metrics]];
    const vars = blk.variants || {{}};
    Object.keys(vars).sort().forEach(function (key) {{
      const cut = key.indexOf(":");
      entries.push([key.slice(0, cut), key.slice(cut + 1), (vars[key] || {{}}).metrics]);
    }});
    entries.forEach(function (e) {{
      const model = e[0], groups = e[1], m = e[2];
      if (!m) return;
      const si = m.segment_indices || {{}};
      const sd = m.speech_distribution || {{}};
      rows.push([play.id || "", name, spine, model, groups, m.size, m.numEdges,
        round(m.density), round(m.averageDegree), m.maxDegree, m.diameter,
        round(m.averagePathLength), round(m.averageClustering),
        m.numConnectedComponents, m.num_segments, round(si.all_in_index),
        si.all_in_segment_label, round(si.final_segment_cast_share),
        si.max_simultaneous_speakers, round(sd.gini_words),
        round(sd.effective_speakers),
        (sd.top_speaker_ids || []).join(", "),
        round(sd.top_speaker_word_share), round(sd.top_speaker_temporal_gini),
        m.edge_weight].map(v => v == null ? "" : v));
    }});
  }});
  return {{ name: name + "-all-configurations", header: header, rows: rows }};
}}
function currentSegData() {{
  // Variants are keyed by `"<mute_mode>:<sorted_group_subset>"`, e.g.:
  //   "full:"            = stage co-presence, no aggregation (= top-level)
  //   "p-speaking:"       = speaking cast / play level, no aggregation
  //   "s-speaking:"       = speaking cast / segment level, no aggregation
  //   "full:choros"       = stage co-presence, aggregated by choros
  //   "p-speaking:choros" = speaking cast / play level, aggregated
  //   "s-speaking:choros" = speaking cast / segment level, aggregated
  // The mute radio + the per-group checkboxes uniquely determine the key.
  // "full" with no aggregation is the top-level fields, not a variant.
  const base = DATA.segmentations[STATE.seg];
  if (!base) return base;
  const muteKey = STATE.muteMode || "full";
  const groupKey = Array.from(STATE.aggregateGroups || []).sort().join(",");
  if (muteKey === "full" && !groupKey) return base;
  const variant = (base.variants || {{}})[muteKey + ":" + groupKey];
  if (variant) return variant;
  // Nothing for this combination -- which the writer should not allow, the
  // checkboxes being drawn from the groups it built variants for.  Should it
  // happen anyway, give back a block whose label is true.  Returning `base`
  // outright would hand over the stage-presence graph while the radio, the
  // chips and the figure captions still read "speaking cast": a different
  // model, a different node set, and nothing on screen to say so.
  console.warn("no block for " + muteKey + ":" + groupKey
               + " on spine " + STATE.seg + "; falling back");
  // Drop the aggregation first -- the same model, unaggregated.
  if (groupKey) {{
    if (STATE.aggregateGroups) STATE.aggregateGroups.clear();
    document.querySelectorAll('#aggregate-toggles input[type="checkbox"]')
      .forEach(cb => {{ cb.checked = false; }});
    const unaggregated = (base.variants || {{}})[muteKey + ":"];
    if (unaggregated) return unaggregated;
  }}
  // Only then the model, and say which one is showing.
  if (muteKey !== "full") {{
    STATE.muteMode = "full";
    document.querySelectorAll('input[name="mute-mode"]')
      .forEach(r => {{ r.checked = (r.value === "full"); }});
  }}
  return base;
}}
// Active-filter chip strip in the header.  Always shows the current
// network model (mutes-in / mutes-out) plus one chip per group currently
// aggregated.  Screenshots therefore document the exact methodological
// configuration that produced them.
function renderActiveFilters() {{
  const host = document.getElementById("active-filters");
  if (!host) return;
  host.innerHTML = "";
  // Model chip - always shown so the reader knows which model is in force.
  const ml = MUTE_MODE_LABELS[STATE.muteMode] || MUTE_MODE_LABELS.full;
  const modelLabel = ml.label
    + ' <span class="detail">(' + ml.detail + ')</span>';
  host.innerHTML += '<span class="filter-chip">' + modelLabel + '</span> ';
  // Aggregation chips.
  for (const g of Array.from(STATE.aggregateGroups || []).sort()) {{
    host.innerHTML += '<span class="filter-chip">aggregate <i>partOf</i> &rarr; <code>' + g + '</code></span> ';
  }}
}}

// Under the dual-model design, the mute toggle selects a different
// precomputed variant entirely (mutes-in: on-stage cast; mutes-out:
// per-segment speaking cast).  The variant's `characters` array carries
// every character declared in <listPerson> (each row tagged with
// `in_network`), so to render only the active graph's nodes we filter
// by the precomputed `in_network` flag.  Under mutes-out this drops the
// pure mutes (and any listPerson entry that never appeared on stage);
// under mutes-in it keeps everyone the static graph kept.
function visibleCharacters() {{
  return currentSegData().characters.filter(c => c.in_network !== false);
}}
function edgeEnd(v) {{ return (v && typeof v === "object") ? v.id : v; }}
// A collective and its own part are one body, and the graph builders never
// join them (network._pairs).  The cliques this page draws per segment skip
// the pair the same way, or a middle sequence holding a split would show the
// chorus meeting its own halves.
function partOfMap() {{
  const m = new Map();
  currentSegData().characters.forEach(c => m.set(c.id, new Set(c.part_of || [])));
  return m;
}}
function oneBody(partOf, a, b) {{
  return (partOf.has(a) && partOf.get(a).has(b))
      || (partOf.has(b) && partOf.get(b).has(a));
}}
function visibleEdges() {{ return currentSegData().edges; }}
// Per-segment cast under the active network model.  Used by DCR / sigma /
// beat chart, and matching the cast the pipeline hands to the plot-dynamics
// indices, so every per-segment reading on the page answers for one model:
//   full       -> every character on stage (seg.characters)
//   p-speaking -> stage cast minus play-level mutes (intersected with
//                 the kept node set of the current variant)
//   s-speaking -> only the characters the segment attributes an utterance
//                 to (seg.speakers)
function castOf(seg) {{
  const m = STATE.muteMode || "full";
  if (m === "full")    return seg.characters.slice();
  if (m === "s-speaking") return (seg.speakers || []).slice();
  // p-speaking: filter the stage cast by the variant's kept (non-mute) IDs
  const kept = new Set(visibleCharacters().map(c => c.id));
  return (seg.characters || []).filter(cid => kept.has(cid));
}}

// Segment-change rates following Trilcke/Fischer et al. 2017 (DH2017):
//   segment_change_rate(i) = |C_i Δ C_{{i+1}}| / |C_i ∪ C_{{i+1}}|
// drama_change_rate = mean of those.  Recomputed on the fly so the mute
// toggle (and segmentation tab) is honoured.
function segmentChangeRates() {{
  // Returns an array of {{fromId, fromNo, rate}} objects, one per
  // consecutive segment pair.  `fromId` is the seg.id of the segment the
  // transition departs from -- the LINKAGE key (scrub target, TEI
  // pre-select).  `fromNo` is the DISPLAY number in the real-segment
  // frame: the empty pre-play marker counts as segment 0, so its skipped
  // outgoing transition is 0 → 1 (always 1.0 by definition: comparing
  // anything with the empty set) and the first plotted transition
  // reads 1 → 2 on every spine.  Symmetrically, the
  // transition INTO the empty terminal segment (the closing bracket
  // after a full exeunt) is 1.0 by the same construction and is
  // likewise skipped: the series ends at the last transition between
  // acted segments.
  const segs = currentSegData().segments;
  const out = [];
  const startI = (segs.length > 0 && segs[0].is_initial &&
                  castOf(segs[0]).length === 0) ? 1 : 0;
  const endI = (segs.length > 1 && segs[segs.length - 1].is_final &&
                castOf(segs[segs.length - 1]).length === 0)
               ? segs.length - 2 : segs.length - 1;
  for (let i = startI; i < endI; i++) {{
    const a = new Set(castOf(segs[i]));
    const b = new Set(castOf(segs[i + 1]));
    const union = new Set([...a, ...b]);
    const rate = union.size === 0 ? 0 :
      ([...union].filter(x => !(a.has(x) && b.has(x))).length / union.size);
    out.push({{fromId: segs[i].id, fromNo: segs[i].id - startI, rate: rate}});
  }}
  return out;
}}
function dramaChangeRate(rates) {{
  if (!rates.length) return 0;
  return rates.reduce((s, r) => s + r.rate, 0) / rates.length;
}}
function stdev(arr, mean) {{
  // Accepts either an array of numbers OR an array of {{rate}} objects.
  if (arr.length < 2) return 0;
  const get = arr[0] && typeof arr[0] === "object" && "rate" in arr[0]
    ? (x => x.rate) : (x => x);
  const v = arr.reduce((s, x) => s + (get(x) - mean) ** 2, 0) / arr.length;
  return Math.sqrt(v);
}}

// -------------------------------------------------------------------- tabs
function renderTabs() {{
  const tabs = d3.select("#seg-tabs");
  const labels = {{ sd: "Stage directions", "large-seq": "large-seq", "middle-seq": "middle-seq" }};
  tabs.selectAll("button.tab")
    .data(AVAILABLE_MODES, d => d)
    .join(
      enter => enter.insert("button", ".toggles").attr("class", "tab")
        .text(d => labels[d] || d)
        .on("click", (_, d) => {{
          STATE.seg = d;
          STATE.segmentIdx = -1;
          render();
        }}),
      update => update,
      exit => exit.remove()
    )
    .classed("active", d => d === STATE.seg);
}}

// -------------------------------------------------------------------- KPIs
function renderKPIs() {{
  const m = currentSegData().metrics;
  const rates = segmentChangeRates();
  const dcr = dramaChangeRate(rates);
  const sdv = stdev(rates, dcr);
  const dem = m.demographics || {{}};
  const spd = m.speech_distribution || {{}};
  const sgi = m.segment_indices || {{}};
  const sx  = dem.sex || {{male: 0, female: 0, mixed: 0, unspecified: 0}};
  const na  = dem.nature || {{human: 0, divine: 0, animal: 0, concept: 0, other: 0}};

  // Helper: "a · b" / "a · b · c" pair-rendering for compact composition rows.
  const pair = (...xs) => xs.map(v => v == null ? "0" : String(v)).join(" \\u00B7 ");

  const topShare = spd.top_speaker_word_share || 0;
  const allInIdx = sgi.all_in_index;
  const allInLab = sgi.all_in_segment_label;
  const finalSz  = sgi.final_segment_cast_share;

  // No alternative "speakers-only" line: the model radio already selects
  // which cast is in view, and every value below -- the plot-dynamics
  // indices included -- is computed for the model that is active.
  const sections = [
    {{
      title: "Headline",
      hint: (MUTE_MODE_LABELS[STATE.muteMode] || MUTE_MODE_LABELS.full).label
            + " model",
      items: [
        {{ k: "order",           v: m.size }},
        {{ k: "edges",           v: m.numEdges }},
        {{ k: "density",         v: fmt(m.density) }},
        {{ k: "average degree",  v: fmt(m.averageDegree, 2) }},
        {{ k: "max degree",
            v: m.maxDegree + " (" + (m.maxDegreeIds || []).join(", ") + ")" }},
        {{ k: "segments",        v: m.num_segments }},
        // Same category as the rest of the section and shown with the same
        // weight; what differs is how much they separate, which the
        // footnote states as a measured fact rather than as a hedge.
        {{ k: "diameter",               v: m.diameter }},
        {{ k: "average path length",    v: fmt(m.averagePathLength, 2) }},
        {{ k: "average clustering",     v: fmt(m.averageClustering, 3) }},
        {{ k: "connected components",   v: m.numConnectedComponents }},
      ],
      footnote: "every value here is exact for the graph on screen, not an estimate. Two of them separate little at drama scale: over the eleven Aristophanic comedies and all 135 model \\u00d7 segmentation combinations, the diameter is 2 in 95 cases and never above 4, and the cast is connected in 128. Clustering is also raised by construction, each segment contributing a clique \\u2014 see Methods \\u00a71.",
    }},
    {{
      title: "Cast composition",
      items: [
        {{ k: "speakers \\u00B7 mutes",
            v: pair(dem.speakers, dem.mutes) }},
        {{ k: "individuals \\u00B7 collectives",
            v: pair(dem.individuals, dem.collectives) }},
        {{ k: sx.mixed ? "male \\u00B7 female \\u00B7 mixed \\u00B7 unspec."
                       : "male \\u00B7 female \\u00B7 unspec.",
            v: sx.mixed ? pair(sx.male, sx.female, sx.mixed, sx.unspecified)
                        : pair(sx.male, sx.female, sx.unspecified) }},
        {{ k: na.other
               ? "human \\u00B7 divine \\u00B7 animal \\u00B7 concept \\u00B7 other"
               : "human \\u00B7 divine \\u00B7 animal \\u00B7 concept",
            v: na.other
               ? pair(na.human, na.divine, na.animal, na.concept, na.other)
               : pair(na.human, na.divine, na.animal, na.concept) }},
      ],
    }},
    {{
      title: "Speech distribution",
      items: [
        {{ k: "top speaker",
            v: ((spd.top_speaker_ids || []).join(", ") || "\\u2014") +
               " (" + fmt(topShare * 100, 1) + "%)" }},
        {{ k: "Gini (words)",         v: fmt(spd.gini_words || 0, 3) }},
        {{ k: "effective speakers",   v: fmt(spd.effective_speakers || 0, 2) }},
        {{ k: "total words spoken",   v: spd.total_words_spoken || 0 }},
      ],
    }},
    {{
      title: "Plot dynamics (Fischer et al. 2017)",
      items: [
        {{ k: "drama-change rate",  v: fmt(dcr, 3),  beat: true }},
        {{ k: "\\u03C3 change rate", v: fmt(sdv, 3), beat: true }},
        {{ k: "all-in index",
            v: (allInIdx == null ? "\\u2014" : fmt(allInIdx, 3)) +
               (allInLab == null ? "" : " (at " + allInLab + ")") }},
        {{ k: "final segment cast share", v: fmt(finalSz, 3) }},
        {{ k: "max simultaneous speakers", v: sgi.max_simultaneous_speakers || 0 }},
      ],
    }},
  ];

  const root = d3.select("#kpis");
  root.selectAll("*").remove();
  const secs = root.selectAll(".metric-section")
    .data(sections).enter()
    .append("section")
    .attr("class", "metric-section");
  const heads = secs.append("h4");
  heads.append("span").text(d => d.title);
  // A hint, when present, drops to its own line under the title.
  secs.filter(d => d.hint).select("h4").append("span")
    .attr("class", "caveat").style("font-style", "normal")
    .text(d => "\\u2014 " + d.hint);
  const dls = secs.append("dl").attr("class", "metrics-list");
  const its = dls.selectAll(".item")
    .data(d => d.items).enter().append("div")
    .attr("class", d =>
      "item" + (d.beat ? " beat" : ""));
  its.append("dt").text(d => d.k);
  const dds = its.append("dd");
  dds.append("span").attr("class", "primary").text(d => d.v);
  // Secondary speakers-only annotation, only when present and different.
  dds.filter(d => d.alt).append("span").attr("class", "alt").text(d => d.alt);
  // Footnote at the bottom of a section (currently used by Headline for
  // the structural-metrics caveat).
  secs.filter(d => d.footnote).append("p")
    .attr("class", "section-footnote").text(d => d.footnote);
}}

// -------------------------------------------------------------------- static graph
function renderStaticGraph() {{
  const svg = d3.select("#static-graph");
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.selectAll("*").remove();
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);

  const root = svg.append("g").attr("class", "zoom-root");
  STATE.staticZoom = d3.zoom()
    .scaleExtent([0.25, 8])
    .on("zoom", (ev) => {{
      STATE.zoomTransform = ev.transform;
      root.attr("transform", ev.transform);
    }});
  svg.call(STATE.staticZoom);
  svg.on("dblclick.zoom", null);
  svg.on("dblclick", () => {{
    svg.transition().duration(400).call(STATE.staticZoom.transform, d3.zoomIdentity);
  }});

  const chars = visibleCharacters();
  const charById = new Map(chars.map(c => [c.id, c]));
  // Clone edges with fresh string source / target so d3-force mutates these
  // copies and leaves the shared `currentSegData().edges` untouched.  Without
  // this, the second render sees source / target as node objects from the
  // previous simulation and the visibleEdges() filter drops everything.
  const links = visibleEdges()
    .map(e => ({{
      source: edgeEnd(e.source),
      target: edgeEnd(e.target),
      weight: e.weight,
      segments_shared: e.segments_shared,
    }}))
    .filter(e => charById.has(e.source) && charById.has(e.target));
  const nodes = chars.map(c => Object.assign({{}}, c));

  if (STATE.forceSim) STATE.forceSim.stop();

  const fp = STATE.forceParams;
  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(fp.link).strength(0.4))
    .force("charge", d3.forceManyBody().strength(-fp.repulsion))
    .force("x", d3.forceX(w / 2).strength(fp.gravity))
    .force("y", d3.forceY(h / 2).strength(fp.gravity))
    .force("collide", d3.forceCollide(d => 12 + Math.sqrt(d.degree)));

  STATE.forceSim = sim;

  const linkSel = root.append("g").selectAll("line")
    .data(links).enter().append("line")
    .attr("class", "link")
    .attr("stroke-width", d => Math.min(8, Math.sqrt(d.weight)));

  const nodeSel = root.append("g").selectAll("g")
    .data(nodes, d => d.id).enter().append("g")
    .attr("class", "node");

  // Degree encoded by node radius: r = 3 + sqrt(degree) * 2.8.
  // Square-root radius makes area grow roughly with degree; the 3px floor
  // keeps an isolate visible and costs proportionality at the low end.
  // The multiplier is bold enough to read: a degree-30 node is 6.1x the
  // RADIUS of a degree-0 isolate and 37x its area, where the old
  // `r = 5 + sqrt(degree) * 1.2` gave 2.3x the radius and 5.4x the area
  // -- a difference the eye did not register.
  nodeSel.append("circle")
    .attr("r", d => 3 + Math.sqrt(d.degree) * 2.8)
    .attr("fill", nodeColor);

  nodeSel.append("title").text(d =>
     d.name + " (" + d.id + ")\\n" +
     "degree " + d.degree + ", weighted " + fmt(d.weightedDegree, 1) + "\\n" +
     "betw " + fmt(d.betweenness) + ", clos " + fmt(d.closeness) + ", eig " + fmt(d.eigenvector));

  nodeSel.append("text")
    .attr("x", d => 4 + Math.sqrt(d.degree) * 2.8)
    .attr("y", 3)
    .attr("display", STATE.showLabels ? null : "none")
    .text(d => d.name);

  nodeSel.call(d3.drag()
    .on("start", (ev, d) => {{ if (!ev.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
    .on("drag", (ev, d) => {{ d.fx = ev.x; d.fy = ev.y; }})
    .on("end", (ev, d) => {{ if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }}));

  // Click a node -> focus on its ego-network.  Click again on the same
  // node, or on the SVG background, to clear.  We use stopPropagation so
  // the SVG-background handler below fires ONLY on background clicks.
  nodeSel.on("click", function(event, d) {{
    event.stopPropagation();
    STATE.focusNode = (STATE.focusNode === d.id) ? null : d.id;
    applyStaticFocus();
  }});
  svg.on("click.focus", function() {{
    if (STATE.focusNode) {{
      STATE.focusNode = null;
      applyStaticFocus();
    }}
  }});

  sim.on("tick", () => {{
    linkSel.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
           .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    nodeSel.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
  }});

  // Snapshot positions for the dynamic graph (and again on end).
  for (let i = 0; i < 100; i++) sim.tick();
  STATE.positions = new Map(nodes.map(n => [n.id, {{x: n.x, y: n.y}}]));
  // NB: `pendingAutoFit` is NOT set here.  It is set explicitly by the
  // events that warrant a refit (initial mount, tab switch, slider release,
  // reset, fit button).  Mute/label toggles, drags and continuous slider
  // input therefore do NOT cause the camera to jump.
  sim.on("end", () => {{
    STATE.positions = new Map(nodes.map(n => [n.id, {{x: n.x, y: n.y}}]));
    if (STATE.pendingAutoFit) {{
      STATE.pendingAutoFit = false;
      autoFitZoom(true);
    }}
    renderDynamicGraph();
  }});
}}

// -------------------------------------------------------------------- dynamic graph
function renderDynamicGraph() {{
  const svg = d3.select("#dynamic-graph");
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.selectAll("*").remove();
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);
  if (!STATE.positions) return;

  // Find the bbox of static positions and rescale into the dynamic SVG.
  // We use INDEPENDENT x and y scales so the layout occupies the full
  // canvas in both directions, rather than preserving the static graph's
  // aspect ratio (which leaves most of the horizontal canvas empty on
  // wide screens and crowds the labels together).  Horizontal padding is
  // larger than vertical so long character labels don't run off the edge.
  const pts = Array.from(STATE.positions.values());
  if (pts.length === 0) return;
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const PAD_X = 90, PAD_Y = 40;
  const sx = (w - 2 * PAD_X) / Math.max(1, x1 - x0);
  const sy = (h - 2 * PAD_Y) / Math.max(1, y1 - y0);
  const proj = id => {{
    const p = STATE.positions.get(id);
    if (!p) return {{x: w / 2, y: h / 2}};
    return {{x: PAD_X + (p.x - x0) * sx, y: PAD_Y + (p.y - y0) * sy}};
  }};

  const chars = visibleCharacters();
  const segs = currentSegData().segments;
  // Segment IDs are 1-indexed; STATE.segmentIdx carries the id (or -1
  // for the static-aggregate frame), so we look up by id, not by array
  // position.  Internally segs[] is still a 0-indexed array.
  const seg = STATE.segmentIdx >= 1
    ? segs.find(s => s.id === STATE.segmentIdx) : null;

  let presentSet, edgesNow;
  if (seg) {{
    const cast = castOf(seg);
    presentSet = new Set(cast);
    const visible = new Set(chars.map(c => c.id));
    edgesNow = [];
    const arr = cast.filter(c => visible.has(c));
    const partOf = partOfMap();
    for (let i = 0; i < arr.length; i++)
      for (let j = i + 1; j < arr.length; j++)
        if (!oneBody(partOf, arr[i], arr[j]))
          edgesNow.push({{source: arr[i], target: arr[j]}});
  }} else {{
    presentSet = new Set(chars.map(c => c.id));
    edgesNow = visibleEdges();
  }}

  svg.append("g").selectAll("line")
    .data(edgesNow).enter().append("line")
    .attr("class", "link")
    .attr("x1", d => proj(d.source).x).attr("y1", d => proj(d.source).y)
    .attr("x2", d => proj(d.target).x).attr("y2", d => proj(d.target).y)
    .attr("stroke-width", 1);

  const nodeSel = svg.append("g").selectAll("g")
    .data(chars, d => d.id).enter().append("g")
    .attr("class", d => "node" + (presentSet.has(d.id) ? "" : " absent"))
    .attr("transform", d => {{ const p = proj(d.id); return `translate(${{p.x}},${{p.y}})`; }});
  // Dynamic-graph node size:
  //   - When scrubbing a specific segment, size encodes per-segment words
  //     spoken by this character (log2-compressed so a 200-word speech
  //     isn't 40x the area of a 5-word one).  Reacts as the user scrubs.
  //   - On the static-aggregate frame (`seg` null, segmentIdx === -1),
  //     size matches the bold static-graph encoding (degree-based) so the
  //     dynamic panel's overview view is consistent with the big static
  //     graph above it.
  const wordsOf = id => (seg && seg.words_by_speaker)
    ? (seg.words_by_speaker[id] || 0) : 0;
  const radius = d => seg
    ? 3 + Math.log2(1 + wordsOf(d.id)) * 1.5
    : 3 + Math.sqrt(d.degree) * 2.8;
  nodeSel.append("circle")
    .attr("r", radius)
    .attr("fill", nodeColor);
  nodeSel.append("text")
    .attr("x", d => radius(d) + 1)
    .attr("y", 3)
    .attr("display", STATE.showLabels ? null : "none")
    .text(d => d.name);
  nodeSel.append("title").text(d => {{
    const w = wordsOf(d.id);
    return d.name + " (" + d.id + ")"
      + (seg ? "\\nwords this segment: " + w : "");
  }});
}}

// -------------------------------------------------------------------- size-over-segments chart

// Cumulative word-position boundaries for each segment, in array order.
// Returns {{left:[], right:[], total}}.  Drives the "word position" x-axis
// mode, which spaces segments by their word mass (stage-time) instead of by
// index: segment i occupies the word interval [left[i], right[i]].
function segWordBounds(segs) {{
  const left = [], right = [];
  let acc = 0;
  for (let i = 0; i < segs.length; i++) {{
    left.push(acc);
    acc += (segs[i].word_count || 0);
    right.push(acc);
  }}
  return {{ left, right, total: acc }};
}}

function renderProgressionChart(selector, valuesOf, label, color) {{
  // Shared renderer for the size and words panels.  They share the x-axis
  // (the segment id, so both curves line up with the segments table) and the
  // curve style; only the y series and the colour differ.  Neither is
  // clickable: jumping to a segment is done from the beat chart, the
  // timeline, the heatmap or the tables.
  const svg = d3.select(selector);
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.selectAll("*").remove();
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);
  const M = {{top: 16, right: 24, bottom: 28, left: 36}};
  const segs = currentSegData().segments;
  if (segs.length === 0) return;
  const ys = segs.map(valuesOf);

  // Segment IDs are 1-indexed throughout the app; the chart x-axis
  // shows the segment id directly.  Domain spans [first.id, last.id]
  // which is naturally [1, N] (or [1, N+1] etc. when the empty initial /
  // final markers are present).
  const firstId = segs[0].id, lastId = segs[segs.length - 1].id;
  const x = d3.scaleLinear().domain([firstId, lastId]).range([M.left, w - M.right]);
  const y = d3.scaleLinear().domain([0, d3.max(ys) || 1]).nice().range([h - M.bottom, M.top]);

  svg.append("g").attr("transform", `translate(0,${{h - M.bottom}})`)
     .call(d3.axisBottom(x).ticks(Math.min(10, segs.length)).tickFormat(d => Math.round(d)));
  svg.append("g").attr("transform", `translate(${{M.left}},0)`)
     .attr("color", color)
     .call(d3.axisLeft(y).ticks(5));
  svg.append("text").attr("x", M.left).attr("y", 11).attr("font-size", 10)
     .attr("fill", color).text(label);
  svg.append("text").attr("x", w - M.right).attr("y", h - 4).attr("text-anchor", "end")
     .attr("font-size", 10).attr("fill", "var(--muted)").text("segment");

  // The line plots y values against the segment's id (not the array index),
  // so the curve's x positions match the segments-table id column exactly.
  const line = d3.line()
    .x((_, i) => x(segs[i].id))
    .y(d => y(d))
    .curve(d3.curveMonotoneX);
  svg.append("path").attr("fill", "none").attr("stroke", color)
     .attr("stroke-width", 2).attr("d", line(ys));
}}

function renderSizeChart() {{
  renderProgressionChart("#size-chart",
                         s => castOf(s).length,
                         "characters", "var(--accent)");
}}
function renderWordChart() {{
  renderProgressionChart("#word-chart",
                         s => s.word_count || 0,
                         "words", "var(--speaker)");
}}

// -------------------------------------------------------------------- beat chart
function renderBeatChart() {{
  const svg = d3.select("#beat-chart");
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.selectAll("*").remove();
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);
  const M = {{top: 16, right: 24, bottom: 28, left: 36}};
  const rates = segmentChangeRates();
  if (rates.length === 0) {{
    svg.append("text").attr("x", w / 2).attr("y", h / 2)
      .attr("text-anchor", "middle").attr("fill", "var(--muted)")
      .text("not enough segments");
    return;
  }}
  const dcr = dramaChangeRate(rates);
  const segs = currentSegData().segments;

  const vb = segWordBounds(segs);
  const wordMode = (STATE.chartXMode === "word" && vb.total > 0);

  // A transition departs from segment fromId.  In segment mode it is plotted
  // at that id; in word mode it sits at the boundary between the from-segment
  // and the next — i.e. the cumulative words up to and including fromId — so
  // doorway flurries collapse and turnover between long scenes stands alone.
  let x, xPos, xLabelText;
  if (wordMode) {{
    const idToRight = new Map();
    segs.forEach((s, i) => idToRight.set(s.id, vb.right[i]));
    x = d3.scaleLinear().domain([0, vb.total]).range([M.left, w - M.right]);
    xPos = d => x(idToRight.has(d.fromId) ? idToRight.get(d.fromId) : 0);
    xLabelText = "word position";
  }} else {{
    const firstNo = rates[0].fromNo, lastNo = rates[rates.length - 1].fromNo;
    x = d3.scaleLinear().domain([firstNo, lastNo]).range([M.left, w - M.right]);
    xPos = d => x(d.fromNo);
    xLabelText = "transition from segment";
  }}
  const y = d3.scaleLinear().domain([0, 1]).range([h - M.bottom, M.top]);

  svg.append("g").attr("transform", `translate(0,${{h - M.bottom}})`)
    .call(wordMode
      ? d3.axisBottom(x).ticks(6)
      : d3.axisBottom(x).ticks(Math.min(10, rates.length)).tickFormat(d => Math.round(d)));
  svg.append("g").attr("transform", `translate(${{M.left}},0)`)
    .call(d3.axisLeft(y).ticks(5).tickFormat(d3.format(".1f")));
  svg.append("text").attr("x", M.left).attr("y", 11).attr("font-size", 10)
    .attr("fill", "var(--muted)").text("change rate");
  svg.append("text").attr("x", w - M.right).attr("y", h - 4).attr("text-anchor", "end")
    .attr("font-size", 10).attr("fill", "var(--muted)")
    .text(xLabelText);

  // drama-change-rate reference line.
  svg.append("line")
    .attr("x1", M.left).attr("x2", w - M.right)
    .attr("y1", y(dcr)).attr("y2", y(dcr))
    .attr("stroke", "#999").attr("stroke-dasharray", "3,3");
  svg.append("text").attr("x", w - M.right - 4).attr("y", y(dcr) - 4)
    .attr("text-anchor", "end").attr("font-size", 10).attr("fill", "var(--beat)")
    .text("drama-change rate = " + fmt(dcr, 3));

  const line = d3.line().x(xPos).y(d => y(d.rate));
  svg.append("path").attr("fill", "none").attr("stroke", "var(--beat)")
    .attr("stroke-width", 2).attr("d", line(rates));
  // Markers, each paired with a generous transparent hover target that
  // carries a native tooltip naming the segment transition in the display
  // frame (fromNo → fromNo+1) and its change-rate value; the click
  // still scrubs by fromId, the segment's real id.
  const mk = svg.append("g");
  mk.selectAll("circle.beat-pt").data(rates).enter().append("circle")
    .attr("class", "beat-pt")
    .attr("cx", xPos).attr("cy", d => y(d.rate))
    .attr("r", 2).attr("fill", "var(--beat)");
  mk.selectAll("circle.beat-hit").data(rates).enter().append("circle")
    .attr("class", "beat-hit")
    .attr("cx", xPos).attr("cy", d => y(d.rate))
    .attr("r", 7).attr("fill", "transparent")
    .style("pointer-events", "all").style("cursor", "pointer")
    .on("click", (_, d) => {{
      // Same scrub action as the segments table / heatmap: jump the
      // dynamic graph to the segment this transition departs from.
      STATE.segmentIdx = d.fromId;
      _pendingTEISegment = d.fromId;   // also pre-select for the TEI source view
      updateSlider(); renderDynamicGraph(); renderInfo();
    }})
    .append("title")
      .text(d => `segment ${{d.fromNo}} \\u2192 ${{d.fromNo + 1}}  \\u00B7  change rate ${{fmt(d.rate, 3)}}`);
}}

// -------------------------------------------------------------------- tables
function renderCharTable() {{
  const cols = [
    ["name",          d => d.name + (d.name_grc ? " ("+d.name_grc+")" : "")],
    ["roles",         d => roleChips(d), true],
    ["degree",        d => d.degree, true],
    ["weighted",      d => fmt(d.weightedDegree, 1), true,
                      d => d.weightedDegree || 0],
    ["betweenness",   d => fmt(d.betweenness), true],
    ["closeness",     d => fmt(d.closeness), true],
    ["eigenvector",   d => fmt(d.eigenvector), true],
    // Local clustering and its triangles: read together, they say whether a
    // character's partners also speak to one another.
    ["clustering",    d => fmt(d.clustering, 3), true],
    ["triangles",     d => d.triangles || 0, true],
  ];
  drawTable("#char-table", cols, visibleCharacters(), "degree", -1);
}}
// Speech concentration table -- per-character temporal Gini.  Sits inside
// Plot Dynamics conceptually (a time-distribution measure on speech, not
// a network-position measure).  Filtered to speakers with at least 40
// words to keep the table interpretable; the threshold is purely a
// display filter and does not influence any number in the table.
function renderTGiniTable() {{
  const MIN_WORDS = 40;
  const csd = currentSegData() || {{}};
  const nActive = ((csd.metrics || {{}}).speech_distribution || {{}}).n_active_segments;
  // Pull speech-time rows out of the nodes list (the centralities table
  // ignores these columns).  visibleCharacters() respects the mute
  // toggle, which here amounts to dropping pure mutes -- they have no
  // words anyway, so the filter is a no-op for the metric but keeps
  // the row set consistent with the rest of the dashboard.
  const rows = visibleCharacters()
    .filter(d => d.temporal_gini != null && (d.total_words || 0) >= MIN_WORDS);
  const cols = [
    ["character",       d => d.name + (d.name_grc ? " ("+d.name_grc+")" : "")],
    ["roles",           d => roleChips(d), true],
    ["words",           d => d.total_words || 0, true],
    // Denominator is the character's own stage time, not the play's span:
    // that is what tGini beside it now divides by, and the two columns
    // would otherwise answer different questions.
    ["speaks / on stage", d => {{
      const s = d.speaking_segments || 0;
      const m = d.n_onstage_segments || 0;
      if (!m) return s;
      return s + " / " + m + " (" + (100 * s / m).toFixed(0) + "%)";
    }}, true, d => (d.n_onstage_segments
                    ? (d.speaking_segments || 0) / d.n_onstage_segments : 0)],
    ["tGini",           d => fmt(d.temporal_gini, 3), true],
  ];
  drawTable("#tgini-table", cols, rows, "words", -1, (d) => {{
    // Click-through: scrub the dynamic graph to the character's
    // loudest segment.  Same wiring pattern as the segments-table
    // row click (STATE.segmentIdx -> updateSlider + render).
    const segs = (currentSegData() || {{}}).segments || [];
    let best = null, bestV = 0;
    for (const s of segs) {{
      const vbs = s.words_by_speaker || {{}};
      const v = vbs[d.id] || 0;
      if (v > bestV) {{ bestV = v; best = s.id; }}
    }}
    if (best != null) {{
      STATE.segmentIdx = best;
      updateSlider();
      renderDynamicGraph();
      renderInfo();
    }}
  }});
}}
// Role chips: two independent axes, in the vocabulary of the demographics
// panel -- muteness, and individual (<person>) vs collective (<personGrp>),
// with `chorus` as the specific collective.  The collectivity chip is always
// emitted.  It used to appear only for collectives, with a bare "speaker"
// standing in for everyone else, which set up a contrast that does not
// exist: the chorus speaks too, and in the speech-concentration table every
// row speaks by construction.
function roleChips(d) {{
  const out = [];
  if (d.is_mute) out.push('<span class="chip mute">mute</span>');
  if (d.is_chorus) out.push('<span class="chip chorus">chorus</span>');
  else if (d.is_collective) out.push('<span class="chip collective">collective</span>');
  else out.push('<span class="chip">individual</span>');
  return out.join(" ");
}}
function renderSegTable() {{
  // "chars" column counts the *operational* cast for the active edge
  // rule (speakers under mutes-out, stage-present under mutes-in).  Cast
  // column shows the same primary list; under mutes-out it also shows
  // present-but-silent in italics on a second line.
  const cols = [
    ["#",         d => d.id, true],
    ["label",     d => d.label],
    ["chars",     d => castOf(d).length, true],
    ["speeches",  d => d.num_speeches, true],
    ["words",     d => d.word_count, true],
    ["crossings", d => d.num_crossings || 0, true],
    ["cast",      d => {{
      const primary = castOf(d);
      const head = primary.join(", ");
      // The "silent-present" annotation is only meaningful under the
      // speaking-cast model, where the cast column shows speakers and we
      // want to surface stage-present-but-silent characters separately.
      // Under stage co-presence and the play-level model, present-but-silent
      // are already in `primary` (they're on stage), so no annotation.
      if (STATE.muteMode === "s-speaking") {{
        const silent = d.silent_present || [];
        if (silent.length > 0) {{
          const stxt = silent.join(", ");
          return head + '<div class="silent-present">silent: ' + stxt + '</div>';
        }}
      }}
      return head;
    }}],
  ];
  drawTable("#seg-table", cols, currentSegData().segments, "#", 1, (p) => {{
    // p is the segment object itself; its `id` field equals its position
    // in the segments array (set by the segmenter in document order).
    STATE.segmentIdx = p.id; updateSlider(); renderDynamicGraph(); renderInfo();
    // Pre-select this segment for the TEI source view, but don't switch
    // tabs.  The TEI dropdown picks this up next time the user opens
    // the TEI tab (see populateTEISegmentSelect).
    _pendingTEISegment = p.id;
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
      if (sortKey === c[0]) sortDir = -sortDir; else {{ sortKey = c[0]; sortDir = -1; }}
      drawTable(sel, cols, rows, sortKey, sortDir, onClickRow);
    }});
  const sortCol = cols.find(c => c[0] === sortKey) || cols[0];
  // A column may carry a 4th element: the value to order by, for when the
  // cell's text is not what the reader wants to sort on.  Without it the
  // sort is lexicographic on whatever is displayed, so "9 / 38 (24%)" lands
  // after "10 / 38 (26%)", and a formatted number orders by its digits --
  // putting "12.7" before "3.7".
  const keyOf = sortCol[3] || sortCol[1];
  rows = rows.slice().sort((a, b) => {{
    const va = keyOf(a); const vb = keyOf(b);
    if (typeof va === "number" && typeof vb === "number") return sortDir * (va - vb);
    return sortDir * String(va).localeCompare(String(vb));
  }});
  const tb = t.append("tbody");
  tb.selectAll("tr").data(rows).enter().append("tr")
    .style("cursor", onClickRow ? "pointer" : null)
    // Pass the data object itself to the callback; the previous version
    // passed `rows.indexOf(d)`, which broke whenever the table was sorted
    // by any column other than the natural (unsorted) order.
    .on("click", (_, d) => onClickRow && onClickRow(d))
    .selectAll("td").data((d, i) => cols.map(c => ({{c, d, i}}))).enter().append("td")
    .attr("class", o => o.c[2] ? "num" : null)
    .html(o => {{ const v = o.c[1](o.d, o.i); return v == null ? "" : v; }});
}}

// -------------------------------------------------------------------- controls
// Segment IDs are 1-indexed throughout.  STATE.segmentIdx carries the
// id directly (1..N, with -1 reserved for the static-aggregate frame).
// All controls below use seg.id rather than array positions; lookups
// go through .find() since the JS array is still 0-indexed.
function _segById(id) {{
  return currentSegData().segments.find(s => s.id === id);
}}
function _segIdRange() {{
  const segs = currentSegData().segments;
  if (!segs.length) return {{min: 1, max: 1}};
  return {{min: segs[0].id, max: segs[segs.length - 1].id}};
}}
function renderInfo() {{
  const segs = currentSegData().segments;
  const slider = document.getElementById("seg-slider");
  const range = _segIdRange();
  slider.min = range.min;
  slider.max = range.max;
  if (STATE.segmentIdx === -1) {{
    document.getElementById("seg-info").textContent = "static (all " + segs.length + " segments)";
  }} else {{
    const s = _segById(STATE.segmentIdx);
    if (!s) return;
    const cast = castOf(s);
    document.getElementById("seg-info").textContent =
      "[" + s.id + "] " + s.label + " - " + cast.length + " chars - " +
      s.num_speeches + " speeches - " + s.word_count + "w";
  }}
}}
function updateSlider() {{
  const range = _segIdRange();
  document.getElementById("seg-slider").value =
    Math.max(range.min, STATE.segmentIdx);
  renderSegmentTimeline();
}}

// Word-proportional segment timeline.  Each segment is a rectangle
// whose width is proportional to its word_count; the empty pre-play /
// final-empty markers get a small minimum width so they remain
// clickable.  The timeline doubles as a scrubber: clicking a segment
// jumps the dynamic graph to that segment.
function renderSegmentTimeline() {{
  const svg = d3.select("#segment-timeline");
  const segs = currentSegData().segments;
  if (!segs.length) {{ svg.selectAll("*").remove(); return; }}
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  svg.selectAll("*").remove();
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);

  // Word-proportional widths, but with a real *pixel* floor so that even a
  // 0-word segment (a silent entrance / exit beat) stays comfortably
  // clickable instead of collapsing to a 1px sliver on a long play -- the
  // former word-unit floor scaled down to ~1px and made such segments
  // impossible to hit, so clicks landed on the neighbour.
  const MIN_PX = 6;   // minimum clickable width per segment (px)
  const rawV = segs.map(s => Math.max(0, s.word_count || 0));
  const totalV = rawV.reduce((a, b) => a + b, 0) || 1;
  const flexible = Math.max(0, w - segs.length * MIN_PX);
  let cum = 0;
  const layout = segs.map((s, i) => {{
    const wpx = MIN_PX + (rawV[i] / totalV) * flexible;
    const x = cum;
    cum += wpx;
    return {{seg: s, x: x, w: wpx}};
  }});

  svg.append("g").selectAll("rect").data(layout).enter().append("rect")
    .attr("x", d => d.x)
    .attr("y", 2)
    .attr("width", d => Math.max(1, d.w - 1))
    .attr("height", h - 4)
    .attr("fill", d => {{
      if (d.seg.is_initial && (d.seg.word_count || 0) === 0) return "#f0f0f0";
      if (d.seg.is_final   && (d.seg.word_count || 0) === 0) return "#f0f0f0";
      // Tint by how "loud" the segment is, so the timeline doubles as a
      // words-over-segments preview.
      const maxV = d3.max(segs, s => s.word_count || 0) || 1;
      const t = (d.seg.word_count || 0) / maxV;
      return d3.interpolateRgb("#d9e6f3", "#1a5fb4")(t);
    }})
    .attr("class", d => d.seg.id === STATE.segmentIdx ? "current" : null)
    .on("click", (_, d) => {{
      STATE.segmentIdx = d.seg.id;
      _pendingTEISegment = d.seg.id;   // also pre-select for the TEI source view
      updateSlider();
      renderDynamicGraph();
      renderInfo();
    }})
    .append("title").text(d =>
      "[" + d.seg.id + "] " + d.seg.label +
      "  -  " + (d.seg.word_count || 0) + " words, " +
      (d.seg.characters ? d.seg.characters.length : 0) + " chars present");
}}

// Character x segment heatmap.  Rows = characters (filtered by mute
// toggle; sorted by the chosen mode), columns = segments in id order.
// Cell state:
//   - transparent   = character not in segment.characters
//   - light grey    = in segment.characters but not in segment.speakers
//   - white -> red  = speaking; intensity = per-segment words / max
// Click a cell to set STATE.segmentIdx to that segment.  Hover shows
// (character, segment, words) in the tooltip.
let _heatmapSort = "loudest";
// A chart can only be drawn into a container the browser has laid out.
// Where the page is rendered with no width -- a hidden window, a panel not
// yet on screen -- the plot area comes out negative, and the heatmap's cells
// would each be given a negative width: thousands of console errors and no
// picture.  Draw nothing there, and watch the element instead, so the chart
// appears by itself as soon as it has room.
let _awaitingWidth = null;
function drawWhenSized(node, draw) {{
  if (_awaitingWidth || typeof ResizeObserver === "undefined") return;
  _awaitingWidth = new ResizeObserver(() => {{
    if (node.clientWidth > 0) {{
      _awaitingWidth.disconnect();
      _awaitingWidth = null;
      draw();
    }}
  }});
  _awaitingWidth.observe(node);
}}
function renderHeatmap() {{
  const svg = d3.select("#character-segment-heatmap");
  const data = currentSegData();
  const segs = data.segments;
  const chars = visibleCharacters();
  if (!segs.length || !chars.length) {{ svg.selectAll("*").remove(); return; }}

  // Aggregate per-character total words (for the default sort) and
  // first-appearance segment id (for the "appearance order" sort).
  const totalWords = new Map();
  const firstAppearance = new Map();
  // Threshold passages = entrances + exits for each character across the
  // visible segment sequence (the same per-segment characters_present the
  // matrix renders, so it follows the active segmentation / mute / partOf
  // mode).  Drives the "most stage entrances/exits" row order: a figure on
  // stage throughout scores the minimum, one that shuttles on and off scores
  // high.  Padded with an empty stage before the first and after the last
  // segment, so the opening entrance and the closing exit both count
  // (passages = 2 x presence-runs).  NOT the <move type="crossing">
  // events, which by design never enter characters_present.
  const passages = new Map();
  chars.forEach(c => {{ totalWords.set(c.id, 0); firstAppearance.set(c.id, Infinity); passages.set(c.id, 0); }});
  let prevPresent = new Set();
  segs.forEach(s => {{
    const present = new Set(s.characters || []);
    chars.forEach(c => {{
      if (present.has(c.id) && firstAppearance.get(c.id) > s.id) {{
        firstAppearance.set(c.id, s.id);
      }}
      if (present.has(c.id) !== prevPresent.has(c.id)) {{
        passages.set(c.id, passages.get(c.id) + 1);
      }}
    }});
    prevPresent = present;
    const vbs = s.words_by_speaker || {{}};
    for (const id in vbs) {{
      if (totalWords.has(id)) totalWords.set(id, totalWords.get(id) + vbs[id]);
    }}
  }});
  // Trailing exit: the stage clears when the play ends, so every character
  // still present in the final segment crosses out once more.
  chars.forEach(c => {{ if (prevPresent.has(c.id)) passages.set(c.id, passages.get(c.id) + 1); }});

  // Sort rows.
  let rows = chars.slice();
  if (_heatmapSort === "appearance") {{
    rows.sort((a, b) => {{
      const fa = firstAppearance.get(a.id), fb = firstAppearance.get(b.id);
      if (fa !== fb) return fa - fb;
      return a.name.localeCompare(b.name);
    }});
  }} else if (_heatmapSort === "mobility") {{
    rows.sort((a, b) => {{
      const ca = passages.get(a.id) || 0, cb = passages.get(b.id) || 0;
      if (ca !== cb) return cb - ca;            // most threshold passages first
      const va = totalWords.get(a.id) || 0, vb = totalWords.get(b.id) || 0;
      if (va !== vb) return vb - va;            // ties: louder first, then name
      return a.name.localeCompare(b.name);
    }});
  }} else if (_heatmapSort === "alphabetical") {{
    rows.sort((a, b) => a.name.localeCompare(b.name));
  }} else {{
    // Loudest first (default).  Ties broken alphabetically.
    rows.sort((a, b) => {{
      const va = totalWords.get(a.id) || 0, vb = totalWords.get(b.id) || 0;
      if (va !== vb) return vb - va;
      return a.name.localeCompare(b.name);
    }});
  }}

  // Layout constants.
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  const LEFT = 160, RIGHT = 16, TOP = 16, BOTTOM = 32;
  const plotW = w - LEFT - RIGHT;
  if (!(plotW > 0)) {{ drawWhenSized(svg.node(), renderHeatmap); return; }}
  const cellW = plotW / segs.length;
  const cellH = Math.max(10, Math.min(20, (h - TOP - BOTTOM) / Math.max(1, rows.length)));

  svg.selectAll("*").remove();
  svg.attr("viewBox", `0 0 ${{w}} ${{h}}`);

  // Per-cell max words for colour normalisation.  Computed across the
  // visible character set under the current sort, so different mute /
  // aggregation modes get appropriately-scaled red intensity.
  let maxV = 0;
  segs.forEach(s => {{
    const vbs = s.words_by_speaker || {{}};
    for (const id of rows.map(r => r.id)) {{
      const v = vbs[id] || 0;
      if (v > maxV) maxV = v;
    }}
  }});
  // sqrt scaling so low-word cells still read as clearly red rather
  // than washed-out pink.  Ramp endpoints are pushed darker on both
  // sides (Brewer Reds palette, steps 3 and 8) so the gradient is
  // visible across the play's typical word-count range.
  const redScale = d3.scaleSqrt()
    .domain([0, Math.max(1, maxV)]).range([0, 1]);
  const colourSpeaking = d3.interpolateRgb("#fcbba1", "#a50f15");
  // Darker silent-present grey so it stands out against the page bg
  // and is unmistakably distinguishable from "absent" (transparent).
  const colourSilent = "#bbbbbb";
  // A speech whose text is not transmitted -- the XOPOY interludes, the
  // lacuna at Clouds 888a -- was performed, and is not silence: hatched in
  // the ramp's darkest red on a pale ground, so it reads as speech with
  // nothing in it.  The corpus chorus chart draws it the same way.
  const hatchId = "heatmap-notext-hatch";
  svg.append("defs").append("pattern").attr("id", hatchId)
    .attr("patternUnits", "userSpaceOnUse").attr("width", 4).attr("height", 4)
    .attr("patternTransform", "rotate(45)")
    .call(p => {{
      p.append("rect").attr("width", 4).attr("height", 4).attr("fill", "#fde0dd");
      p.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 4)
        .attr("stroke", "#a50f15").attr("stroke-width", 1.5);
    }});

  // Row labels.
  svg.append("g").selectAll("text").data(rows).enter().append("text")
    .attr("class", "row-label")
    .attr("x", LEFT - 6).attr("y", (_, i) => TOP + (i + 0.7) * cellH)
    .attr("text-anchor", "end")
    .text(d => d.name)
    .append("title").text(d => d.id + "  total words: " + (totalWords.get(d.id) || 0));

  // Cells.
  const cellsData = [];
  rows.forEach((c, ri) => {{
    segs.forEach((s, ci) => {{
      const present = (s.characters || []).indexOf(c.id) !== -1;
      const words = (s.words_by_speaker || {{}})[c.id] || 0;
      // The <sp>, not the word count, decides whether a character spoke.
      const speaks = (s.speakers || []).indexOf(c.id) !== -1;
      cellsData.push({{c: c, s: s, ri: ri, ci: ci, present: present,
                       words: words, speaks: speaks}});
    }});
  }});
  // Persistent column-stripe rect; positioned and shown on hover, hidden
  // otherwise.  Placed BEFORE the cells in document order so cell fills
  // (especially the transparent "absent" cells) sit on top of it without
  // colour collision.
  const colStripe = svg.append("rect")
    .attr("class", "col-stripe")
    .attr("y", TOP).attr("height", rows.length * cellH)
    .attr("width", cellW).attr("x", -9999);   // off-canvas until hover

  const cellSel = svg.append("g").selectAll("rect.cell").data(cellsData).enter().append("rect")
    .attr("class", d => "cell" +
        (d.s.id === STATE.segmentIdx ? " current-segment-strip" : ""))
    .attr("data-row", d => d.c.id)
    .attr("x", d => LEFT + d.ci * cellW)
    .attr("y", d => TOP + d.ri * cellH)
    .attr("width", cellW - 0.5)
    .attr("height", cellH - 0.5)
    .attr("fill", d => {{
      if (!d.present) return "transparent";
      if (d.words > 0) return colourSpeaking(redScale(d.words));
      if (d.speaks) return "url(#" + hatchId + ")";
      return colourSilent;
    }})
    .on("click", (_, d) => {{
      STATE.segmentIdx = d.s.id;
      _pendingTEISegment = d.s.id;   // also pre-select for the TEI source view
      updateSlider(); renderDynamicGraph(); renderInfo();
      renderHeatmap();  // redraw current-segment outline
    }})
    .on("mouseover", (_, d) => {{
      // Highlight three things together so the cell sits at a cross-hair:
      //   1. the hovered character's row label (accent bold);
      //   2. the row labels of *other* characters present in the same
      //      segment (muted bold) -- the stage-mate cast at this beat;
      //   3. a faint vertical column-stripe behind the segment's cells.
      const presentInCol = new Set(d.s.characters || []);
      svg.selectAll(".row-label")
        .classed("highlight", l => l && l.id === d.c.id)
        .classed("same-col",  l => l && l.id !== d.c.id && presentInCol.has(l.id));
      colStripe
        .attr("x", LEFT + d.ci * cellW)
        .attr("width", cellW - 0.5);
    }})
    .on("mouseout", () => {{
      svg.selectAll(".row-label")
        .classed("highlight", false).classed("same-col", false);
      colStripe.attr("x", -9999);
    }})
    .append("title").text(d => {{
      const status = !d.present ? "absent"
        : d.words > 0 ? (d.words + " word" + (d.words === 1 ? "" : "s"))
        : d.speaks ? "performs, text not transmitted"
        : "present (silent)";
      return d.c.name + "  -  segment " + d.s.id + " (" + d.s.label + ")  -  " + status;
    }});

  // -------------------------------------------------------------------
  // Cell-composition + would-be edges summary (rendered into #heatmap-stats).
  // Counts run over the same rows/cols that the heatmap shows, so the panel
  // follows the mute-mode radio and the partOf aggregation toggle.
  // Two readings of the same heatmap:
  //   - co-presence: a pair (a,b) forms an edge iff both are coloured in
  //     some column (red OR grey).  This is what stage co-presence and
  //     the play-level model do.
  //   - speaking cast: a pair (a,b) forms an edge iff both are RED in some
  //     column.  This is what the s-speaking network does.
  // -------------------------------------------------------------------
  let nRed = 0, nGray = 0;
  const presPairs = new Set();
  const coSpkPairs = new Set();
  const partOf = partOfMap();
  segs.forEach(s => {{
    const colored = [];   // chars present (red or grey) in this segment
    const speaking = [];  // chars red (words > 0) in this segment
    rows.forEach(c => {{
      const present = (s.characters || []).indexOf(c.id) !== -1;
      if (!present) return;
      const words = (s.words_by_speaker || {{}})[c.id] || 0;
      if (words > 0) {{ nRed++; colored.push(c.id); speaking.push(c.id); }}
      else {{ nGray++; colored.push(c.id); }}
    }});
    for (let i = 0; i < colored.length; i++) {{
      for (let j = i + 1; j < colored.length; j++) {{
        const a = colored[i], b = colored[j];
        if (oneBody(partOf, a, b)) continue;
        presPairs.add(a < b ? a + "|" + b : b + "|" + a);
      }}
    }}
    for (let i = 0; i < speaking.length; i++) {{
      for (let j = i + 1; j < speaking.length; j++) {{
        const a = speaking[i], b = speaking[j];
        if (oneBody(partOf, a, b)) continue;
        coSpkPairs.add(a < b ? a + "|" + b : b + "|" + a);
      }}
    }}
  }});
  const nTotal = rows.length * segs.length;
  const nEmpty = nTotal - nRed - nGray;
  const nNodes = rows.length;
  const ePres = presPairs.size, eSpk = coSpkPairs.size;
  const maxE = nNodes < 2 ? 0 : nNodes * (nNodes - 1) / 2;
  const fmt = (n, d = 0) => n.toLocaleString("el-GR", {{ minimumFractionDigits: d, maximumFractionDigits: d }});
  const pct = (x, total) => total > 0
      ? fmt(100 * x / total, 1) + " %"
      : "\\u2014";
  const ratio = nRed > 0 ? fmt(nGray / nRed, 2) : "\\u2014";
  const densP = maxE > 0 ? fmt(ePres / maxE, 3) : "\\u2014";
  const densS = maxE > 0 ? fmt(eSpk / maxE, 3) : "\\u2014";
  const kP = nNodes > 0 ? fmt(2 * ePres / nNodes, 2) : "\\u2014";
  const kS = nNodes > 0 ? fmt(2 * eSpk / nNodes, 2) : "\\u2014";
  const statsEl = document.getElementById("heatmap-stats");
  if (statsEl) {{
    statsEl.innerHTML =
      '<div class="group">'
        + '<div class="group-title">Cell composition (' + fmt(nTotal) + ' cells &middot; '
            + fmt(nNodes) + ' &times; ' + fmt(segs.length) + ')</div>'
        + '<div class="row"><span class="key"><span class="swatch" style="background:#a50f15"></span>speaking (red)</span>'
            + '<span class="val">' + fmt(nRed) + '  (' + pct(nRed, nTotal) + ')</span></div>'
        + '<div class="row"><span class="key"><span class="swatch" style="background:#bbbbbb"></span>silent presence (grey)</span>'
            + '<span class="val">' + fmt(nGray) + '  (' + pct(nGray, nTotal) + ')</span></div>'
        + '<div class="row"><span class="key"><span class="swatch" style="background:transparent"></span>absent (empty)</span>'
            + '<span class="val">' + fmt(nEmpty) + '  (' + pct(nEmpty, nTotal) + ')</span></div>'
        + '<div class="row summary"><span class="key">grey / red ratio</span>'
            + '<span class="val">' + ratio + '</span></div>'
      + '</div>'
      + '<div class="group">'
        + '<div class="group-title">Network readings (' + fmt(nNodes) + ' nodes)</div>'
        + '<div class="row"><span class="key">on-stage cast (any coloured pair)</span>'
            + '<span class="val">' + fmt(ePres) + ' edges</span></div>'
        + '<div class="row"><span class="key" style="padding-left:14px">density &middot; &lang;k&rang;</span>'
            + '<span class="val">' + densP + ' &middot; ' + kP + '</span></div>'
        + '<div class="row"><span class="key">speaking cast (red pair only)</span>'
            + '<span class="val">' + fmt(eSpk) + ' edges</span></div>'
        + '<div class="row"><span class="key" style="padding-left:14px">density &middot; &lang;k&rang;</span>'
            + '<span class="val">' + densS + ' &middot; ' + kS + '</span></div>'
      + '</div>';
  }}

  // X-axis (segment ids).  Tick every Nth segment so labels don't overlap;
  // we tag each segment with its original index up front so the filter
  // doesn't lose positional info.
  const tickStride = Math.max(1, Math.ceil(segs.length / 12));
  const tickItems = segs
    .map((s, i) => ({{seg: s, i: i}}))
    .filter(t => t.i % tickStride === 0);
  const xAxisG = svg.append("g")
    .attr("transform", `translate(0,${{TOP + rows.length * cellH + 4}})`);
  xAxisG.selectAll("text").data(tickItems).enter().append("text")
    .attr("class", "axis-label")
    .attr("x", t => LEFT + (t.i + 0.5) * cellW)
    .attr("y", 12).attr("text-anchor", "middle")
    .text(t => t.seg.id);
}}
function setupControls() {{
  // Fullscreen toggles for the static and dynamic graph panels.  Each
  // adds / removes a class on its panel, then re-renders the graph (so
  // the force simulation picks up the new container dimensions).  The
  // dynamic panel also re-renders its timeline.  Escape exits whichever
  // panel is currently fullscreen.
  function wireFullscreen(panelId, btnId, klass, onAfterToggle) {{
    const panel = document.getElementById(panelId);
    const btn   = document.getElementById(btnId);
    if (!panel || !btn) return null;
    function toggle(force) {{
      const next = force !== undefined
        ? force : !panel.classList.contains(klass);
      panel.classList.toggle(klass, next);
      btn.innerHTML = next ? "&#x274C; exit fullscreen" : "&#x26F6; fullscreen";
      requestAnimationFrame(onAfterToggle);
    }}
    btn.addEventListener("click", () => toggle());
    return toggle;
  }}
  const toggleDynFullscreen = wireFullscreen(
    "dynamic-panel", "dyn-fullscreen-btn", "dyn-fullscreen",
    () => {{ renderSegmentTimeline(); renderDynamicGraph(); }});
  const toggleStaticFullscreen = wireFullscreen(
    "static-panel", "static-fullscreen-btn", "static-fullscreen",
    () => {{ renderStaticGraph(); }});
  const toggleHeatmapFullscreen = wireFullscreen(
    "heatmap-panel", "heatmap-fullscreen-btn", "heatmap-fullscreen",
    () => {{ renderHeatmap(); }});
  const toggleSizeFullscreen = wireFullscreen(
    "size-panel", "size-fullscreen-btn", "size-fullscreen",
    () => {{ renderSizeChart(); }});
  const toggleWordFullscreen = wireFullscreen(
    "word-panel", "word-fullscreen-btn", "word-fullscreen",
    () => {{ renderWordChart(); }});
  const toggleBeatFullscreen = wireFullscreen(
    "beat-panel", "beat-fullscreen-btn", "beat-fullscreen",
    () => {{ renderBeatChart(); }});
  document.addEventListener("keydown", (e) => {{
    if (e.key !== "Escape") return;
    const dyn = document.getElementById("dynamic-panel");
    const sta = document.getElementById("static-panel");
    const heat = document.getElementById("heatmap-panel");
    const sz = document.getElementById("size-panel");
    const wd = document.getElementById("word-panel");
    const bt = document.getElementById("beat-panel");
    if (dyn && dyn.classList.contains("dyn-fullscreen")) toggleDynFullscreen(false);
    else if (sta && sta.classList.contains("static-fullscreen")) toggleStaticFullscreen(false);
    else if (heat && heat.classList.contains("heatmap-fullscreen")) toggleHeatmapFullscreen(false);
    else if (sz && sz.classList.contains("size-fullscreen")) toggleSizeFullscreen(false);
    else if (wd && wd.classList.contains("word-fullscreen")) toggleWordFullscreen(false);
    else if (bt && bt.classList.contains("beat-fullscreen")) toggleBeatFullscreen(false);
  }});

  // Heatmap row-order dropdown.
  const heatmapSortSel = document.getElementById("heatmap-sort");
  if (heatmapSortSel) {{
    heatmapSortSel.addEventListener("change", (e) => {{
      _heatmapSort = e.target.value;
      renderHeatmap();
    }});
  }}

  const slider = document.getElementById("seg-slider");
  slider.addEventListener("input", () => {{
    STATE.segmentIdx = +slider.value;
    renderDynamicGraph(); renderInfo();
  }});
  document.getElementById("seg-prev").addEventListener("click", () => {{
    const range = _segIdRange();
    STATE.segmentIdx = Math.max(range.min, STATE.segmentIdx - 1);
    updateSlider(); renderDynamicGraph(); renderInfo();
  }});
  document.getElementById("seg-next").addEventListener("click", () => {{
    const range = _segIdRange();
    STATE.segmentIdx = Math.min(range.max, Math.max(range.min - 1, STATE.segmentIdx) + 1);
    updateSlider(); renderDynamicGraph(); renderInfo();
  }});
  function startPlayback(btn) {{
    STATE.playing = true; btn.textContent = "pause";
    const tick = () => {{
      const range = _segIdRange();
      if (STATE.segmentIdx >= range.max) {{
        clearInterval(STATE.playTimer); STATE.playing = false; btn.textContent = "play"; return;
      }}
      STATE.segmentIdx = Math.max(range.min - 1, STATE.segmentIdx) + 1;
      updateSlider(); renderDynamicGraph(); renderInfo();
    }};
    STATE.playTimer = setInterval(tick, STATE.playSpeed);
  }}
  document.getElementById("seg-play").addEventListener("click", function() {{
    if (STATE.playing) {{
      clearInterval(STATE.playTimer); STATE.playing = false; this.textContent = "play";
    }} else {{
      startPlayback(this);
    }}
  }});
  const speed = document.getElementById("play-speed");
  const speedVal = document.getElementById("play-speed-v");
  function fmtSpeed(ms) {{ return (ms / 1000).toFixed(1) + "s"; }}
  speedVal.textContent = fmtSpeed(STATE.playSpeed);
  speed.value = STATE.playSpeed;
  speed.addEventListener("input", () => {{
    STATE.playSpeed = +speed.value;
    speedVal.textContent = fmtSpeed(STATE.playSpeed);
    if (STATE.playing) {{
      clearInterval(STATE.playTimer);
      startPlayback(document.getElementById("seg-play"));
    }}
  }});

  // Force-layout sliders update the live simulation in place.
  // Note: this does NOT queue an auto-fit on every input event -- only the
  // slider's `change` event (mouse release) does, to avoid the camera
  // re-fitting during continuous slider dragging.
  function applyForce(reheat=true) {{
    const sim = STATE.forceSim;
    if (!sim) return;
    const fp = STATE.forceParams;
    sim.force("charge").strength(-fp.repulsion);
    sim.force("link").distance(fp.link);
    sim.force("x").strength(fp.gravity);
    sim.force("y").strength(fp.gravity);
    if (reheat) sim.alpha(0.6).restart();
  }}
  function bindForce(id, key, parse, fmt) {{
    const inp = document.getElementById(id);
    const out = document.getElementById(id + "-v");
    inp.value = STATE.forceParams[key];
    out.textContent = fmt(STATE.forceParams[key]);
    // `input` fires continuously during drag -> live force update only.
    // No auto-fit is queued: the user controls framing via the Fit button.
    inp.addEventListener("input", () => {{
      STATE.forceParams[key] = parse(inp.value);
      out.textContent = fmt(STATE.forceParams[key]);
      applyForce(true);
    }});
  }}
  bindForce("f-repulsion", "repulsion", v => +v, v => "" + v);
  bindForce("f-link",      "link",      v => +v, v => "" + v);
  bindForce("f-gravity",   "gravity",   v => +v, v => (+v).toFixed(3));
  document.getElementById("f-reset").addEventListener("click", () => {{
    STATE.forceParams = Object.assign({{}}, FORCE_DEFAULTS);
    document.getElementById("f-repulsion").value = FORCE_DEFAULTS.repulsion;
    document.getElementById("f-repulsion-v").textContent = FORCE_DEFAULTS.repulsion;
    document.getElementById("f-link").value = FORCE_DEFAULTS.link;
    document.getElementById("f-link-v").textContent = FORCE_DEFAULTS.link;
    document.getElementById("f-gravity").value = FORCE_DEFAULTS.gravity;
    document.getElementById("f-gravity-v").textContent = FORCE_DEFAULTS.gravity.toFixed(3);
    applyForce(true);
  }});
  // Fit button: snap if the simulation has already settled, otherwise queue
  // so the fit fires once the new equilibrium is reached.
  document.getElementById("f-fit").addEventListener("click", () => {{
    if (STATE.forceSim && STATE.forceSim.alpha() > 0.05) {{
      STATE.pendingAutoFit = true;
    }} else {{
      autoFitZoom(true);
    }}
  }});

  // Three-state network-model radio.  Each radio in the fieldset shares
  // name="mute-mode"; the change event fires on the newly-selected one.
  document.querySelectorAll('input[name="mute-mode"]').forEach(r => {{
    r.addEventListener("change", (e) => {{
      if (!e.target.checked) return;
      STATE.muteMode = e.target.value;
      // The model switch can change the node set (p-speaking, s-speaking)
      // and the segment cast (s-speaking).  Invalidate cached layout and
      // reset the slider so the new graph renders cleanly.
      STATE.positions = null;
      STATE.segmentIdx = -1;
      renderActiveFilters();
      render();
    }});
  }});
  document.getElementById("show-labels").addEventListener("change", (e) => {{
    STATE.showLabels = e.target.checked;
    d3.selectAll("#static-graph .node text, #dynamic-graph .node text")
      .attr("display", STATE.showLabels ? null : "none");
  }});
  // X-axis mode toggle for the beat chart only.
  document.getElementById("chart-xmode").addEventListener("change", (e) => {{
    STATE.chartXMode = e.target.checked ? "word" : "segment";
    renderBeatChart();
  }});

  // One independent checkbox per partOf group declared on this play.
  // The slot is empty (and so the toolbar shows nothing extra) when the
  // play has no partOf relations.  Each toggle is checked individually;
  // any combination of groups produces a precomputed `variants[key]`
  // entry that the JS swaps in via currentSegData().
  const aggHost = document.getElementById("aggregate-toggles");
  for (const g of AGGREGATE_GROUPS) {{
    const id = "agg-group-" + g.replace(/[^a-zA-Z0-9_-]/g, "_");
    const label = document.createElement("label");
    label.innerHTML = '<input type="checkbox" id="' + id + '" data-group="' + g
      + '"> aggregate <i>partOf</i> &rarr; <code>' + g + '</code>';
    aggHost.appendChild(label);
    label.querySelector("input").addEventListener("change", (e) => {{
      const group = e.target.dataset.group;
      if (e.target.checked) STATE.aggregateGroups.add(group);
      else STATE.aggregateGroups.delete(group);
      // Aggregation changes the node set; cached layout positions and the
      // segment-slider index are no longer valid.  Reset both.
      STATE.positions = null;
      STATE.segmentIdx = -1;
      renderActiveFilters();
      render();
    }});
  }}
}}

// -------------------------------------------------------------------- render
function render() {{
  if (STATE.playing) {{
    clearInterval(STATE.playTimer); STATE.playing = false;
    document.getElementById("seg-play").textContent = "play";
  }}
  // Tab / mute toggle = full re-render: drop any node focus since the
  // focused character may no longer exist (mute filter) or moved to a
  // different segmentation's layout.
  STATE.focusNode = null;
  renderTabs();
  renderKPIs();
  renderStaticGraph();
  renderSizeChart();
  renderWordChart();
  renderBeatChart();
  renderCharTable();
  renderTGiniTable();
  renderSegTable();
  renderInfo();
  renderSegmentTimeline();
  renderHeatmap();
  // Dynamic graph re-renders via sim.on("end") inside renderStaticGraph;
  // no direct call needed here.
}}

// ----------------------------------------------------------- view tabs
// Top-level view switch: Analysis (default) ↔ TEI ↔ Methods.  Heavy
// content (KaTeX math, TEI source) is rendered on first reveal of its
// tab so hidden content doesn't add to initial-load latency.
let _mathRendered = false;
let _teiRendered = false;
// Segment id pre-selected by a click on the segments table.  Consumed
// (and cleared) the next time the TEI view's dropdown is populated.
let _pendingTEISegment = null;
// Remember the body scroll position of each view so that the user lands
// back where they were after a Analysis -> TEI -> Analysis round-trip.
const _viewScrollY = {{ analysis: 0, tei: 0, methods: 0 }};
function showView(name) {{
  // Capture where we are in the outgoing view BEFORE we hide it (after
  // `display: none` the browser may have already clamped scrollY).
  const cur = document.querySelector(".view-tab.active");
  if (cur) _viewScrollY[cur.dataset.view] = window.scrollY;

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
  if (name === "tei") {{
    if (!_teiRendered) {{ renderTEI(); _teiRendered = true; }}
    populateTEISegmentSelect();    // refresh on every reveal (segmentation may have changed)
  }}
  // Analysis returns to its remembered position; TEI / Methods snap to
  // the top so their toolbar / intro is visible.  applyTEISelection's
  // smooth scroll inside the .tei-source-wrap is unaffected (that's an
  // inner scroll, not the window's).
  if (name === "analysis") {{
    window.scrollTo(0, _viewScrollY.analysis || 0);
  }} else {{
    window.scrollTo(0, 0);
  }}
}}
document.querySelectorAll(".view-tab").forEach(b =>
  b.addEventListener("click", () => showView(b.dataset.view)));

// ----------------------------------------------------------- TEI view
function renderTEI() {{
  const src = DATA.tei_source || "";
  const container = document.getElementById("tei-content");
  container.innerHTML = "";
  if (!src) {{
    container.innerHTML = '<div class="tei-source-empty">No TEI source embedded.</div>';
    return;
  }}
  // Split into lines and build one DOM row per line with a number gutter.
  // We do this with a single innerHTML write to avoid layout thrash on
  // 3 000+-line plays.  Each line keeps a data-ln attribute for scrolling.
  const lines = src.split("\\n");
  const buf = [];
  const escapeHTML = s => s
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  for (let i = 0; i < lines.length; i++) {{
    const ln = i + 1;
    const text = lines[i].length ? lines[i] : "\\u00A0";  // non-breaking space for empty lines
    // Split into alternating runs of [text, tag, text, tag, ...] so we
    // can colour markup distinctly from the actual play text.  Index 0
    // is always text; odd indices are tags (or comments).
    const parts = text.split(/(<[^>]*>)/);
    const inner = parts.map((part, j) => {{
      const safe = escapeHTML(part);
      if (j % 2 === 0) return safe;             // text content
      let cls;
      if (part.startsWith("<!--")) cls = "xml-comment";
      else if (/^<\\/?move\\b/.test(part)) cls = "xml-move";
      else cls = "xml-tag";
      return '<span class="' + cls + '">' + safe + '</span>';
    }}).join("");
    buf.push('<div class="tei-line" data-ln="' + ln + '">'
           + '<span class="ln">' + ln + '</span>'
           + '<span class="content">' + inner + '</span></div>');
  }}
  container.innerHTML = buf.join("");
}}

function populateTEISegmentSelect() {{
  const sel = document.getElementById("tei-segment-select");
  // A pending pre-selection from a segments-table click takes precedence;
  // otherwise preserve whatever the dropdown currently shows.
  let cur;
  if (_pendingTEISegment != null) {{
    cur = String(_pendingTEISegment);
    _pendingTEISegment = null;
  }} else {{
    cur = sel.value;
  }}
  // Drop everything except the "whole play" option.
  while (sel.options.length > 1) sel.remove(1);
  const segs = currentSegData().segments;
  for (const s of segs) {{
    const opt = document.createElement("option");
    opt.value = String(s.id);
    const range = (s.tei_start && s.tei_end)
      ? "  (lines " + s.tei_start + "-" + s.tei_end + ")" : "";
    opt.textContent = "segment " + s.id + " - " + s.label + range;
    sel.appendChild(opt);
  }}
  // Restore previous selection if still valid; otherwise reset to whole play.
  const restorable = Array.from(sel.options).some(o => o.value === cur);
  sel.value = restorable ? cur : "-1";
  applyTEISelection();
}}

function applyTEISelection() {{
  const sel = document.getElementById("tei-segment-select");
  const info = document.getElementById("tei-range-info");
  // Clear previous highlights.
  document.querySelectorAll(".tei-line.highlight").forEach(el => {{
    el.classList.remove("highlight"); el.classList.remove("first");
  }});
  const v = sel.value;
  if (v === "-1") {{
    info.textContent = "";
    document.getElementById("tei-source-wrap").scrollTop = 0;
    return;
  }}
  const segId = parseInt(v, 10);
  const seg = currentSegData().segments.find(s => s.id === segId);
  if (!seg || seg.tei_start == null) {{
    info.textContent = "(no source-line range recorded)";
    return;
  }}
  const a = seg.tei_start, b = seg.tei_end || seg.tei_start;
  info.textContent = "lines " + a + "-" + b + " (" + (b - a + 1) + ")";
  // Highlight each line in the range, mark the first for the left accent.
  for (let ln = a; ln <= b; ln++) {{
    const el = document.querySelector('.tei-line[data-ln="' + ln + '"]');
    if (el) {{
      el.classList.add("highlight");
      if (ln === a) el.classList.add("first");
    }}
  }}
  const first = document.querySelector('.tei-line[data-ln="' + a + '"]');
  if (first) {{
    // Scroll only the inner .tei-source-wrap, not the page; otherwise
    // scrollIntoView's window-scroll would push the sticky toolbar (and
    // its "jump to" dropdown) above the topbar and out of sight.
    const wrap = document.getElementById("tei-source-wrap");
    const wrapRect = wrap.getBoundingClientRect();
    const lineRect = first.getBoundingClientRect();
    const target = wrap.scrollTop + (lineRect.top - wrapRect.top)
      - (wrap.clientHeight / 2 - lineRect.height / 2);
    wrap.scrollTo({{top: target, behavior: "smooth"}});
  }}
}}

document.getElementById("tei-segment-select")
  .addEventListener("change", applyTEISelection);

setupControls();
renderActiveFilters();
// Populate the Methods tab's "partOf relations in this play" line.  No
// effect for the corpus dashboard (which uses the same methods panel but
// no DATA.play); for per-play, it shows e.g. "chorosGeronton, chorosGynaikon
// partOf choros".
(function fillAggregationRelations() {{
  const slot = document.getElementById("aggregation-relations");
  if (!slot) return;
  const rels = (DATA.play && DATA.play.relations) || [];
  if (!rels.length) {{ slot.textContent = "(none declared)"; return; }}
  // Group by passive (the parent), list actives under each.
  const byParent = {{}};
  for (const r of rels) {{
    (byParent[r.passive] = byParent[r.passive] || []).push(r.active);
  }}
  slot.innerHTML = Object.entries(byParent).map(([p, parts]) =>
    "<code>" + parts.join(", ") + "</code> <i>partOf</i> <code>" + p + "</code>"
  ).join("; ");
}})();
render();

// Measure the sticky topbar so the segmentation-tabs row can pin
// directly below it (see the `.tabs` rule with top: var(--topbar-h)).
function updateTopbarHeight() {{
  const tb = document.querySelector('.topbar');
  if (tb) {{
    document.documentElement.style.setProperty('--topbar-h', tb.offsetHeight + 'px');
  }}
}}
updateTopbarHeight();
window.addEventListener('resize', updateTopbarHeight);
</script>
<!--FIGURE_EXPORT_JS-->
</body>
</html>
"""


def write_dashboard(
    play: PlayData,
    results: Dict[str, Dict],
    out_path: Path,
) -> Path:
    """Render the dashboard HTML for one play and write it to disk."""
    payload = build_dashboard_payload(play, results)
    title = (play.title_en or play.title_grc or play.play_id or "Untitled").strip()
    # Author and Greek title come from the TEI header: escaped, like the
    # title, before they reach the page.  The separators are ours.
    subtitle_parts = []
    if play.author:
        subtitle_parts.append(_html_escape(play.author))
    if play.title_grc and play.title_grc != title:
        subtitle_parts.append(_html_escape(play.title_grc))
    subtitle_parts.append("segmentations: " + ", ".join(results.keys()))
    subtitle = " &middot; ".join(subtitle_parts)
    data_json = _json_for_script(payload)
    html = _TEMPLATE.format(
        title=_html_escape(title),
        subtitle=subtitle,
        data_json=data_json,
    )
    # Inject the Methods tab's HTML via plain replace so KaTeX's literal
    # `{` and `}` don't have to be escaped for `str.format`.  The figure
    # exporter and the inlined d3/KaTeX ride the same mechanism, for the
    # same reason; the libraries go in last, so no later replace scans them.
    html = html.replace("<!--METHODS_HTML-->", methods_panel_html())
    html = html.replace(CSS_PLACEHOLDER, figure_export_css())
    html = html.replace(JS_PLACEHOLDER, figure_export_js())
    html = html.replace(VENDOR_PLACEHOLDER, vendor_assets_html())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


def _json_for_script(payload) -> str:
    """Serialise `payload` for embedding in an inline <script>.

    JSON quoting does not protect the script element's HTML boundary.  The
    parser scans for the literal characters `</script` before any JavaScript
    runs, so a closing tag anywhere in the data ends the element there and
    turns the rest of the dashboard's code into page text.  The data is not
    hypothetical: the TEI tab carries the whole source file, comments
    included, and a comment may legally hold one.

    Escaping the three HTML-significant characters as \\uXXXX leaves the JSON
    equal as a value and inert as markup.  U+2028 and U+2029 go with them:
    legal inside a JSON string, and line terminators in JavaScript before
    ES2019.
    """
    out = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return (out.replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("&", "\\u0026")
               .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


__all__ = ["write_dashboard", "build_dashboard_payload"]
