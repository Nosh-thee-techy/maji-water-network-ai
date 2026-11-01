"""t_sat vs true fill minutes — the clock is not the field.

    python -m results.mixed_fill
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from baseline.saturation import detect_saturation
from sim.demand import DEFAULT_FILL_MINUTES
from sim.leaks import leaks_from_q_lps
from sim.network import build_dma
from sim.scenario import run_scenario

FILLS = (45, 60, 75, 90, 120, 150)
DURATION_H = 12.0
OUT = Path("results/mixed_fill.json")
FIG = Path("results/figures/fig_tsat_vs_fill.png")


def _t_sat_hours(sc) -> float | None:
    q = sc.inlet_flow_lps.to_numpy(dtype=float)
    times = np.asarray(sc.times_s, dtype=float)
    sat = detect_saturation(times, q, sc.duration_h)
    ts = [w.t_sat_s for w in sat.windows if w.t_sat_s is not None]
    if not ts:
        return None
    return float(ts[0]) / 3600.0


def run() -> dict:
    wn = build_dma()
    leak = leaks_from_q_lps(wn, [("J07", 1.5)])
    rows = []
    for fill in FILLS:
        none = run_scenario(scenario_id=f"fill-{fill}-none", leaks=[], fill_minutes=fill, duration_h=DURATION_H)
        hit = run_scenario(scenario_id=f"fill-{fill}-leak", leaks=leak, fill_minutes=fill, duration_h=DURATION_H)
        t0 = _t_sat_hours(none)
        t1 = _t_sat_hours(hit)
        true_h = 5.0 + fill / 60.0
        rows.append(
            {
                "fill_minutes": fill,
                "true_sat_h": true_h,
                "t_sat_noleak_h": t0,
                "t_sat_leak_h": t1,
                "clock_75_h": 5.0 + DEFAULT_FILL_MINUTES / 60.0,
                "err_noleak_min": None if t0 is None else (t0 - true_h) * 60,
                "err_leak_min": None if t1 is None else (t1 - true_h) * 60,
                "clock_err_min": (DEFAULT_FILL_MINUTES - fill),
            }
        )
        print(f"  fill={fill:3d}  true={true_h:.2f}  t_sat none/leak={t0} / {t1}")
    payload = {"duration_h": DURATION_H, "fills": list(FILLS), "rows": rows, "label": "simulated"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _plot(rows)
    return payload


def _plot(rows: list[dict]) -> None:
    fills = [r["fill_minutes"] for r in rows]
    true = [r["true_sat_h"] for r in rows]
    none = [r["t_sat_noleak_h"] for r in rows]
    leak = [r["t_sat_leak_h"] for r in rows]
    clock = [r["clock_75_h"] for r in rows]
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(fills, true, "k-", marker="o", label="true fill end")
    ax.plot(fills, none, "C0--", marker="s", label="t_sat, no leak")
    ax.plot(fills, leak, "C3--", marker="^", label="t_sat, 1.5 L/s at J07")
    ax.plot(fills, clock, color="0.5", linestyle=":", label="75-minute clock")
    ax.set_xlabel("True tank-fill minutes")
    ax.set_ylabel("Time of day (h)")
    ax.set_title("Simulated IWS — hydrograph t_sat tracks fill, the clock does not")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG, dpi=140)
    plt.close(fig)
    print(f"wrote {OUT} and {FIG}")


if __name__ == "__main__":
    run()
