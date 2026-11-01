"""Re-score the hook under the IWS duty-cycle observation model.

The 300 × 48 h library numbers in RESULTS.md used i.i.d. 3% dropouts.
This runner builds a live 12 h mixed-fill set and observes it the way
a chamber logger uplinks (sleep off-window, dense after t_sat).

    python -m results.duty_eval
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from baseline.emitter_calibrate import estimate_leaks
from baseline.evaluate import build_noleak_and_sensitivity
from baseline.graph_distance import match_leaks, pipe_graph
from placement.greedy import greedy_place
from sim.generate import generate_one
from sim.network import JUNCTION_NAMES
from sim.observe import make_observations, valve_open_for_solver

N = 24
DURATION_H = 12.0
BUDGET = 10
SEED = 2026
OUT = Path("results/duty_cycle_eval.json")


def run(n: int = N, duration_h: float = DURATION_H) -> dict:
    print(f"duty-cycle eval: {n} live {duration_h} h mixed-fill scenarios")
    pack = build_noleak_and_sensitivity(duration_h)
    sensors = greedy_place(pack["signatures"], pack["junctions"], BUDGET)
    graph = pipe_graph()
    rows = []
    for i in range(n):
        sc = generate_one(i, SEED + 100 + i, duration_h, fill_minutes=None)
        obs = make_observations(
            sc.pressure_m,
            sc.inlet_flow_lps,
            sensors,
            seed=sc.seed + BUDGET,
            duration_h=sc.duration_h,
        )
        p0 = pack["noleak"].pressure_m.reindex(sc.times_s).interpolate().bfill().ffill()
        q0 = pack["noleak"].inlet_flow_lps.reindex(sc.times_s).interpolate().bfill().ffill()
        est = estimate_leaks(
            pressure_obs=obs["pressure_m"].to_numpy(dtype=float),
            inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
            sensors=sensors,
            times_s=np.asarray(sc.times_s),
            p_noleak=p0[list(JUNCTION_NAMES)].to_numpy(dtype=float),
            inlet_noleak_lps=q0.to_numpy(dtype=float),
            sensitivity=pack["signatures"],
            candidate_nodes=pack["leak_nodes"],
            duration_h=sc.duration_h,
            valve_open=valve_open_for_solver(obs),
        )
        truth = [lk.node for lk in sc.leaks]
        pred = [n_ for n_, _ in est.ranked[: max(1, len(truth))]] if est.detected else []
        loc = match_leaks(pred, truth, graph)
        rows.append(
            {
                "id": sc.scenario_id,
                "fill_minutes": sc.fill_minutes,
                "n_true": len(truth),
                "detected": est.detected,
                "event": est.event,
                "used_change_point": est.used_change_point,
                "q_total_lps": est.q_total_lps,
                "leftover_m3_per_day": est.leftover_m3_per_day,
                "hops": loc["mean_hops"],
                "duty_cycle": bool(obs["duty_cycle"]),
            }
        )
        print(f"  {sc.scenario_id} fill={sc.fill_minutes:.0f} leaks={len(truth)} event={est.event} hops={loc['mean_hops']}")

    zero = [r for r in rows if r["n_true"] == 0]
    leaked = [r for r in rows if r["n_true"] > 0]
    hops = [r["hops"] for r in leaked if r["detected"]]
    summary = {
        "observation_model": "iws_duty_cycle",
        "n": n,
        "duration_h": duration_h,
        "budget": BUDGET,
        "sensors": sensors,
        "mixed_fill": True,
        "n_zero": len(zero),
        "n_leak": len(leaked),
        "false_positive_rate": sum(1 for r in zero if r["detected"]) / max(len(zero), 1),
        "true_positive_rate": sum(1 for r in leaked if r["detected"]) / max(len(leaked), 1),
        "mean_hops_detected": float(np.mean(hops)) if hops else None,
        "frac_within_3_hops_detected": sum(1 for h in hops if h <= 3) / max(len(hops), 1),
        "frac_used_change_point": sum(1 for r in rows if r["used_change_point"]) / max(len(rows), 1),
        "label": "simulated, duty-cycle observations, mixed fill 45–150 min",
        "rows": rows,
    }
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))
    print(f"wrote {OUT}")
    return summary


if __name__ == "__main__":
    run()
