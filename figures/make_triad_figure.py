"""Render the 8 labelled graphs on 3 vertices (X1, X2, X3) as one PNG.

Fixed equilateral-triangle node positions across all panels, so only the
edges change from panel to panel.  Deliberately plain: black on white,
white-filled nodes, thin edges, a small panel index beneath each.
"""
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

GRAPHS = [
    [],                                                      # 1 empty
    [("X1", "X2")],                                          # 2
    [("X1", "X3")],                                          # 3
    [("X2", "X3")],                                          # 4
    [("X1", "X2"), ("X1", "X3")],                            # 5
    [("X1", "X2"), ("X2", "X3")],                            # 6
    [("X1", "X3"), ("X2", "X3")],                            # 7
    [("X1", "X2"), ("X2", "X3"), ("X1", "X3")],              # 8 complete
]

INK = "#1a1a1a"
NODE_R = 0.30

fig, axes = plt.subplots(2, 4, figsize=(11, 6))
for i, (ax, edges) in enumerate(zip(axes.flat, GRAPHS), start=1):
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-1.25, 1.2)
    ax.set_aspect("equal")
    ax.axis("off")
    # edges (drawn first, so the white node discs sit on top of the ends)
    for a, b in edges:
        (xa, ya), (xb, yb) = POS[a], POS[b]
        ax.plot([xa, xb], [ya, yb], color=INK, lw=1.8,
                solid_capstyle="round", zorder=1)
    # nodes
    for name, (x, y) in POS.items():
        ax.add_patch(Circle((x, y), NODE_R, facecolor="white",
                            edgecolor=INK, lw=1.5, zorder=2))
        ax.text(x, y, name, ha="center", va="center",
                fontsize=12, color=INK, zorder=3)
    # panel index
    ax.text(0, -1.12, str(i), ha="center", va="center",
            fontsize=14, color=INK)

plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01,
                    wspace=0.05, hspace=0.08)
OUT = str(Path(__file__).with_name("three-node-graphs.png"))
fig.savefig(OUT, dpi=200, facecolor="white")
print("wrote", OUT)
