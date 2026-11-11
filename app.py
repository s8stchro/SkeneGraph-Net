"""SkeneGraph-Net -- DraCor-style network analysis for TEI/XML-encoded drama.

Usage
-----
    python app.py analyze PLAY.xml [--seg sd|large-seq|middle-seq|all]
                                   [--export-model full|p-speaking|s-speaking]
                                   [--out OUTDIR] [--weight segments|words]

    python app.py corpus  DIR/ [--seg ...] [--export-model ...] [--out ...]

Output
------
    OUTDIR/<title>/<seg>/{metrics.json, characters.csv, segments.csv,
                          networkdata.csv, networkdata.gexf, networkdata.graphml,
                          dynamic.gexf, dynamic_metrics.csv}

    <title> is the sanitised English title, and OUTDIR/<title>/source.json
    records which file it was built from and the play's id, so that two plays
    whose titles sanitise alike get a directory each (see
    exporter.allocate_play_dir).  The id -- the TLG work number where the
    header gives one -- is what identifies the play in metrics.json.

Departures from DraCor (https://dracor.org/doc/api):
    1. Three segmentation methods: stage directions (sd), middle-seq (scene),
       large-seq (act).  DraCor uses one fixed scene-based segmentation.
    2. Three network models over two orthogonal axes -- node set (play-level
       mutes in/out) and segment cast (what makes a character count as being
       in a segment: standing on stage, or speaking there): "full",
       "p-speaking", "s-speaking".  All three are undirected co-occurrence
       networks -- an edge says the pair shared a segment, never that one
       addressed the other; @toWhom is not read here (it belongs to the
       directed-perception app).  The dashboard carries all three and
       switches between them; --export-model picks which one is written to
       files.  DraCor offers a single speakers-only co-occurrence model.
    3. Collective figures (the chorus and its subdivisions) are optionally
       aggregated to a single node or kept distinct.  Not modelled by DraCor.
    4. A dynamic per-segment graph is produced alongside the static aggregate,
       packaged as a Gephi-renderable GEXF with <spells>.  DraCor publishes
       the static aggregate only.
"""

from __future__ import annotations

# Re-exported so `from app import __version__` keeps working; the single
# definition lives in `version.py`, which the dashboards can import without
# the circular dependency that importing `app` would create.
from version import __version__

import argparse
import logging
import sys
from itertools import chain, combinations
from pathlib import Path
from typing import Dict, List, Optional

# Local modules (run from the SkeneGraph-Net directory).
from parser import parse_play
from segmentation import SEGMENTERS, fold_for_model
from network import (
    build_static, build_dynamic_spell_graph, build_dynamic, _kept_characters,
)
from metrics import (
    compute_metrics, compute_dynamic_metrics,
    compute_demographics, compute_speech_distribution, compute_segment_indices,
    compute_temporal_gini,
)
from aggregation import aggregatable_groups, aggregate_play, absorb_silent_parts
from exporter import allocate_play_dir, write_outputs
from dashboard import write_dashboard
from corpus_dashboard import extract_play_summary, write_corpus_dashboard


log = logging.getLogger("SkeneGraph-Net")


# The three network models, named alike on the command line, in the exported
# metrics and in the dashboard.  All three are undirected co-occurrence
# networks; they differ in the node set and in what makes a character count
# as being in a segment (see MUTE_MODE_PARAMS inside analyze_one):
#
#   full        nodes: whole cast        | in segment: on stage
#   p-speaking  nodes: play speakers     | in segment: on stage
#   s-speaking  nodes: segment speakers  | in segment: speaking
#
# The dashboard carries all three and switches between them at viewing time;
# the file exports can hold only one, chosen by --export-model.
EXPORT_MODELS = ("full", "p-speaking", "s-speaking")
DEFAULT_EXPORT_MODEL = "full"


