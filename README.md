# SkeneGraph-Net

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20548973.svg)](https://doi.org/10.5281/zenodo.20548973)

Network-analysis application for TEI/XML-encoded drama, modelled on the
[DraCor API](https://dracor.org/doc/api) and departing from it on four
methodological points:

1. **Three segmentation methods** (DraCor uses one):
   * `sd`   — stage directions: a new segment opens at every `<move>` that
     changes who is on stage (an entrance, an exit, an assertion of presence,
     or a collective merging or splitting). A crossing, and a change of state
     such as a figure becoming visible, leave the segment as it is.
   * `middle-seq` — one segment per `<milestone unit="middle-seq">` (the "scene" level)
   * `large-seq` — one segment per `<milestone unit="large-seq">` (the "macro-structure" / act level)

2. **Three network models** over two orthogonal axes — the *node set*
   (are play-level mute characters admitted as nodes?) and the *segment cast*
   (what makes a character count as being in a segment: standing on stage in
   it, or speaking in it). All three are undirected co-occurrence networks:
   an edge records that two characters shared a segment, never that one
   addressed the other — `@toWhom` is parsed but takes no part in these
   graphs. DraCor offers a single speakers-only co-occurrence model.

   | model | node set | segment cast — edge `(u, v)` iff |
   |---|---|---|
   | `full` *(default)* | all characters, **including** play-level mutes | both on stage in some segment |
   | `p-speaking` | speakers only (play-level mutes dropped) | both on stage in some segment |
   | `s-speaking` | speakers only (play-level mutes dropped) | both **speak** in some segment |

   The fourth combination — mutes admitted but the segment cast defined by
   speaking — is incoherent (mutes would become isolated nodes) and is not
   generated.

   `p-speaking` and `s-speaking` name speakers at **p**lay and at **s**egment
   scope: the first admits anyone who speaks somewhere in the play and then
   asks who stood on stage together, the second asks, segment by segment, who
   actually spoke there. These three keys are what the command line and
   `metrics.json` (`mute_mode`) use; the dashboards name the same models in
   words — *stage co-presence*, *speaking cast on play level*, *speaking cast
   on segment level* — and so do the captions of exported figures.

   All three are always computed, and the dashboard switches between them at
   viewing time. The exported files can hold only one, named by
   `--export-model`. `characters.csv` always lists the full roster, with
   `in_network` marking who the chosen model admits.

   On the stage-direction spine each model gets a spine of its own: a
   boundary the model cannot see is folded away — a mute's entrance under the
   speaking models, or, under the segment-level one, a figure crossing in
   silence between two characters who speak on either side. The three models
   therefore report different segment counts for the same play, and
   `num_segments` in `metrics.json` is the count of the spine that model saw.
   The textual spines are the editor's divisions and stay fixed.

   Under `p-speaking` only, a `partOf` member that never speaks is treated as
   a part of the figure it belongs to rather than as a mute character:
   its presence is attributed to that figure, provided the figure itself
   speaks. Members that speak in their own right are left alone. This affects
   one play in the Aristophanic corpus — Ecclesiazusae, whose chorus enters in
   three silent parts during the prologue and only sings once whole: without
   the attribution the chorus would stand absent from four of the play's
   forty stage-direction segments, and its graph would lose three edges.

3. **Collective figures aggregated or split.** The chorus and its subdivisions
   (e.g. `chorosAndron`, `chorosGynaikon` `partOf` `choros`) can be collapsed
   into a single node or kept distinct. Kept distinct, a part and its whole
   are still one body and are never joined by an edge, even where a large or
   middle sequence holds both. Not modelled by DraCor.

4. **Dynamic graph** produced alongside the static one and packaged as a
   Gephi-renderable GEXF whose `<spells>` give, segment by segment, when each
   character and each edge is active. DraCor publishes the static aggregate
   only.

Input is TEI/XML in the TEI-compatible **SkeneGraph schema** (stage directions
as `<move>`, the `large-seq` / `middle-seq` hierarchy, and `partOf` relations for collective
figures); arbitrary TEI may need adapting first. The tool itself is
language-agnostic — it has so far been exercised on ancient Greek drama.

Each of these is a deliberate, exposed choice rather than a hidden default. The
full methodology — every metric and formula, and the rationale for each model —
lives in the **Methods & formulas** tab of every generated dashboard.

## Install

```sh
pip install -r requirements.txt
```

Tested with **Python 3.13, lxml 6.0, networkx 3.5, numpy 2.3, scipy 1.16**
(floors: lxml ≥ 5.0, networkx ≥ 3.0, numpy ≥ 1.25, scipy ≥ 1.11.2). NumPy and
SciPy are listed because NetworkX does not require them and the eigenvector
centralities come out slightly different without them; see
[`requirements.txt`](requirements.txt).

## Quickstart

Two sample plays — Aristophanes, *Lysistrata* and *Acharnians* — ship under
[`examples/`](examples/):

```sh
python app.py analyze examples/Ar-07-Lys.xml
```

This writes `output/Lysistrata/`, a directory named for the play's English
title; open its `dashboard.html` in any browser. The page carries D3 and,
for the formulas in the *Methods* tab, KaTeX inside itself, so it works
offline. Run with **no arguments** for a guided prompt:

```sh
python app.py
```

## Run

```sh
# one play
python app.py analyze examples/Ar-07-Lys.xml
python app.py analyze examples/Ar-07-Lys.xml --seg large-seq --export-model p-speaking

# the two bundled samples as a corpus
python app.py corpus  examples/

# corpus subcommand accepts one or more paths; each path is either a
# directory (globbed with --pattern, default *.xml) or a single TEI XML
# file.  Mix them freely; pass --name for a custom corpus title and
# --out to pick a non-default output root.  The paths below assume the
# SkeneGraph corpus checked out alongside this app as
# ../01-SkeneGraph-corpus, whose comedy/ holds the eleven Aristophanic
# comedies.
python app.py corpus  ../01-SkeneGraph-corpus/comedy/ --seg all
python app.py corpus  path/to/comedy/ path/to/tragedy/ \
                      --name "Drama" --out output/drama
python app.py corpus  ../01-SkeneGraph-corpus/comedy/Ar-07-Lys.xml \
                      ../01-SkeneGraph-corpus/comedy/Ar-01-Ach.xml \
                      ../01-SkeneGraph-corpus/comedy/Ar-03-Nub.xml \
                      --name "Lysistrata + references" \
                      --out output/lys-presentation
```

Flags, on both subcommands: `--seg {sd,large-seq,middle-seq,all}` (default
`all`), `--export-model {full,p-speaking,s-speaking}` (which model reaches the
files, default `full`), `--weight {segments,words}` (static-graph edge weight,
default `segments`, DraCor-compatible), `--out`, `--no-dashboard`. `corpus`
adds `--pattern` (the glob applied to each directory, default `*.xml`) and
`--name`.

Each invocation writes::

    output/
        corpus_dashboard.html            (`corpus` only: every play in one view)
        <title>/
            dashboard.html               (interactive dashboard, one tab per segmentation run)
            source.json                  (the file this directory was built from, and the play's id)
            <seg>/
                metrics.json             (DraCor /metrics-style JSON)
                characters.csv           (one row per character: centralities, clustering,
                                          triangles, words, stage time)
                segments.csv             (one row per segment: stage cast, speakers,
                                          and the cast the exported model joins)
                networkdata.csv          (DraCor /networkdata/csv: Source,Type,Target,Weight)
                networkdata.gexf         (static, Gephi)
                networkdata.graphml      (static, Cytoscape / yEd)
                dynamic.gexf             (dynamic, one timestamp per segment, Gephi)
                dynamic_metrics.csv      (per-segment size / edges / words)

A play's directory is named for its English title, so the output tree reads as
a list of plays, and `source.json` records which file it was built from.
Re-running the same file reuses its directory. A different file wanting a
directory another play holds — two *Electras*, or two titles that sanitise
alike — is given one qualified by its file name instead, with a warning,
rather than overwriting what is there.

A segment's graph is its cast joined into a clique, so `dynamic_metrics.csv`
reports no per-segment density: it would read 1 wherever two or more stand
together and 0 otherwise, which states the construction rather than the play.
Its `numEdges` is the same fact as a count, *n*(*n* − 1)/2, less any pair of a
collective and its own part, which are never joined.

`dashboard.html` opens directly in any browser (D3 and KaTeX are inlined; no
server and no internet connection needed) and lets you:

  * switch between the segmentations as tabs, and between the three network
    models, with the collectives aggregated or split;
  * inspect the static co-presence graph (force-directed; node area is
    proportional to degree, edge width to weight, colour to role), with node
    labels on or off;
  * scrub through the dynamic graph segment-by-segment with the slider, or
    play it back; jump to a segment by clicking the beat chart, the segment
    timeline, a heatmap cell or a table row;
  * read the character × segment heatmap, whose cells tell absence from a
    silent presence, from a performance whose text is not transmitted, from
    words spoken; its key stands under the chart;
  * read the in-app *Methods* panel documenting every metric and choice;
  * sort the character and segment tables, the first carrying the
    centralities with the local clustering coefficient and triangle count,
    the second each segment's cast;
  * export any figure with the **SVG** / **PNG** buttons in its panel header,
    any table with **CSV** / **COPY**, and every configuration at once with
    **CSV × ALL**.

`corpus_dashboard.html` puts the same controls over a whole corpus: a chip
selector for the plays included, corpus KPIs, four scatters (density × order,
average degree × order, the drama-dynamics typology of Fischer et al. (2017), and
effective speakers × average degree), cast-composition bars, one beat chart
per play, a chorus-presence chart, and a sortable table of the plays, whose
rows link to the per-play dashboards. Density × order can colour its dots by
average degree and draw lines between plays of nearly equal order; both are
off until asked for.

### Exporting figures and data

Every chart in both dashboards is SVG, so a figure meant for an article or a
talk can be lifted out as vector art rather than photographed. Each panel
header carries two buttons: **SVG**, which downloads the figure with its text
still text — rescalable, and editable in Inkscape or Illustrator — and
**PNG**, a 3× bitmap for slides.

A figure is headed by its panel's title and footed by a provenance line:
*Acharnians · stage-direction segmentation · speaking cast on play level ·
aggregated: choros · edges weighted by segments · SkeneGraph-Net x.y.z*. The
line is also written into the file's `<title>` and `<desc>`, and is wrapped to
the figure's width, so nothing of it falls outside the image. The same panel
shows different numbers under different segmentations and models, so a figure
that cannot say which one it came from cannot be checked by a reader or
re-made by its author; the screenshot it replaces carried none of that. Where
the dynamic graph is showing a single segment, where the beat multiples are
spaced by word position, or where the dots carry a play's average degree in
their colour, the caption says so too.

What is exported is what the panel shows, not the first `<svg>` in it: a grid
of small multiples comes out as the whole grid, with the per-chart titles that
live in HTML redrawn into the figure, and a chart's key travels with it —
plain colours, the heatmap's hatch, and the word ramp alike, each redrawn as
the chart draws it. Colours are resolved on the way out, since the charts
paint themselves through CSS custom properties that mean nothing outside the
dashboard. For a journal that wants EPS or PDF, convert the SVG with Inkscape.

Tables carry **CSV** and **COPY** instead. Both take the whole table, not the
visible part — these tables sit in scroll boxes, so a screenshot of the
speech-concentration panel silently omits its loudest speakers. CSV is written
with a byte-order mark so Greek names survive in Excel; COPY puts the table on
the clipboard tab-separated, which pastes into a spreadsheet or a Word table
without an import dialogue.

### Comparing configurations

The **CSV × ALL** button on the metrics panel writes every combination the
dashboard can show as a single table: each segmentation × network model ×
aggregation state, one row apiece, with order, edges, density, average degree,
maximum degree, diameter, average path length, clustering, components, segment
count, the plot-dynamics indices, the word-distribution figures and the top
speaker. The corpus dashboard's version spans every play as well — 135 rows
for the eleven comedies — and adds the author and the drama-change rate.

This is the comparison the dashboards can otherwise only show one cell of at a
time. Building the article's Table 1 meant switching model, reading, switching
back and remembering; it is now one file and a pivot table. An empty
`aggregated` column means the collectives were left split, in both exports.

`metrics.json` mirrors the DraCor schema, with extra fields recording the
methodological configuration that produced it:

```json
{
  "id": "tlg0019.tlg001",
  "name": "Acharnians",
  "size": 43, "numEdges": 174,
  "density": 0.193, "averageDegree": 8.09,
  "maxDegree": 42, "maxDegreeIds": ["dikaiopolis"],
  "diameter": 2, "averagePathLength": 1.81,
  "averageClustering": 0.879, "numConnectedComponents": 1,
  "nodes": [
    {"id": "dikaiopolis", "degree": 42, "weightedDegree": 249,
     "betweenness": 0.5956, "closeness": 1.0, "eigenvector": 0.5556,
     "clustering": 0.1533, "triangles": 132,
     "total_words": 3326, "speaking_segments": 63,
     "n_onstage_segments": 76, "temporal_gini": 0.6716}
  ],
  "segmentation": "sd", "num_segments": 94,
  "mute_mode": "full", "segment_cast": "stage", "edge_weight": "segments",
  "demographics": {}, "speech_distribution": {}, "segment_indices": {}
}
```

The last three fields are abbreviated above: `demographics` counts the cast by
kind, sex and nature; `speech_distribution` holds the word total, the speech
Gini, the effective speaker count and the top speaker; `segment_indices` holds
the plot-dynamics figures — the all-in segment and index, the final segment's
cast share, and the largest number of characters speaking in one segment.

One field in `segment_indices` reads oddly out of context: `all_in_segment` is
a **0-based position in the scanned sequence**, and an empty leading marker is
not scanned, so it is not the segment's number — Lysistrata's stage-direction
spine stores 51 beside the label `sd-53`. `all_in_segment_label` names the
segment; `all_in_index` is that position as a fraction of the scanned count,
*j*/*N′* with *j* 1-based — 52/62 = 0.8387 in the same play. The *Methods*
panel gives the definition in §5.

### How a play is identified

A title does not identify a play — Sophocles and Euripides each wrote an
*Electra*, and both cite as *El.* The `id` in `metrics.json`, in both
dashboards and in both CSV × ALL exports is therefore the play's **TLG work
number**, read from the header's CTS URN and kept to text group and work:

```xml
<idno type="CTS-URN">urn:cts:greekLit:tlg0019.tlg003.perseus-grc2</idno>
```

gives `tlg0019.tlg003` for *Clouds*; the trailing `.perseus-grc2` names one
digital text of the play, not the play, and is dropped. A bare canon number,
`<idno type="TLG">0019.003</idno>`, is accepted too. A file whose header has
neither is identified by its file name, with a warning. The output folders
stay named for the English title, so the output tree reads as a list of plays.

Where two plays of a corpus would carry the same label on a chart, the
author's citation form is added to both — *Soph. El.*, *Eur. El.* It is read
from the header, encoded like the Latin title:

```xml
<author xml:lang="lat"><choice><expan>Sophocles</expan><abbr>Soph.</abbr></choice></author>
```

and falls back to the author's name as given. A corpus without a shared title
is labelled exactly as before.

## Modules

* `parser.py`        TEI → `PlayData` (characters, moves, speeches, large-seq/middle-seq)
* `segmentation.py`  three segmenters → list of `Segment`
* `aggregation.py`   collective-figure (`partOf`) aggregation
* `network.py`       static, dynamic-per-segment, dynamic-spell graphs
* `metrics.py`       DraCor-compatible metrics
* `exporter.py`      CSV / GEXF / GraphML / JSON writers
* `dashboard.py`     self-contained HTML dashboard (D3 + embedded JSON)
* `corpus_dashboard.py`  corpus-level dashboard
* `methods_content.py`   the in-app *Methods* panel
* `figure_export.py`     per-panel SVG / PNG export, shared by both dashboards
* `vendor_assets.py`     inlines the pinned D3 and KaTeX from `vendor/`
* `interactive.py`   guided prompt (run `python app.py` with no subcommand)
* `version.py`       single source of the version string
* `app.py`           CLI entry point

Pass `--no-dashboard` to skip the HTML generation.

## Tests

The core pipeline (parsing → segmentation → graphs → metrics → export) is
covered by a pytest suite:

```bash
python -m pytest
```

`pytest` is the only dependency it adds (`requirements-dev.txt`); the suite
needs no network and writes nothing outside a temporary directory. Skip the
end-to-end runs that shell out to `app.py` with `-m "not slow"`.

A handful of tests run a piece of the dashboards' JavaScript — the scatter's
label placement, the figure caption's wrap — by cutting the function out of a
generated page and handing it to `node`. They are skipped where node is not
installed; everything else runs without it.

Tests fall into two kinds. Most assert *invariants* — that the play-level fold
preserves topology, that the speaking cast's edges are a subset of the
on-stage cast's, that a segment's word count is the sum of its speeches — and
so survive edits to the demo play. The version-sensitive numbers are confined to
`tests/baseline_demo.json`, a fingerprint of `examples/Ar-07-Lys.xml`. When you
change the demo play or a metric definition on purpose, accept the new values
with:

```bash
python tests/regen_baseline.py
```

which rewrites the baseline and prints exactly which quantities moved.

## Parallel scholarly annotation (not implemented)

The SkeneGraph encoding schema admits parallel *segmentation streams*: alongside
the primary segmentation, a published scholar's division of the same play can be
recorded as its own stream of `<milestone>` points tagged
`source="#work"` (see the corpus's `encoding-schema.md`, *Segmenting the
drama*). **SkeneGraph-Net reads the primary stream only** — milestones carrying
`@source` (or `@resp`) are ignored, so files containing parallel streams are
processed correctly but the alternative segmentations are not exposed in the
views. Reading such streams — selecting a scholar's segmentation per play, with
metrics and exports labelled by system — is a potential future feature, as is
the wider extension it belongs to: documenting alternative *stage-direction*
reconstructions (`<move>` streams) by different scholars.

## Cite this software

Citation metadata is in [`CITATION.cff`](CITATION.cff). After the first Zenodo
release, please cite via the Zenodo **concept DOI** (which always resolves to
the latest version). What changed between versions, and why, is in
[`CHANGELOG.md`](CHANGELOG.md).

## License

The **software** is Apache-2.0 — see [`LICENSE`](LICENSE). Copyright 2024–2026
Stylianos Chronopoulos.

The sample **data** under [`examples/`](examples/) is licensed separately, under
**CC BY-SA 4.0** (base text from the Perseus Digital Library; editorial additions
by the author). See [`examples/README.md`](examples/README.md) for attribution.
