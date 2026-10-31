"""Build a library of intermittent-supply scenarios.

Varies leak location / size / count (including zero leaks), unmetered
share, and meter bias. Sensor noise is NOT applied here — the full
clean field is stored so placement can re-observe at any budget.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from sim.demand import DEFAULT_FILL_MINUTES
from sim.io import save_scenario
from sim.leaks import leaks_from_q_lps
from sim.network import build_dma, customer_junctions
from sim.scenario import run_scenario
from sim.schedule import DEFAULT_DURATION_H


DEFAULT_OUT = Path("data/scenarios")


def _draw_leaks(rng: np.random.Generator, wn, nodes: list[str]) -> list:
    roll = rng.random()
    if roll < 0.20:
        count = 0
    elif roll < 0.80:
        count = 1
    else:
        count = 2
    if count == 0:
        return []
    chosen = rng.choice(nodes, size=count, replace=False)
    # 0.5–2.5 L/s at 20 m ≈ 9–45% of peak DMA inflow (~5.6 L/s).
    # Below ~0.5 L/s the pressure residual on this DMA is < sensor noise.
    spec = [(str(n), float(rng.uniform(0.80, 3.00))) for n in chosen]
    return leaks_from_q_lps(wn, spec)


def _draw_unmetered(rng: np.random.Generator, nodes: list[str]) -> dict[str, float]:
    k = int(rng.integers(0, 5))
    if k == 0:
        return {}
    chosen = rng.choice(nodes, size=k, replace=False)
    return {str(n): float(rng.uniform(0.20, 0.80)) for n in chosen}


def generate_one(index: int, seed: int, duration_h: float, fill_minutes: float):
    rng = np.random.default_rng(seed)
    wn = build_dma()
    nodes = list(customer_junctions())
    leaks = _draw_leaks(rng, wn, nodes)
    unmetered = _draw_unmetered(rng, nodes)
    bias = float(rng.uniform(0.02, 0.06))
    sid = f"s{index:04d}"
    return run_scenario(
        scenario_id=sid,
        seed=seed,
        leaks=leaks,
        unmetered_share=unmetered,
        meter_bias=bias,
        fill_minutes=fill_minutes,
        duration_h=duration_h,
    )


def generate_library(
    n: int = 300,
    *,
    out_dir: Path = DEFAULT_OUT,
    seed: int = 2026,
    duration_h: float = DEFAULT_DURATION_H,
    fill_minutes: float = DEFAULT_FILL_MINUTES,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    n_zero = 0
    for i in range(n):
        sc = generate_one(i, seed + i, duration_h, fill_minutes)
        save_scenario(sc, out_dir)
        rec = {
            "scenario_id": sc.scenario_id,
            "seed": sc.seed,
            "n_leaks": len(sc.leaks),
            "leak_nodes": [lk.node for lk in sc.leaks],
            "water_balance_m3": sc.water_balance_m3,
        }
        index.append(rec)
        if len(sc.leaks) == 0:
            n_zero += 1
        if (i + 1) % 25 == 0 or i == 0:
            print(f"  generated {i+1}/{n}  last={sc.scenario_id} leaks={len(sc.leaks)}")
    summary = {
        "n": n,
        "n_zero_leak": n_zero,
        "seed": seed,
        "duration_h": duration_h,
        "fill_minutes": fill_minutes,
        "out_dir": str(out_dir),
    }
    (out_dir / "index.json").write_text(
        json.dumps({"summary": summary, "scenarios": index}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {n} scenarios ({n_zero} zero-leak) to {out_dir}")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Generate M.A.J.I scenario library")
    p.add_argument("-n", type=int, default=300)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--duration-h", type=float, default=DEFAULT_DURATION_H)
    p.add_argument("--fill-minutes", type=float, default=DEFAULT_FILL_MINUTES)
    args = p.parse_args()
    generate_library(
        args.n,
        out_dir=args.out,
        seed=args.seed,
        duration_h=args.duration_h,
        fill_minutes=args.fill_minutes,
    )


if __name__ == "__main__":
    main()