def analyze_one(
    xml_path: Path,
    seg_modes: List[str],
    out_root: Path,
    export_model: str,
    edge_weight: str,
    make_dashboard: bool = True,
    claimed_dirs: Optional[Dict[str, str]] = None,
) -> Optional[dict]:
    """Analyze one play.  Returns a compact summary dict that the corpus
    runner uses to populate the corpus dashboard (or None on skip).

    `claimed_dirs` maps the output directories taken so far in this run to
    the source that took each, so that a corpus of two plays whose titles
    sanitise alike writes two directories rather than one (see
    `allocate_play_dir`).  A single-play run passes none: there is nobody
    else to collide with but an earlier run, which the marker file catches."""
    log.info("Parsing %s", xml_path.name)
    play = parse_play(xml_path)
    log.info(
        "  characters=%d  moves=%d  speeches=%d  large-seq=%d  middle-seq=%d  relations=%d",
        len(play.characters), len(play.moves), len(play.speeches),
        len(play.large_seqs), len(play.middle_seqs), len(play.relations),
    )

    # The directory is named for the title, so the output tree reads as a list
    # of plays; the play's identity is its id, recorded beside it.
    play_dir = allocate_play_dir(out_root, play.title_en or play.play_id,
                                 xml_path, claimed_dirs, play_id=play.play_id)

    # Enumerate every non-empty subset of the play's partOf groups.  For
    # each subset, the dashboard precomputes an aggregated variant; the
    # JS toggles pick which one to show.  With 1 group (current corpus),
    # this is a single extra variant per segmentation; with N groups,
    # 2**N - 1.  Costs only matter for N >= 5, which the corpus doesn't have.
    group_ids = aggregatable_groups(play)

    def _nonempty_subsets(items):
        return chain.from_iterable(combinations(items, r) for r in range(1, len(items) + 1))

    group_subsets = [tuple(sub) for sub in _nonempty_subsets(group_ids)]

    dashboard_payload: dict = {}

    # Three orthogonal mute modes (replace the older binary in/out).  The
    # (include_mutes, segment_cast) axes underneath are independent; this
    # table exposes all three meaningful combinations.  The fourth
    # combination (include_mutes=True, segment_cast="speaking") is
    # incoherent for our purposes (mute characters become isolated
    # nodes) and is not generated.
    MUTE_MODE_PARAMS = {
        # model         (include_mutes, segment_cast)
        "full":       (True,  "stage"),     # whole cast;    in segment: on stage
        "p-speaking": (False, "stage"),     # speakers only; in segment: on stage
        "s-speaking": (False, "speaking"),  # speakers only; in segment: speaking
    }

    def _run_pipeline(source_play, mode: str, mute_mode: str):
        """Run segmenter + graph builders + metric pipeline for one play view.

        Every model produces the same kind of graph: an undirected
        co-occurrence network, joining any two characters who share a
        segment.  They differ in the node set and in what makes a
        character count as being in a segment.

        `mute_mode` is one of:
          * "full"    — whole on-stage cast as nodes; a character is in a
            segment by standing on stage in it
          * "p-speaking" — play-level mutes dropped from the node set; being
            in a segment is still standing on stage in it
          * "s-speaking" — play-level mutes dropped; a character is in a
            segment only by speaking in it.  The edges remain
            co-occurrence: both spoke in the segment, which is not a claim
            that either addressed the other.
        """
        if mute_mode not in MUTE_MODE_PARAMS:
            raise ValueError(f"Unknown mute_mode: {mute_mode}")
        # p-speaking only: a partOf member that never speaks is a part
        # of its group, not a mute character, so its presence is attributed
        # to the group rather than dropped (Ecclesiazusae's chorus arrives in
        # three silent parts).  "full" keeps the parts as annotated, and
        # under "s-speaking" they are ignored anyway -- presence is not that
        # model's criterion, and they never speak.
        if mute_mode == "p-speaking":
            source_play = absorb_silent_parts(source_play)
        seg_fn = SEGMENTERS[mode]
        segments = seg_fn(source_play)
        if not segments:
            return None
        inc_mutes, seg_cast = MUTE_MODE_PARAMS[mute_mode]
        # The active model's node set.  Needed in two places: to fold the sd
        # spine below, and to make the segment indices answer for the graph
        # this model selects rather than for the raw annotated stage.  It is
        # computed before any fold, which is safe -- folding merges segments,
        # so the union of casts, and hence the node set, is unchanged.
        kept = _kept_characters(source_play.characters, segments,
                                inc_mutes, seg_cast)
        # Model-specific spine (sd + mutes-out models only): fold boundaries
        # the active model cannot see.  The stage model (mutes-in) is left as
        # the faithful annotated spine -- it keeps every move as a boundary,
        # so the only thing a fold would remove there is a redundant
        # duplicate-cast annotation, which is better surfaced than silently
        # merged (and "full" is the default view for file exports).
        # large-seq / middle-seq are textual divisions, not cast-triggered
        # boundaries, so they keep their fixed, model-independent spine.
        if mode == "sd" and not inc_mutes:
            segments = fold_for_model(segments, kept, seg_cast)
        static_g = build_static(segments, source_play.characters,
                                include_mutes=inc_mutes,
                                edge_weight=edge_weight,
                                segment_cast=seg_cast)
        dyn_spell = build_dynamic_spell_graph(segments, source_play.characters,
                                              include_mutes=inc_mutes,
                                              segment_cast=seg_cast)
        dyn_per_segment = build_dynamic(segments, source_play.characters,
                                        include_mutes=inc_mutes,
                                        segment_cast=seg_cast)
        metrics = compute_metrics(static_g,
                                  play_id=source_play.play_id,
                                  play_name=source_play.title_en or source_play.title_grc)
        metrics["segmentation"] = mode
        metrics["mute_mode"] = mute_mode
        metrics["segment_cast"] = seg_cast
        metrics["num_segments"] = len(segments)
        metrics["edge_weight"] = edge_weight
        metrics["demographics"] = compute_demographics(source_play, include_mutes=inc_mutes)
        metrics["speech_distribution"] = compute_speech_distribution(source_play)
        metrics["segment_indices"] = compute_segment_indices(segments, kept,
                                                             seg_cast)
        # Per-character temporal Gini.  Merged into the nodes list so
        # the per-play dashboard can render a "speech concentration"
        # table inside Plot Dynamics; surfaced at the play level (top
        # speaker only) so the corpus dashboard can show it as a
        # column without re-walking segments.  See methods §5 for the
        # operationalisation choice (all active segments, zero-padded).
        tgini = compute_temporal_gini(segments)
        # One referent, `top_speaker_id`: where several characters tie for the
        # largest word total, all of them are named in `top_speaker_ids`, but
        # each has a temporal Gini of their own and the column holds one
        # number.  It is the first of the tied ids; §5 says so.
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
                node["temporal_gini"]      = entry["temporal_gini"]
                node["total_words"]        = entry["total_words"]
                node["speaking_segments"]  = entry["speaking_segments"]
                # The metric's own divisor: without it neither the table's
                # "speaks / on stage" column nor a reader recomputing from
                # characters.csv can say what the tGini was divided by.
                node["n_onstage_segments"] = entry["n_onstage_segments"]
        dynamic_rows = compute_dynamic_metrics(dyn_per_segment)
        return {
            "static_graph": static_g,
            "dyn_spell": dyn_spell,
            "segments": segments,
            "metrics": metrics,
            "dynamic_rows": dynamic_rows,
            # The play this view was actually computed on: p-speaking absorbs
            # a speaking figure's silent parts, so its roster differs
            # from the annotated one and the dashboard must read it from here.
            "play": source_play,
        }

    for mode in seg_modes:
        # All three models are always computed: the dashboard carries them
        # side by side ("full" at the top level, the other two in
        # `variants`) and switches at viewing time.  The file exports can
        # hold only one, chosen by --export-model; "full" (= stage, the
        # annotated co-presence spine) is the default.
        raw_stage    = _run_pipeline(play, mode, mute_mode="full")
        if raw_stage is None:
            log.warning("  [%s] no segments produced (skipped)", mode)
            continue
        raw_p_speaking = _run_pipeline(play, mode, mute_mode="p-speaking")
        raw_s_speaking = _run_pipeline(play, mode, mute_mode="s-speaking")

        seg_dir = play_dir / mode
        by_mute_mode = {"full": raw_stage, "p-speaking": raw_p_speaking,
                        "s-speaking": raw_s_speaking}
        exported = by_mute_mode.get(export_model)
        if exported is None:
            # Only reachable if a non-stage pipeline yielded nothing while
            # stage did; export the spine rather than write no files.
            log.warning("  [%s] export model %r produced no graph; "
                        "exporting %r instead", mode, export_model,
                        DEFAULT_EXPORT_MODEL)
            exported = raw_stage
        paths = write_outputs(
            play=play,
            segments=exported["segments"],
            static_graph=exported["static_graph"],
            dynamic_spell_graph=exported["dyn_spell"],
            metrics=exported["metrics"],
            dynamic_rows=exported["dynamic_rows"],
            out_dir=seg_dir,
        )
        log.info("  [%s] stage     %d segments  size=%d  edges=%d  density=%.4f",
                 mode, len(raw_stage["segments"]),
                 raw_stage["metrics"]["size"], raw_stage["metrics"]["numEdges"],
                 raw_stage["metrics"]["density"])
        if raw_p_speaking is not None:
            log.info("  [%s] p-speaking                size=%d  edges=%d  density=%.4f",
                     mode,
                     raw_p_speaking["metrics"]["size"], raw_p_speaking["metrics"]["numEdges"],
                     raw_p_speaking["metrics"]["density"])
        if raw_s_speaking is not None:
            log.info("  [%s] s-speaking                size=%d  edges=%d  density=%.4f",
                     mode,
                     raw_s_speaking["metrics"]["size"], raw_s_speaking["metrics"]["numEdges"],
                     raw_s_speaking["metrics"]["density"])
        log.info("  [%s] exported model: %s", mode, export_model)
        for name, p in paths.items():
            log.info("    -> %s", p)

        # Variants: one per (mute_mode, group_subset) pair.  Empty subset
        # with mute_mode="full" is the top-level (default) view and is
        # NOT added to variants -- the dashboard reads it from r directly.
        variants: dict = {}
        if raw_p_speaking is not None:
            variants["p-speaking:"] = {
                "static_graph": raw_p_speaking["static_graph"],
                "segments":     raw_p_speaking["segments"],
                "metrics":      raw_p_speaking["metrics"],
                "dynamic_rows": raw_p_speaking["dynamic_rows"],
                "play":         raw_p_speaking["play"],
            }
        if raw_s_speaking is not None:
            variants["s-speaking:"] = {
                "static_graph": raw_s_speaking["static_graph"],
                "segments":     raw_s_speaking["segments"],
                "metrics":      raw_s_speaking["metrics"],
                "dynamic_rows": raw_s_speaking["dynamic_rows"],
                "play":         raw_s_speaking["play"],
            }
        for subset in group_subsets:
            play_v = aggregate_play(play, groups=set(subset))
            if play_v is play:
                continue
            key_g = ",".join(sorted(subset))
            for mute_mode in ("full", "p-speaking", "s-speaking"):
                agg = _run_pipeline(play_v, mode, mute_mode=mute_mode)
                if agg is None:
                    continue
                variants[f"{mute_mode}:{key_g}"] = {
                    "static_graph": agg["static_graph"],
                    "segments":     agg["segments"],
                    "metrics":      agg["metrics"],
                    "dynamic_rows": agg["dynamic_rows"],
                    "play":         agg["play"],
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
    seg_modes = (["sd", "large-seq", "middle-seq"] if args.seg == "all" else [args.seg])
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    summary = analyze_one(
        xml_path=Path(args.file),
        seg_modes=seg_modes,
        out_root=out_root,
        export_model=args.export_model,
        edge_weight=args.weight,
        make_dashboard=not args.no_dashboard,
    )
    if summary is None:
        # Nothing was written but the directory's marker: a script calling
        # this must not read the run as a success.
        log.error("No segmentation produced any segments for %s (asked for: "
                  "%s); nothing was exported.", args.file, ", ".join(seg_modes))
        return 1
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
    return f"Custom corpus ({n_plays} play{'' if n_plays == 1 else 's'})"


def cmd_corpus(args: argparse.Namespace) -> int:
    seg_modes = (["sd", "large-seq", "middle-seq"] if args.seg == "all" else [args.seg])
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
    claimed_dirs: Dict[str, str] = {}
    for f in files:
        try:
            s = analyze_one(
                xml_path=f,
                seg_modes=seg_modes,
                out_root=out_root,
                export_model=args.export_model,
                edge_weight=args.weight,
                make_dashboard=not args.no_dashboard,
                claimed_dirs=claimed_dirs,
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
    a.add_argument("--seg", choices=["sd", "large-seq", "middle-seq", "all"], default="all",
                   help="Segmentation method (default: all three)")
    a.add_argument("--export-model", choices=list(EXPORT_MODELS),
                   default=DEFAULT_EXPORT_MODEL,
                   help="Which network model is written to the exported files "
                        "(default: full). full = every character on stage; "
                        "p-speaking = characters who speak somewhere in the "
                        "play; s-speaking = characters speaking in the segment "
                        "at hand. All three are undirected co-occurrence "
                        "networks; the dashboard always carries all three.")
    a.add_argument("--weight", choices=["segments", "words"],
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
    c.add_argument("--seg", choices=["sd", "large-seq", "middle-seq", "all"], default="all")
    c.add_argument("--export-model", choices=list(EXPORT_MODELS),
                   default=DEFAULT_EXPORT_MODEL,
                   help="Which network model is written to the exported files "
                        "(default: full). See `analyze --help`.")
    c.add_argument("--weight", choices=["segments", "words"], default="segments")
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
        "export_model": DEFAULT_EXPORT_MODEL,
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
