"""SkeneGraph-Net -- DraCor-style network analysis for TEI/XML-encoded drama.

Usage
-----
    python app.py analyze PLAY.xml [--seg sd|div2|div3|all] [--no-mutes]
                                   [--out OUTDIR] [--weight segments|verses|words]

    python app.py corpus  DIR/ [--seg ...] [--no-mutes] [--out ...]

Output
------
    OUTDIR/<play_id>/<seg>/{metrics.json, characters.csv, segments.csv,
                            networkdata.csv, networkdata.gexf, networkdata.graphml,
                            dynamic.gexf, dynamic_metrics.csv}

Departures from DraCor (https://dracor.org/doc/api):
    1. Three segmentation methods: stage directions (sd), div3 (scene),
       div2 (act).  DraCor uses one fixed scene-based segmentation.
    2. Three network models over two orthogonal axes -- cast filter
       (play-level mutes in/out, --no-mutes) and edge rule (co-presence /
       co-speech): "stage", "dialogic", "cospeech".  DraCor offers a single
       speakers-only co-occurrence model.
    3. Collective figures (the chorus and its subdivisions) are optionally
       aggregated to a single node or kept distinct.  Not modelled by DraCor.
    4. A dynamic per-segment graph is produced alongside the static aggregate,
       packaged as a Gephi-renderable GEXF with <spells>.  DraCor publishes
       the static aggregate only.
"""

from __future__ import annotations

__version__ = "1.0.0"

import argparse
import logging
import sys
from itertools import chain, combinations
from pathlib import Path
from typing import List, Optional

# Local modules (run from the SkeneGraph-Net directory).
from parser import parse_play
from segmentation import SEGMENTERS, fold_segments
from network import (
    build_static, build_dynamic_spell_graph, build_dynamic, _kept_characters,
)
from metrics import (
    compute_metrics, compute_dynamic_metrics,
    compute_demographics, compute_speech_distribution, compute_segment_indices,
    compute_temporal_gini,
)
from aggregation import aggregate_play
from exporter import write_outputs, _safe_dirname
from dashboard import write_dashboard
from corpus_dashboard import extract_play_summary, write_corpus_dashboard


log = logging.getLogger("SkeneGraph-Net")


