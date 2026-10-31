"""Static stand-ins for the three dashboard tabs (no browser required)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from dashboard.views import DEFAULT_INTRUSION_THRESHOLD_M, intrusion_flags
from sim.io import load_scenario
from sim.network import JUNCTION_NAMES
from sim.plot_network import draw


def main() -> None:
    data_dir = Path("data/scenarios")
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    # Pick a one-leak scenario for the demo frames.
    sid = next(r["scenario_id"] for r in index["scenarios"] if r["n_leaks"] == 1)
    meta, frames = load_scenario(data_dir, sid)
    sensors = json.loads(Path("results/placement.json").read_text(encoding="utf-8"))["placements"]["10"]["sensors"]
    leaks = [lk["node"] for lk in meta["leaks"]]
    out = Path("results/figures")
    out.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8.2, 6.4))
    draw(ax, sensors=sensors, leaks=leaks)
    ax.set_title(f"Crew view · scenario {sid} · sensors green · true leak yellow")
    fig.tight_layout()
    fig.savefig(out / "fig_dashboard_crew.png", dpi=150)
    plt.close(fig)

    bal = meta["water_balance_m3"]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    labels = ["Supplied", "Leaked", "Customer", "Unmetered", "Billed", "Meter error"]
    vals = [bal["supplied"], bal["leaked"], bal["customer"], bal["unmetered"], bal["billed"], bal["meter_error"]]
    ax.bar(labels, vals, color=["#1f4e79", "#c0392b", "#1e8449", "#b7950b", "#5d6d7e", "#8e44ad"])
    ax.set_ylabel("m³ / 48 h")
    ax.set_title(f"Manager view · water balance · {sid} (simulated)")
    fig.autofmt_xdate(rotation=20)
    fig.tight_layout()
    fig.savefig(out / "fig_dashboard_manager.png", dpi=150)
    plt.close(fig)

    flags = intrusion_flags(frames["pressure_m"])
    t = np.asarray(meta["times_s"]) / 3600.0
    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    node = leaks[0]
    ax.plot(t, frames["pressure_m"][node], color="#1f4e79", lw=1.4, label=node)
    ax.axhline(DEFAULT_INTRUSION_THRESHOLD_M, color="#8e44ad", ls="--", label="7 m prior")
    ax.fill_between(t, 0, 8, where=flags[node].to_numpy(), color="#f5b7b1", alpha=0.5, label="below prior")
    ax.set_xlabel("hour")
    ax.set_ylabel("pressure (m)")
    ax.set_title(f"Health view · intrusion windows at {node} · {sid}")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out / "fig_dashboard_health.png", dpi=150)
    plt.close(fig)
    print("wrote crew/manager/health figures for", sid)


if __name__ == "__main__":
    main()
