# Changelog

All notable changes to SkeneGraph-Net are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-06-01

First public release.

### Features

- **TEI parser** (`parser.py`) — reads SkeneGraph-schema (TEI-compatible) drama
  into a `PlayData` model: characters, `<move>` stage directions, speeches, and
  the `div2` / `div3` hierarchy.
- **Three segmentation methods** (`segmentation.py`) — `sd` (stage directions),
  `div3` (scene), `div2` (act).
- **Three network models** over two orthogonal axes — cast filter (mutes in /
  out) × edge rule (co-presence / co-speech): `stage`, `dialogic`, `cospeech`.
- **Collective-figure aggregation** (`aggregation.py`) — the chorus and its
  subdivisions optionally collapsed to one node or kept distinct (`partOf`).
- **Static and dynamic graphs** (`network.py`) — static co-presence aggregate
  plus a per-segment dynamic graph carrying `<spells>`.
- **DraCor-compatible metrics** (`metrics.py`) — network-, character-, and
  segment-level measures.
- **Exporters** (`exporter.py`) — `metrics.json`, `characters.csv`,
  `segments.csv`, `networkdata.csv`, GEXF (static + dynamic), GraphML.
- **Self-contained dashboards** (`dashboard.py`, `corpus_dashboard.py`) — one
  HTML file per play / corpus, with an in-app methods panel.
- **CLI** (`app.py`) — `analyze` (one play) and `corpus` (many) subcommands.

[1.0.0]: https://github.com/USERNAME/SkeneGraph-Net/releases/tag/v1.0.0
