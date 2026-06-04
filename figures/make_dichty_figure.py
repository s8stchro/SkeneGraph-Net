# -*- coding: utf-8 -*-
"""'Dichty' (Net): one graph per scene + the aggregate graph, as one PNG.

Fixed positions for all five nodes across every panel (X1 central, since it
is present in every scene; X2/X3/X4/X5 at N/E/S/W chosen so each scene's
co-presence clique and the union are crossing-free).  Characters absent from
a scene are drawn faintly so the fixed five-person frame stays visible.
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
    ("Σκηνή 2", ["X1", "X4", "X5"],
        [("X1", "X4"), ("X1", "X5"), ("X4", "X5")]),
    ("Σκηνή 3", ["X1", "X3", "X5"],
        [("X1", "X3"), ("X1", "X5"), ("X3", "X5")]),
]
TOTAL_EDGES = [("X1", "X2"), ("X1", "X3"), ("X2", "X3"), ("X1", "X4"),
               ("X1", "X5"), ("X3", "X5"), ("X4", "X5")]
TOTAL_TITLE = "Συνολικό γράφημα"  # "Συνολικό γράφημα"

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
    for a, b in edges:                      # edges first (behind discs)
        (xa, ya), (xb, yb) = POS[a], POS[b]
        ax.plot([xa, xb], [ya, yb], color=INK, lw=1.8,
                solid_capstyle="round", zorder=1)
    for name, (x, y) in POS.items():
        on = name in present
        ax.add_patch(Circle((x, y), NODE_R, facecolor="white",
                            edgecolor=INK if on else FAINT, lw=1.6, zorder=2))
        ax.text(x, y, name, ha="center", va="center", fontsize=12,
                color=INK if on else FAINT, zorder=3)

fig.suptitle("«Δίχτυ»", fontsize=18, color=INK)  # «Δίχτυ»
plt.subplots_adjust(left=0.01, right=0.99, top=0.82, bottom=0.02, wspace=0.06)
OUT = str(Path(__file__).with_name("dichty-scenes.png"))
fig.savefig(OUT, dpi=200, facecolor="white")
print("wrote", OUT)
