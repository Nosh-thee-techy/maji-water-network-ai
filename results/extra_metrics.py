"""Intrusion-window and reconstruction extras from the 48 h library."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from dashboard.views import DEFAULT_INTRUSION_THRESHOLD_M, intrusion_flags, intrusion_summary
from sim.io import load_scenario
from sim.schedule import is_supply_open


def main() -> None:
    data_dir = Path("data/scenarios")
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    off_flag_hours = []
    on_flag_hours = []
    leak_on_low = 0
    leak_n = 0
    for row in index["scenarios"]:
        meta, frames = load_scenario(data_dir, row["scenario_id"])
        flags = intrusion_flags(frames["pressure_m"], threshold_m=DEFAULT_INTRUSION_THRESHOLD_M)
        times = meta["times_s"]
        off = np.array([not is_supply_open(t) for t in times])
        on = ~off
        off_flag_hours.append(float(flags.to_numpy()[off].mean() * (off.sum() * 5 / 60.0)))
        on_share = float(flags.to_numpy()[on].mean()) if on.any() else 0.0
        on_flag_hours.append(on_share)
        if meta["leaks"]:
            leak_n += 1
            node = meta["leaks"][0]["node"]
            p_on = frames["pressure_m"][node].to_numpy()[on]
            if (p_on < DEFAULT_INTRUSION_THRESHOLD_M).any():
                leak_on_low += 1
    out = {
        "threshold_m": DEFAULT_INTRUSION_THRESHOLD_M,
        "note": (
            "Off-window pressure is clamped to 0 m (drained), so the off-window "
            "intrusion flag is identically true. The non-trivial number is the "
            "share of *in-window* node-steps below the 7 m prior."
        ),
        "mean_offwindow_flagged_node_hours": float(np.mean(off_flag_hours)),
        "mean_inwindow_node_step_share_below_prior": float(np.mean(on_flag_hours)),
        "frac_leaks_with_any_inwindow_P_below_prior": leak_on_low / max(leak_n, 1),
        "n": len(index["scenarios"]),
    }
    Path("results/intrusion_metrics.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
