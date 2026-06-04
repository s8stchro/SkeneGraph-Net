# -*- coding: utf-8 -*-
"""'Skorpochori' (episodic): one graph per scene + the aggregate, as one PNG.

Same fixed five-node frame and style as the 'Dichty' figure, so the two
plays can be compared node-for-node.  Here scenes 2 and 3 carry a single
edge each, so the aggregate is almost a star on X1 (only outer edge: X2-X3).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

POS = {
    "X1": (0.0,  0.0),
    "X2": (0.0,  1.0),
    "X3": (1.0,  0.0),
    "X4": (-1.0, 0.0),
    "X5": (0.0, -1.0),
}

SCENES = [
    ("Σκηνή 1", ["X1", "X2", "X3"],
        [("X1", "X2"), ("X1", "X3"), ("X2", "X3")]),
    ("Σκηνή 2", ["X1", "X4"], [("X1", "X4")]),
    ("Σκηνή 3", ["X1", "X5"], [("X1", "X5")]),
]
TOTAL_EDGES = [("X1", "X2"), ("X1", "X3"), ("X1", "X4"),
               ("X1", "X5"), ("X2", "X3")]
TOTAL_TITLE = "Συνολικό γράφημα"

INK = "#1a1a1a"
FAINT = "#c8c8c8"
NODE_R = 0.24

panels = [(t, set(p), e) for (t, p, e) in SCENES]
panels.append((TOTAL_TITLE, set(POS), TOTAL_EDGES))

fig, axes = plt.subplots(1, 4, figsize=(16, 4.7))
for ax, (title, present, edges) in zip(axes, panels):
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-1.5, 1.45)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=15, color=INK, pad=8)
    for a, b in edges:
        (xa, ya), (xb, yb) = POS[a], POS[b]
        ax.plot([xa, xb], [ya, yb], color=INK, lw=1.8,
                solid_capstyle="round", zorder=1)
    for name, (x, y) in POS.items():
        on = name in present
        ax.add_patch(Circle((x, y), NODE_R, facecolor="white",
                            edgecolor=INK if on else FAINT, lw=1.6, zorder=2))
        ax.text(x, y, name, ha="center", va="center", fontsize=12,
                color=INK if on else FAINT, zorder=3)

fig.suptitle("«Σκορποχώρι»", fontsize=18, color=INK)
plt.subplots_adjust(left=0.01, right=0.99, top=0.82, bottom=0.02, wspace=0.06)
OUT = str(Path(__file__).with_name("skorpochori-scenes.png"))
fig.savefig(OUT, dpi=200, facecolor="white")
print("wrote", OUT)
