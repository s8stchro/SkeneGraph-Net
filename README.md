# SkeneGraph-Net

<!-- After the first Zenodo release, uncomment and fill in the concept DOI:
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
-->

Network-analysis application for TEI/XML-encoded ancient Greek and Latin drama,
modelled on the [DraCor API](https://dracor.org/doc/api) and departing from it
on four methodological points:

1. **Three segmentation methods** (DraCor uses one):
   * `sd`   — stage directions: a new segment opens after every `<move>`
   * `div3` — one segment per `<div3>` (the "scene" level)
   * `div2` — one segment per `<div2>` (the "macro-structure" / act level)

2. **Three network models** over two orthogonal axes — the *cast filter*
   (are play-level mute characters admitted as nodes?) and the *edge rule*
   (co-presence on stage vs. co-speech within a segment). DraCor offers a
   single speakers-only co-occurrence model.

   | model | node set | edge `(u, v)` iff |
   |---|---|---|
   | `stage` *(default)* | all characters, **including** play-level mutes | both on stage in some segment |
   | `dialogic` | speakers only (play-level mutes dropped) | both on stage in some segment |
   | `cospeech` | speakers only (play-level mutes dropped) | both **speak** in some segment |

   The fourth combination — mutes admitted but edges defined by co-speech — is
   incoherent (mutes would become isolated nodes) and is not generated.
   `--no-mutes` drops play-level mutes from the static graph.

3. **Collective figures aggregated or split.** The chorus and its subdivisions
   (e.g. `chorosAndron`, `chorosGynaikon` `partOf` `choros`) can be collapsed
   into a single node or kept distinct. Not modelled by DraCor.

4. **Dynamic graph** produced alongside the static one and packaged as a
   Gephi-renderable GEXF with `<spells>` describing when each character and
   each edge is active. DraCor publishes the static aggregate only.

Each of these is a deliberate, exposed choice rather than a hidden default. The
full methodology — every metric and formula, and the rationale for each model —
lives in the **Methods & formulas** tab of every generated dashboard.

## Install

```sh
pip install -r requirements.txt
```

Tested with **Python 3.13, lxml 6.0, networkx 3.5** (floors: lxml ≥ 4.9,
networkx ≥ 3.0). The figure scripts under `figures/` additionally need
matplotlib — see [`requirements-figures.txt`](requirements-figures.txt).

## Quickstart

A sample play — Aristophanes, *Lysistrata* — ships under [`examples/`](examples/):

```sh
python app.py analyze examples/Ar-07-Lys.xml
```

This writes `output/Aristophanes_Lysistrata/`; open its `dashboard.html` in any
browser (it loads D3 from a CDN, so an internet connection is needed the first
time). Run with **no arguments** for a guided prompt:

```sh
python app.py
```

## Run

```sh
# one play
python app.py analyze examples/Ar-07-Lys.xml
python app.py analyze examples/Ar-07-Lys.xml --seg div2 --no-mutes

# corpus subcommand accepts one or more paths; each path is either a
# directory (globbed with --pattern, default *.xml) or a single TEI XML
# file.  Mix them freely; pass --name for a custom corpus title and
# --out to pick a non-default output root.  Paths below assume the full
# SkeneGraph corpus checked out alongside this app as ../01-SkeneGraph-corpus.
python app.py corpus  ../01-SkeneGraph-corpus/comedy/ --seg all
python app.py corpus  ../01-SkeneGraph-corpus/comedy/ ../01-SkeneGraph-corpus/tragedy/ \
                      --name "Drama" --out output/drama
python app.py corpus  ../01-SkeneGraph-corpus/comedy/Ar-07-Lys.xml \
                      ../01-SkeneGraph-corpus/comedy/Ar-01-Ach.xml \
                      ../01-SkeneGraph-corpus/comedy/Ar-03-Nub.xml \
                      --name "Lysistrata + references" \
                      --out output/lys-presentation
```

Flags: `--seg {sd,div2,div3,all}` (default `all`), `--no-mutes`,
`--weight {segments,verses,words}` (static-graph edge weight, default
`segments`, DraCor-compatible), `--out`, `--no-dashboard`.

Each invocation writes::

    output/<play_id>/
        dashboard.html              (interactive dashboard, all three segmentations)
        <seg>/
            metrics.json            (DraCor /metrics-style JSON)
            characters.csv          (one row per character + centralities)
            segments.csv            (one row per segment + cast)
            networkdata.csv         (DraCor /networkdata/csv: Source,Type,Target,Weight)
            networkdata.gexf        (static, Gephi)
            networkdata.graphml     (static, Cytoscape / yEd)
            dynamic.gexf            (dynamic with spells, Gephi)
            dynamic_metrics.csv     (per-segment size / edges / density)

`dashboard.html` opens directly in any browser (it loads D3 from a CDN; no
server needed) and lets you:

  * switch between the three segmentations as tabs;
  * switch between the three network models, and toggle node labels on / off;
  * inspect the static co-presence graph (force-directed; node area is
    proportional to degree, edge width to weight, colour to role);
  * scrub through the dynamic graph segment-by-segment with the slider, or
    play it back; click on the density chart to jump to a segment;
  * read the in-app *Methods* panel documenting every metric and choice;
  * sort the character and segment tables.

`metrics.json` mirrors the DraCor schema, with extra fields recording the
methodological configuration that produced it:

```json
{
  "id": "Aristophanes' Acharnians",
  "name": "Acharnians",
  "size": 31, "numEdges": 92,
  "density": 0.198, "averageDegree": 5.93,
  "maxDegree": 24, "maxDegreeIds": ["dikaiopolis"],
  "diameter": 3, "averagePathLength": 1.73,
  "averageClustering": 0.61, "numConnectedComponents": 1,
  "nodes": [
    {"id": "dikaiopolis", "degree": 24, "weightedDegree": 81,
     "betweenness": 0.31, "closeness": 0.79, "eigenvector": 0.41}
  ],
  "segmentation": "sd", "num_segments": 28,
  "mute_mode": "stage", "edge_rule": "presence", "edge_weight": "segments",
  "demographics": {}, "speech_distribution": {}, "segment_indices": {}
}
```

## Modules

* `parser.py`        TEI → `PlayData` (characters, moves, speeches, div2/div3)
* `segmentation.py`  three segmenters → list of `Segment`
* `aggregation.py`   collective-figure (`partOf`) aggregation
* `network.py`       static, dynamic-per-segment, dynamic-spell graphs
* `metrics.py`       DraCor-compatible metrics
* `exporter.py`      CSV / GEXF / GraphML / JSON writers
* `dashboard.py`     self-contained HTML dashboard (D3 + embedded JSON)
* `corpus_dashboard.py`  corpus-level dashboard
* `methods_content.py`   the in-app *Methods* panel
* `interactive.py`   guided prompt (run `python app.py` with no subcommand)
* `app.py`           CLI entry point

Pass `--no-dashboard` to skip the HTML generation. Paper-figure scripts live
under `figures/`; one-off data-migration utilities under `scripts/`.

## Cite this software

Citation metadata is in [`CITATION.cff`](CITATION.cff). After the first Zenodo
release, please cite via the Zenodo **concept DOI** (which always resolves to
the latest version).

## License

The **software** is Apache-2.0 — see [`LICENSE`](LICENSE). Copyright 2024–2026
Stylianos Chronopoulos.

The sample **data** under [`examples/`](examples/) is licensed separately, under
**CC BY-SA 4.0** (base text from the Perseus Digital Library; editorial additions
by the author). See [`examples/README.md`](examples/README.md) for attribution.
