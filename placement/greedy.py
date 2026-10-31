"""Greedy placement: maximise the minimum pairwise leak-signature distance.

A leak signature is the vector of nodal pressure *changes* (vs a no-leak
run) averaged over the first supply-window fill period, for a reference
orifice of 1.5 L/s at 20 m. Sensors are chosen one at a time so that the
smallest Euclidean distance between any two signatures, restricted to the
chosen sites, is maximised.

Re-run for budgets 5 / 10 / 15 / 20. The inlet flow meter is assumed
present regardless of the pressure-sensor budget.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from sim.leaks import leaks_from_q_lps
from sim.network import JUNCTION_NAMES, build_dma, customer_junctions
from sim.scenario import run_scenario


REFERENCE_Q_LPS = 1.5
FILL_START_S = 5 * 3600
FILL_END_S = FILL_START_S + 75 * 60
BUDGETS = (5, 10, 15, 20)


def _fill_mean_pressure(sc) -> np.ndarray:
    times = [t for t in sc.times_s if FILL_START_S <= t < FILL_END_S]
    return sc.pressure_m.loc[times, list(JUNCTION_NAMES)].mean(axis=0).to_numpy(dtype=float)


def compute_signatures(duration_h: float = 12.0) -> dict:
    wn = build_dma()
    nodes = list(customer_junctions())
    baseline = run_scenario(scenario_id="place-base", leaks=[], duration_h=duration_h)
    p0 = _fill_mean_pressure(baseline)
    sigs = []
    for node in nodes:
        leaks = leaks_from_q_lps(wn, [(node, REFERENCE_Q_LPS)])
        sc = run_scenario(scenario_id=f"place-{node}", leaks=leaks, duration_h=duration_h)
        sigs.append(_fill_mean_pressure(sc) - p0)
        print(f"  signature {node}  ||dP||={np.linalg.norm(sigs[-1]):.3f} m")
    return {
        "leak_nodes": nodes,
        "junctions": list(JUNCTION_NAMES),
        "signatures": np.asarray(sigs, dtype=float),  # [n_leak, n_junc]
        "baseline_pressure_m": p0,
    }


def _min_pairwise(sigs: np.ndarray) -> float:
    n = sigs.shape[0]
    if n < 2:
        return 0.0
    best = np.inf
    for i in range(n):
        d = np.linalg.norm(sigs[i + 1 :] - sigs[i], axis=1)
        if len(d):
            best = min(best, float(d.min()))
    return 0.0 if np.isinf(best) else best


def greedy_place(signatures: np.ndarray, junctions: list[str], budget: int) -> list[str]:
    remaining = list(range(len(junctions)))
    chosen: list[int] = []
    # Seed with the junction whose signatures have the largest spread.
    spread = signatures.std(axis=0)
    first = int(remaining[int(np.argmax(spread[remaining]))])
    chosen.append(first)
    remaining.remove(first)
    while len(chosen) < min(budget, len(junctions)):
        best_j = remaining[0]
        best_score = -1.0
        for j in remaining:
            cols = chosen + [j]
            score = _min_pairwise(signatures[:, cols])
            if score > best_score:
                best_score = score
                best_j = j
        chosen.append(best_j)
        remaining.remove(best_j)
    return [junctions[j] for j in chosen]


def place_sensors(budgets: tuple[int, ...] = BUDGETS, duration_h: float = 12.0) -> dict:
    pack = compute_signatures(duration_h=duration_h)
    placements = {}
    for b in budgets:
        b = min(int(b), len(pack["junctions"]))
        chosen = greedy_place(pack["signatures"], pack["junctions"], b)
        score = _min_pairwise(
            pack["signatures"][:, [pack["junctions"].index(s) for s in chosen]]
        )
        placements[str(b)] = {"sensors": chosen, "min_pairwise_m": score}
        print(f"budget {b:2d}: {chosen}  min-pairwise={score:.3f} m")
    return {
        "reference_q_lps": REFERENCE_Q_LPS,
        "leak_nodes": pack["leak_nodes"],
        "junctions": pack["junctions"],
        "placements": placements,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("results/placement.json"))
    p.add_argument("--duration-h", type=float, default=12.0)
    args = p.parse_args()
    result = place_sensors(duration_h=args.duration_h)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # drop numpy
    payload = {k: v for k, v in result.items()}
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
