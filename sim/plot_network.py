"""Draw the schematic DMA. Run: python -m sim.plot_network"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from sim.network import (
    INLET_PIPE,
    RESERVOIR_ID,
    RESERVOIR_XY,
    build_dma,
    junction_coordinates,
    pipe_table,
)


def draw(ax=None, sensors: list[str] | None = None, leaks: list[str] | None = None):
    coords = junction_coordinates()
    coords[RESERVOIR_ID] = RESERVOIR_XY
    if ax is None:
        _, ax = plt.subplots(figsize=(8.2, 6.4))
    for pid, start, end, _length, diameter in pipe_table():
        x0, y0 = coords[start]
        x1, y1 = coords[end]
        lw = 1.2 + 18.0 * diameter
        color = "#1f4e79" if pid == INLET_PIPE else "#4a7aa8"
        ax.plot([x0, x1], [y0, y1], color=color, lw=lw, solid_capstyle="round", zorder=1)
    sensors = set(sensors or [])
    leaks = set(leaks or [])
    for name, (x, y) in coords.items():
        if name == RESERVOIR_ID:
            ax.scatter([x], [y], s=160, c="#c0392b", marker="s", zorder=3, edgecolors="k")
            ax.annotate(name, (x, y), xytext=(-18, 8), textcoords="offset points", fontsize=8)
            continue
        color = "#27ae60" if name in sensors else "#f4d03f" if name in leaks else "#ecf0f1"
        marker = "D" if name in sensors else "o"
        ax.scatter([x], [y], s=90, c=color, marker=marker, zorder=3, edgecolors="#2c3e50")
        ax.annotate(name, (x, y), xytext=(5, 4), textcoords="offset points", fontsize=7)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("M.A.J.I schematic DMA (18 junctions, looped + branched)")
    handles = [
        mpatches.Patch(color="#4a7aa8", label="pipe (width ∝ diameter)"),
        mpatches.Patch(color="#c0392b", label="reservoir / inlet"),
    ]
    if sensors:
        handles.append(mpatches.Patch(color="#27ae60", label="pressure sensor"))
    if leaks:
        handles.append(mpatches.Patch(color="#f4d03f", label="true leak node"))
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8)
    return ax


def main() -> None:
    out = Path("results/figures")
    out.mkdir(parents=True, exist_ok=True)
    build_dma()  # sanity that the model still constructs
    fig, ax = plt.subplots(figsize=(8.2, 6.4))
    draw(ax)
    fig.tight_layout()
    path = out / "fig_dma_network.png"
    fig.savefig(path, dpi=160)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