def analyze_one(
    xml_path: Path,
    seg_modes: List[str],
    out_root: Path,
    include_mutes: bool,
    edge_weight: str,
    make_dashboard: bool = True,
) -> Optional[dict]:
    """Analyze one play.  Returns a compact summary dict that the corpus
    runner uses to populate the corpus dashboard (or None on skip)."""
    log.info("Parsing %s", xml_path.name)
    play = parse_play(xml_path)
    log.info(
        "  characters=%d  moves=%d  speeches=%d  div2=%d  div3=%d  relations=%d",
        len(play.characters), len(play.moves), len(play.speeches),
        len(play.div2s), len(play.div3s), len(play.relations),
    )

    play_dir = out_root / _safe_dirname(play.play_id or xml_path.stem)
    play_dir.mkdir(parents=True, exist_ok=True)

    # Enumerate every non-empty subset of the play's partOf groups.  For
    # each subset, the dashboard precomputes an aggregated variant; the
    # JS toggles pick which one to show.  With 1 group (current corpus),
    # this is a single extra variant per segmentation; with N groups,
    # 2**N - 1.  Costs only matter for N >= 5, which the corpus doesn't have.
    group_ids = sorted({r.passive for r in play.relations if r.name == "partOf"
                        and r.passive in play.characters})

    def _nonempty_subsets(items):
        return chain.from_iterable(combinations(items, r) for r in range(1, len(items) + 1))

    group_subsets = [tuple(sub) for sub in _nonempty_subsets(group_ids)]

    dashboard_payload: dict = {}

    # Three orthogonal mute modes (replace the older binary in/out).  The
    # (include_mutes, edge_rule) axes underneath are independent; this
    # table exposes all three meaningful combinations.  The fourth
    # combination (include_mutes=True, edge_rule="co_speech") is
    # incoherent for our purposes (mute characters become isolated
    # nodes) and is not generated.
    MUTE_MODE_PARAMS = {
        "stage":    (True,  "presence"),   # all on-stage characters; co-presence edges
        "dialogic": (False, "presence"),   # speakers-only cast; co-presence edges
        "cospeech": (False, "co_speech"),  # speakers-only cast; per-segment co-speech edges
    }

    def _run_pipeline(source_play, mode: str, mute_mode: str):
        """Run segmenter + graph builders + metric pipeline for one play view.

        `mute_mode` is one of:
          * "stage"    — stage co-presence (all on-stage characters as
            nodes; edges from per-segment co-presence)
          * "dialogic" — dialogic cast at play level (drop play-level
            mute characters from the node set; edges still from
            per-segment co-presence among the kept cast)
          * "cospeech" — dialogic cast at segment level (drop play-level
            mutes; edges only when characters share a segment as
            speakers).
        """
        seg_fn = SEGMENTERS[mode]
        segments = seg_fn(source_play)
        if not segments:
            return None
        if mute_mode not in MUTE_MODE_PARAMS:
            raise ValueError(f"Unknown mute_mode: {mute_mode}")
        inc_mutes, e_rule = MUTE_MODE_PARAMS[mute_mode]
        # Model-specific spine (sd + mutes-out models only): fold boundaries
        # the active model cannot see -- e.g. a mute's entrance under
        # dialogic / cospeech, where the mute is not a node.  The static
        # graph is invariant (the merged segment re-emits the same clique),
        # so order, density and average degree are unchanged; num_segments,
        # DCR and the per-segment series then reflect the model rather than
        # the raw stage spine.  The stage model (mutes-in) is left as the
        # faithful annotated spine -- it keeps every move as a boundary, so
        # the only thing a fold would remove there is a redundant duplicate-
        # cast annotation, which is better surfaced than silently merged
        # (and stage is the canonical view for file exports).  div2 / div3
        # are textual divisions, not cast-triggered boundaries, so they keep
        # their fixed, model-independent spine.
        if mode == "sd" and not inc_mutes:
            kept = _kept_characters(source_play.characters, segments,
                                    inc_mutes, e_rule)

            def _model_cast(seg, _kept=kept):
                # The fold is meant to remove sd-segment boundaries that
                # exist only because of a mute move (a boundary that does
                # not change the model-relevant cast).  The model-relevant
                # cast under both "dialogic" (presence edges, no mutes) and
                # "cospeech" (co-speech edges, no mutes) is the same set:
                # the play-level speakers on stage in this segment.  Using
                # seg.speakers under cospeech instead would make the spine
                # speaker-turn-driven rather than stage-direction-driven,
                # blurring the orthogonality between the segmentation axis
                # (sd / div2 / div3) and the network model axis -- and
                # producing extra segment boundaries that do not correspond
                # to any stage event.  The fold leaves network metrics
                # unchanged: edges in a merged segment are the union of
                # edges in its sub-segments under co_speech (every cross-
                # speaker pair the merge would introduce is already formed
                # in some other segment of the play).
                return seg.characters_present & _kept

            segments = fold_segments(segments, _model_cast)
        static_g = build_static(segments, source_play.characters,
                                include_mutes=inc_mutes,
                                edge_weight=edge_weight,
                                edge_rule=e_rule)
        dyn_spell = build_dynamic_spell_graph(segments, source_play.characters,
                                              include_mutes=inc_mutes,
                                              edge_rule=e_rule)
        dyn_per_segment = build_dynamic(segments, source_play.characters,
                                        include_mutes=inc_mutes,
                                        edge_rule=e_rule)
        metrics = compute_metrics(static_g,
                                  play_id=source_play.play_id,
                                  play_name=source_play.title_en or source_play.title_grc)
        metrics["segmentation"] = mode
        metrics["mute_mode"] = mute_mode
        metrics["edge_rule"] = e_rule
        metrics["num_segments"] = len(segments)
        metrics["edge_weight"] = edge_weight
        metrics["demographics"] = compute_demographics(source_play, include_mutes=inc_mutes)
        metrics["speech_distribution"] = compute_speech_distribution(source_play)
        metrics["segment_indices"] = compute_segment_indices(segments)
        # Per-character temporal Gini.  Merged into the nodes list so
        # the per-play dashboard can render a "speech concentration"
        # table inside Plot Dynamics; surfaced at the play level (top
        # speaker only) so the corpus dashboard can show it as a
        # column without re-walking segments.  See methods §5 for the
        # operationalisation choice (all active segments, zero-padded).
        tgini = compute_temporal_gini(segments)
        top_id = metrics["speech_distribution"].get("top_speaker_id")
        metrics["speech_distribution"]["top_speaker_temporal_gini"] = (
            tgini[top_id]["temporal_gini"] if top_id and top_id in tgini else None
        )
        if tgini:
            # Same for every character (it's the active span).
            metrics["speech_distribution"]["n_active_segments"] = next(
                iter(tgini.values()))["n_active_segments"]
        for node in metrics["nodes"]:
            entry = tgini.get(node["id"])
            if entry:
                node["temporal_gini"]     = entry["temporal_gini"]
                node["total_verses"]      = entry["total_verses"]
                node["speaking_segments"] = entry["speaking_segments"]
        dynamic_rows = compute_dynamic_metrics(dyn_per_segment)
        return {
            "static_graph": static_g,
            "dyn_spell": dyn_spell,
            "segments": segments,
            "metrics": metrics,
            "dynamic_rows": dynamic_rows,
        }

    for mode in seg_modes:
        # The stage mode (case 1, presence-based, all on-stage characters
        # as nodes) is the canonical view used for file exports.  The
        # other two modes (dialogic at play level, dialogic at segment
        # level / co-speech) are dashboard-only and live in `variants`.
        raw_stage    = _run_pipeline(play, mode, mute_mode="stage")
        if raw_stage is None:
            log.warning("  [%s] no segments produced (skipped)", mode)
            continue
        raw_dialogic = _run_pipeline(play, mode, mute_mode="dialogic")
        raw_cospeech = _run_pipeline(play, mode, mute_mode="cospeech")

        seg_dir = play_dir / mode
        paths = write_outputs(
            play=play,
            segments=raw_stage["segments"],
            static_graph=raw_stage["static_graph"],
            dynamic_spell_graph=raw_stage["dyn_spell"],
            metrics=raw_stage["metrics"],
            dynamic_rows=raw_stage["dynamic_rows"],
            out_dir=seg_dir,
        )
        log.info("  [%s] stage     %d segments  size=%d  edges=%d  density=%.4f",
                 mode, len(raw_stage["segments"]),
                 raw_stage["metrics"]["size"], raw_stage["metrics"]["numEdges"],
                 raw_stage["metrics"]["density"])
        if raw_dialogic is not None:
            log.info("  [%s] dialogic                  size=%d  edges=%d  density=%.4f",
                     mode,
                     raw_dialogic["metrics"]["size"], raw_dialogic["metrics"]["numEdges"],
                     raw_dialogic["metrics"]["density"])
        if raw_cospeech is not None:
            log.info("  [%s] cospeech                  size=%d  edges=%d  density=%.4f",
                     mode,
                     raw_cospeech["metrics"]["size"], raw_cospeech["metrics"]["numEdges"],
                     raw_cospeech["metrics"]["density"])
        for name, p in paths.items():
            log.info("    -> %s", p)

        # Variants: one per (mute_mode, group_subset) pair.  Empty subset
        # with mute_mode="stage" is the top-level (default) view and is
        # NOT added to variants -- the dashboard reads it from r directly.
        variants: dict = {}
        if raw_dialogic is not None:
            variants["dialogic:"] = {
                "static_graph": raw_dialogic["static_graph"],
                "segments":     raw_dialogic["segments"],
                "metrics":      raw_dialogic["metrics"],
                "dynamic_rows": raw_dialogic["dynamic_rows"],
                "play":         play,
            }
        if raw_cospeech is not None:
            variants["cospeech:"] = {
                "static_graph": raw_cospeech["static_graph"],
                "segments":     raw_cospeech["segments"],
                "metrics":      raw_cospeech["metrics"],
                "dynamic_rows": raw_cospeech["dynamic_rows"],
                "play":         play,
            }
        for subset in group_subsets:
            play_v = aggregate_play(play, groups=set(subset))
            if play_v is play:
                continue
            key_g = ",".join(sorted(subset))
            for mute_mode in ("stage", "dialogic", "cospeech"):
                agg = _run_pipeline(play_v, mode, mute_mode=mute_mode)
                if agg is None:
                    continue
                variants[f"{mute_mode}:{key_g}"] = {
                    "static_graph": agg["static_graph"],
                    "segments":     agg["segments"],
                    "metrics":      agg["metrics"],
                    "dynamic_rows": agg["dynamic_rows"],
                    "play":         play_v,
                }
                log.info("    [%s/agg %s/%s] size=%d  edges=%d  density=%.4f",
                         mode, key_g, mute_mode,
                         agg["metrics"]["size"], agg["metrics"]["numEdges"],
                         agg["metrics"]["density"])

        dashboard_payload[mode] = {
            "static_graph": raw_stage["static_graph"],
            "segments":     raw_stage["segments"],
            "metrics":      raw_stage["metrics"],
            "dynamic_rows": raw_stage["dynamic_rows"],
            "variants":     variants,
        }

    if make_dashboard and dashboard_payload:
        dash_path = play_dir / "dashboard.html"
        write_dashboard(play, dashboard_payload, dash_path)
        log.info("  dashboard -> %s", dash_path)

    if not dashboard_payload:
        return None
    # Compact summary for the corpus dashboard.  href is relative to the
    # corpus dashboard which lives at out_root / corpus_dashboard.html, so
    # we point at `<play_dir>/dashboard.html`.
    href = f"{play_dir.name}/dashboard.html"
    return extract_play_summary(play, dashboard_payload, href)


