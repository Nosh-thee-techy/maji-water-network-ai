"""Same engine on an always-pressurised copy of our DMA.

This is NOT BattLeDIM / LeakDB. It only supports the claim that the
emitter-calibration baseline still detects leaks when the network never
drains. Label results 'continuous-supply variant (same topology)'.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from baseline.emitter_calibrate import estimate_leaks
from baseline.graph_distance import match_leaks, pipe_graph
from placement.greedy import compute_signatures, greedy_place
from sim.io import save_scenario
from sim.leaks import leaks_from_q_lps
from sim.network import JUNCTION_NAMES, build_dma, customer_junctions
from sim.observe import make_observations
from sim.scenario import run_scenario


def generate_continuous(n: int, out_dir: Path, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    wn = build_dma()
    nodes = list(customer_junctions())
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for i in range(n):
        if rng.random() < 0.2:
            leaks = []
        else:
            node = str(rng.choice(nodes))
            leaks = leaks_from_q_lps(wn, [(node, float(rng.uniform(0.8, 3.0)))])
        sc = run_scenario(
            scenario_id=f"c{i:04d}",
            seed=seed + i,
            leaks=leaks,
            duration_h=24,
            continuous=True,
        )
        save_scenario(sc, out_dir)
        index.append({"scenario_id": sc.scenario_id, "n_leaks": len(leaks), "leak_nodes": [lk.node for lk in leaks], "water_balance_m3": sc.water_balance_m3})
    (out_dir / "index.json").write_text(
        json.dumps({"summary": {"n": n, "mode": "continuous"}, "scenarios": index}, indent=2),
        encoding="utf-8",
    )


def evaluate_continuous(data_dir: Path, out: Path) -> dict:
    from sim.io import load_scenario

    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    pack = compute_signatures(duration_h=12.0)
    sensors = greedy_place(pack["signatures"], pack["junctions"], 10)
    noleak = run_scenario(scenario_id="c-noleak", leaks=[], duration_h=24, continuous=True)
    graph = pipe_graph()
    rows = []
    for row in index["scenarios"]:
        meta, frames = load_scenario(data_dir, row["scenario_id"])
        obs = make_observations(frames["pressure_m"], frames["inlet_flow_lps"], sensors, seed=meta["seed"])
        times = meta["times_s"]
        p0 = noleak.pressure_m.reindex(times).interpolate().bfill().ffill()
        q0 = noleak.inlet_flow_lps.reindex(times).interpolate().bfill().ffill()
        est = estimate_leaks(
            pressure_obs=obs["pressure_m"].to_numpy(dtype=float),
            inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
            sensors=sensors,
            times_s=np.asarray(times),
            p_noleak=p0[list(JUNCTION_NAMES)].to_numpy(dtype=float),
            inlet_noleak_lps=q0.to_numpy(dtype=float),
            sensitivity=pack["signatures"],
            candidate_nodes=pack["leak_nodes"],
            duration_h=24.0,
        )
        truth = [lk["node"] for lk in meta["leaks"]]
        pred = [n for n, _ in est.ranked[: max(1, len(truth))]] if est.detected else []
        loc = match_leaks(pred, truth, graph)
        rows.append({"id": row["scenario_id"], "n_true": len(truth), "detected": est.detected, "hops": loc["mean_hops"]})
    leaked = [r for r in rows if r["n_true"] > 0]
    zero = [r for r in rows if r["n_true"] == 0]
    hops = [r["hops"] for r in leaked if r["detected"]]
    summary = {
        "label": "continuous-supply variant (same topology) — not BattLeDIM/LeakDB",
        "n": len(rows),
        "false_positive_rate": sum(1 for r in zero if r["detected"]) / max(len(zero), 1),
        "true_positive_rate": sum(1 for r in leaked if r["detected"]) / max(len(leaked), 1),
        "mean_hops_detected": float(np.mean(hops)) if hops else None,
        "sensors": sensors,
        "rows": rows,
    }
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--data", type=Path, default=Path("data/continuous"))
    p.add_argument("--out", type=Path, default=Path("results/continuous_eval.json"))
    args = p.parse_args()
    generate_continuous(args.n, args.data)
    evaluate_continuous(args.data, args.out)


if __name__ == "__main__":
    main()
