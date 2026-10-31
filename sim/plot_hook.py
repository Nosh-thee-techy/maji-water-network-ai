"""Figure: after the tank fills, inlet flow is the leak.

Run: python -m sim.plot_hook
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from sim.leaks import leaks_from_q_lps
from sim.network import build_dma
from sim.scenario import run_scenario


def main() -> None:
    wn = build_dma()
    none = run_scenario(scenario_id="hook-none", leaks=[], duration_h=12)
    leak = run_scenario(
        scenario_id="hook-leak",
        leaks=leaks_from_q_lps(wn, [("J07", 1.5)]),
        duration_h=12,
    )
    t = np.asarray(none.times_s) / 3600.0
    fig, axes = plt.subplots(2, 1, figsize=(8.4, 5.8), sharex=True)
    axes[0].plot(t, none.inlet_flow_lps, label="no leak", color="#1f4e79", lw=1.8)
    axes[0].plot(t, leak.inlet_flow_lps, label="1.5 L/s leak at J07", color="#c0392b", lw=1.8)
    axes[0].axvspan(5, 9, color="#d5f5e3", alpha=0.6, zorder=0)
    axes[0].set_ylabel("inlet flow (L/s)")
    axes[0].legend(frameon=False)
    axes[0].set_title("After the tank-fill window, remaining inlet flow is the leak")
    axes[1].plot(t, none.pressure_m["J07"], label="no leak", color="#1f4e79", lw=1.8)
    axes[1].plot(t, leak.pressure_m["J07"], label="leak at J07", color="#c0392b", lw=1.8)
    axes[1].axvspan(5, 9, color="#d5f5e3", alpha=0.6, zorder=0)
    axes[1].axhline(7.0, color="#8e44ad", ls="--", lw=1, label="intrusion prior (7 m)")
    axes[1].set_ylabel("pressure at J07 (m)")
    axes[1].set_xlabel("hour")
    axes[1].legend(frameon=False)
    fig.tight_layout()
    out = Path("results/figures")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "fig_storage_vs_leak.png"
    fig.savefig(path, dpi=160)
    print(f"wrote {path}")
    print("no-leak after-fill Q", float(none.inlet_flow_lps.loc[7 * 3600 : 9 * 3600].mean()))
    print("leak after-fill Q", float(leak.inlet_flow_lps.loc[7 * 3600 : 9 * 3600].mean()))


if __name__ == "__main__":
    main()