def cmd_analyze(args: argparse.Namespace) -> int:
    seg_modes = (["sd", "div2", "div3"] if args.seg == "all" else [args.seg])
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    analyze_one(
        xml_path=Path(args.file),
        seg_modes=seg_modes,
        out_root=out_root,
        include_mutes=not args.no_mutes,
        edge_weight=args.weight,
        make_dashboard=not args.no_dashboard,
    )
    return 0


def _resolve_corpus_paths(paths: List[str], pattern: str) -> List[Path]:
    """Expand the `corpus` subcommand's positional paths into a flat,
    deduplicated, sorted list of XML files.

    Each entry in `paths` is treated as one of:
      * a directory  -> globbed with `pattern` (default *.xml)
      * a file       -> kept as-is (whatever its extension)
      * non-existent -> logged as a warning and skipped
    The same file passed twice (e.g. once explicitly and once via its
    containing directory) is deduplicated to its resolved absolute path,
    so that running `corpus comedy/ comedy/Ar-07-Lys.xml` does not
    double-analyze Lysistrata.  The final list is sorted lexicographically
    for stable output ordering across re-runs.
    """
    seen: set = set()
    out: List[Path] = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            log.warning("Path does not exist, skipping: %s", raw)
            continue
        if p.is_dir():
            matched = list(p.glob(pattern))
            if not matched:
                log.warning("No files matching %s in %s", pattern, p)
                continue
            for f in matched:
                key = f.resolve()
                if key in seen:
                    continue
                seen.add(key)
                out.append(f)
        elif p.is_file():
            key = p.resolve()
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        else:
            log.warning("Path is neither file nor directory, skipping: %s", raw)
    out.sort()
    return out


