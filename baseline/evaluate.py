"""Evaluate the emitter-calibration baseline on a scenario library."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from baseline.emitter_calibrate import estimate_leaks
from baseline.graph_distance import match_leaks, pipe_graph
from placement.greedy import REFERENCE_Q_LPS, compute_signatures, greedy_place
from sim.io import load_scenario
from sim.network import JUNCTION_NAMES
from sim.observe import make_observations, valve_open_for_solver
from sim.scenario import run_scenario


def build_noleak_and_sensitivity(duration_h: float) -> dict:
    pack = compute_signatures(duration_h=min(duration_h, 12.0))
    noleak = run_scenario(scenario_id="noleak-ref", leaks=[], duration_h=duration_h)
    return {
        "signatures": pack["signatures"],
        "leak_nodes": pack["leak_nodes"],
        "junctions": pack["junctions"],
        "noleak": noleak,
    }


def _align_noleak(noleak, times_s: list[int]):
    """Reindex the no-leak fields onto a scenario's time grid."""
    p = noleak.pressure_m.reindex(times_s).interpolate().bfill().ffill()
    q = noleak.inlet_flow_lps.reindex(times_s).interpolate().bfill().ffill()
    return p[list(JUNCTION_NAMES)].to_numpy(dtype=float), q.to_numpy(dtype=float)


def evaluate_library(
    data_dir: Path,
    *,
    budgets: tuple[int, ...] = (5, 10, 15, 20),
    duration_h: float = 48.0,
    max_scenarios: int | None = None,
) -> dict:
    data_dir = Path(data_dir)
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    ids = [row["scenario_id"] for row in index["scenarios"]]
    if max_scenarios:
        ids = ids[: max_scenarios]
    print(f"building sensitivity / no-leak reference ({duration_h} h)…")
    pack = build_noleak_and_sensitivity(duration_h)
    graph = pipe_graph()
    placements = {}
    for b in budgets:
        chosen = greedy_place(pack["signatures"], pack["junctions"], b)
        placements[b] = chosen
        print(f"  budget {b}: {chosen}")

    by_budget: dict[int, list[dict]] = defaultdict(list)
    for sid in ids:
        meta, frames = load_scenario(data_dir, sid)
        times = meta["times_s"]
        p0, q0 = _align_noleak(pack["noleak"], times)
        truth_nodes = [lk["node"] for lk in meta["leaks"]]
        for b, sensors in placements.items():
            obs = make_observations(
                frames["pressure_m"],
                frames["inlet_flow_lps"],
                sensors,
                seed=meta["seed"] + 17 * b,
                duration_h=meta["duration_h"],
            )
            p_obs = obs["pressure_m"].to_numpy(dtype=float)
            q_obs = obs["inlet_flow_lps"].to_numpy(dtype=float)
            est = estimate_leaks(
                pressure_obs=p_obs,
                inlet_obs_lps=q_obs,
                sensors=sensors,
                times_s=np.asarray(times),
                p_noleak=p0,
                inlet_noleak_lps=q0,
                sensitivity=pack["signatures"],
                candidate_nodes=pack["leak_nodes"],
                duration_h=meta["duration_h"],
                valve_open=valve_open_for_solver(obs),
            )
            pred_nodes = [n for n, _v in est.ranked[: max(1, len(truth_nodes))]] if est.detected else []
            if est.detected and not truth_nodes:
                pred_nodes = [est.ranked[0][0]] if est.ranked else ["J05"]
            loc = match_leaks(pred_nodes, truth_nodes, graph)
            supplied = meta["water_balance_m3"]["supplied"]
            leaked_true = meta["water_balance_m3"]["leaked"]
            # Estimated leak volume: q_total (L/s) × pressurised seconds.
            # Four 4-hour windows in 48 h → 16 h pressurised. Use inlet>0 mask.
            inlet = frames["inlet_flow_lps"].to_numpy(dtype=float)
            press_s = float(np.sum(inlet > 0.05) * meta["timestep_s"])
            leaked_hat = est.q_total_lps * press_s / 1000.0
            leak_pp_true = 100.0 * leaked_true / supplied if supplied else 0.0
            leak_pp_hat = 100.0 * leaked_hat / supplied if supplied else 0.0
            by_budget[b].append(
                {
                    "id": sid,
                    "n_true": len(truth_nodes),
                    "detected": est.detected,
                    "q_total_lps": est.q_total_lps,
                    "hops": loc["mean_hops"],
                    "perfect": loc["perfect"],
                    "leak_pp_true": leak_pp_true,
                    "leak_pp_hat": leak_pp_hat,
                    "pred": pred_nodes,
                    "true": truth_nodes,
                }
            )
        print(f"  evaluated {sid}")

    summary = {"budgets": {}, "n_scenarios": len(ids)}
    for b, rows in by_budget.items():
        zero = [r for r in rows if r["n_true"] == 0]
        leaked = [r for r in rows if r["n_true"] > 0]
        fp = sum(1 for r in zero if r["detected"]) / max(len(zero), 1)
        tp = sum(1 for r in leaked if r["detected"]) / max(len(leaked), 1)
        hops = [r["hops"] for r in leaked if r["detected"]]
        hops_all = [r["hops"] for r in leaked]
        within3 = sum(1 for h in hops if h <= 3) / max(len(hops), 1)
        pp_err = [abs(r["leak_pp_hat"] - r["leak_pp_true"]) for r in rows]
        summary["budgets"][str(b)] = {
            "sensors": placements[b],
            "n": len(rows),
            "n_zero": len(zero),
            "n_leak": len(leaked),
            "false_positive_rate": fp,
            "true_positive_rate": tp,
            "mean_hops_detected": float(np.mean(hops)) if hops else None,
            "mean_hops_all_leaks": float(np.mean(hops_all)) if hops_all else None,
            "frac_within_3_hops_detected": within3,
            "median_leak_pp_abs_error": float(np.median(pp_err)),
            "mean_leak_pp_abs_error": float(np.mean(pp_err)),
        }
    summary["rows"] = {str(b): by_budget[b] for b in by_budget}
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data/scenarios"))
    p.add_argument("--out", type=Path, default=Path("results/baseline_eval.json"))
    p.add_argument("--duration-h", type=float, default=48.0)
    p.add_argument("--max", type=int, default=0)
    args = p.parse_args()
    summary = evaluate_library(
        args.data,
        duration_h=args.duration_h,
        max_scenarios=args.max or None,
    )
    # Drop per-row dump from the printed file? keep it — report needs numbers.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["budgets"], indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
