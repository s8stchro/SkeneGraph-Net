# -*- coding: utf-8 -*-
"""Two final graphs stacked vertically: Dichty (top) and Skorpochori (bottom).
Same fixed five-node positions as the individual-scene figures.
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

PANELS = [
    ("«Δίχτυ»",
     [("X1","X2"),("X1","X3"),("X2","X3"),("X1","X4"),("X1","X5"),("X3","X5"),("X4","X5")]),
    ("«Σκορποχώρι»",
     [("X1","X2"),("X1","X3"),("X1","X4"),("X1","X5"),("X2","X3")]),
]

INK   = "#1a1a1a"
NODE_R = 0.24

fig, axes = plt.subplots(2, 1, figsize=(4.2, 8.2))
for ax, (title, edges) in zip(axes, PANELS):
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-1.5, 1.45)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=15, color=INK, pad=6)
    for a, b in edges:
        (xa, ya), (xb, yb) = POS[a], POS[b]
        ax.plot([xa, xb], [ya, yb], color=INK, lw=1.8,
                solid_capstyle="round", zorder=1)
    for name, (x, y) in POS.items():
        ax.add_patch(Circle((x, y), NODE_R, facecolor="white",
                            edgecolor=INK, lw=1.6, zorder=2))
        ax.text(x, y, name, ha="center", va="center",
                fontsize=12, color=INK, zorder=3)

plt.subplots_adjust(left=0.02, right=0.98, top=0.97, bottom=0.02, hspace=0.18)
OUT = str(Path(__file__).with_name("two-graphs.png"))
fig.savefig(OUT, dpi=200, facecolor="white")
print("wrote", OUT)