def _default_corpus_name(paths: List[str], n_plays: int) -> str:
    """Pick a sensible default corpus title when --name is not given.

    Single directory path -> its basename (matches the pre-multi-path
    behaviour, so single-directory invocations look identical to before).
    Any other shape -> a generic '<n> plays' label, signalling clearly
    that this is an ad-hoc corpus.  --name overrides both.
    """
    if len(paths) == 1:
        p = Path(paths[0])
        if p.is_dir():
            return p.name or "Corpus"
    return f"Custom corpus ({n_plays} plays)"


def cmd_corpus(args: argparse.Namespace) -> int:
    seg_modes = (["sd", "div2", "div3"] if args.seg == "all" else [args.seg])
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    files = _resolve_corpus_paths(args.paths, args.pattern)
    if not files:
        log.error("No XML files resolved from the given paths.")
        return 1
    if len(args.paths) == 1:
        log.info("Found %d plays in %s", len(files), args.paths[0])
    else:
        log.info("Found %d plays across %d paths", len(files), len(args.paths))

    summaries: List[dict] = []
    failures: List[str] = []
    for f in files:
        try:
            s = analyze_one(
                xml_path=f,
                seg_modes=seg_modes,
                out_root=out_root,
                include_mutes=not args.no_mutes,
                edge_weight=args.weight,
                make_dashboard=not args.no_dashboard,
            )
            if s is not None:
                summaries.append(s)
        except Exception as exc:
            log.exception("Failed on %s: %s", f.name, exc)
            failures.append(f.name)
    if failures:
        log.warning("Failed plays: %s", ", ".join(failures))

    if summaries and not args.no_dashboard:
        authors = sorted({s["author"] for s in summaries if s.get("author")})
        name = args.name or _default_corpus_name(args.paths, len(summaries))
        corpus_data = {
            "name": name,
            "plays": summaries,
            "authors": authors,
        }
        dash_path = out_root / "corpus_dashboard.html"
        write_corpus_dashboard(corpus_data, dash_path)
        log.info("Corpus dashboard -> %s", dash_path)

    return 0 if not failures else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="SkeneGraph-Net",
        description="DraCor-style network analysis for TEI/XML-encoded drama "
                    "(mutes, three segmenters, dynamic graphs).",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version",
                   version=f"SkeneGraph-Net {__version__}")

    # Subcommand is optional: when omitted, the interactive prompt fires
    # (see `run_interactive`).  When given, the subcommand drives the
    # pipeline directly via argparse defaults.
    sub = p.add_subparsers(dest="cmd", required=False)

    a = sub.add_parser("analyze", help="Analyze one play")
    a.add_argument("file", help="Path to TEI XML file")
    a.add_argument("--seg", choices=["sd", "div2", "div3", "all"], default="all",
                   help="Segmentation method (default: all three)")
    a.add_argument("--no-mutes", action="store_true",
                   help="Exclude mute characters from the network")
    a.add_argument("--weight", choices=["segments", "verses", "words"],
                   default="segments",
                   help="Edge weight scheme for the static graph (default: segments, DraCor-compatible)")
    a.add_argument("--out", default="output", help="Output root directory")
    a.add_argument("--no-dashboard", action="store_true",
                   help="Skip the HTML dashboard")
    a.set_defaults(func=cmd_analyze)

    c = sub.add_parser(
        "corpus",
        help=("Analyze a corpus assembled from one or more paths (directories "
              "and/or individual TEI XML files)."),
        description=(
            "Each positional argument is either a directory (glommed with "
            "--pattern, default *.xml) or a single TEI XML file.  All "
            "resolved files are pooled into a single corpus; the corpus "
            "dashboard treats them as one set.  Examples:\n"
            "  corpus comedy/                          # one directory\n"
            "  corpus comedy/ tragedy/                 # two directories\n"
            "  corpus comedy/Ar-07-Lys.xml comedy/Ar-01-Ach.xml comedy/Ar-03-Nub.xml\n"
            "  corpus comedy/ tragedy/Soph-Ant.xml --name 'Mixed' --out output/mixed"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    c.add_argument("paths", nargs="+",
                   help="One or more paths.  Each may be a directory of TEI XML "
                        "files or a single XML file.")
    c.add_argument("--pattern", default="*.xml",
                   help="Glob pattern applied to each directory path (default: *.xml).")
    c.add_argument("--name", default=None,
                   help="Corpus title shown on the dashboard.  Defaults to the "
                        "directory name when a single directory is given; "
                        "otherwise to 'Custom corpus (N plays)'.")
    c.add_argument("--seg", choices=["sd", "div2", "div3", "all"], default="all")
    c.add_argument("--no-mutes", action="store_true")
    c.add_argument("--weight", choices=["segments", "verses", "words"], default="segments")
    c.add_argument("--out", default="output")
    c.add_argument("--no-dashboard", action="store_true",
                   help="Skip the HTML dashboard for each play")
    c.set_defaults(func=cmd_corpus)

    return p


def _interactive_namespace(command: str, kw: dict) -> argparse.Namespace:
    """Build the argparse namespace the cmd_* handlers expect, using the
    same defaults as the CLI subparsers above.

    The interactive corpus prompt now collects a list of paths
    (`kw["paths"]`) and an optional corpus title (`kw["name"]`),
    matching the multi-path CLI shape one-for-one.
    """
    base = {
        "verbose": False,
        "seg": "all",
        "no_mutes": False,
        "weight": "segments",
        "no_dashboard": False,
    }
    if command == "analyze":
        base.update({"file": kw["file"], "out": kw["out"], "func": cmd_analyze})
    else:
        base.update({
            "paths":    kw["paths"],
            "name":     kw.get("name"),
            "out":      kw["out"],
            "pattern":  "*.xml",
            "func":     cmd_corpus,
        })
    return argparse.Namespace(**base)


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # No subcommand on the command line -> launch the interactive prompt.
    if getattr(args, "cmd", None) is None:
        from interactive import run_interactive
        result = run_interactive()
        if result is None:
            return 0
        command, kw = result
        args = _interactive_namespace(command, kw)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
