# -*- coding: utf-8 -*-
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

POS = {
    "X1": (0.00,  0.85),
    "X2": (-0.74, -0.43),
    "X3": (0.74, -0.43),
}

PANELS = [
    ([("X1","X2"), ("X1","X3")]),
    ([("X1","X2"), ("X2","X3"), ("X1","X3")]),
]

INK = "#1a1a1a"
NODE_R = 0.28

fig, axes = plt.subplots(2, 1, figsize=(3.2, 6.0))
for ax, edges in zip(axes, PANELS):
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-1.1, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    for a, b in edges:
        (xa, ya), (xb, yb) = POS[a], POS[b]
        ax.plot([xa, xb], [ya, yb], color=INK, lw=1.8,
                solid_capstyle="round", zorder=1)
    for name, (x, y) in POS.items():
        ax.add_patch(Circle((x, y), NODE_R, facecolor="white",
                            edgecolor=INK, lw=1.6, zorder=2))
        ax.text(x, y, name, ha="center", va="center",
                fontsize=13, color=INK, zorder=3)

plt.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02, hspace=0.08)
OUT = str(Path(__file__).with_name("two-triads.png"))
fig.savefig(OUT, dpi=200, facecolor="white")
print("wrote", OUT)
