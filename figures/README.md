# Paper-figure scripts

Standalone matplotlib scripts that render the schematic figures used in the
accompanying papers and presentations. They are **not** part of the app's
pipeline — they carry their own small, hand-set graph data — and are kept here
only for reproducibility of those figures.

## Use

```sh
pip install -r ../requirements-figures.txt   # matplotlib
python make_triad_figure.py
```

Each script writes its PNG next to itself (in this directory). The generated
PNGs are git-ignored.

| script | output | figure |
|---|---|---|
| `make_triad_figure.py` | `three-node-graphs.png` | the 8 labelled graphs on 3 vertices |
| `make_two_triads.py` | `two-triads.png` | two selected triads side by side |
| `make_comparison_figure.py` | `two-graphs.png` | Dichty / Skorpochori compared |
| `make_dichty_figure.py` | `dichty-scenes.png` | *Dichty* (Net): per-scene graphs + aggregate |
| `make_skorpochori_figure.py` | `skorpochori-scenes.png` | *Skorpochori* (episodic): per-scene graphs + aggregate |
