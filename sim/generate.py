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
# Field tanks do not all fill in 75 minutes. 150 min still leaves 90 min
# of after-fill in a 4-hour window (enough for the leftover hold).
FILL_MINUTE_CHOICES = (45, 60, 75, 90, 120, 150)


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


def generate_one(
    index: int,
    seed: int,
    duration_h: float,
    fill_minutes: float | None = None,
):
    rng = np.random.default_rng(seed)
    wn = build_dma()
    nodes = list(customer_junctions())
    leaks = _draw_leaks(rng, wn, nodes)
    unmetered = _draw_unmetered(rng, nodes)
    bias = float(rng.uniform(0.02, 0.06))
    if fill_minutes is None:
        fill_minutes = float(rng.choice(FILL_MINUTE_CHOICES))
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
    fill_minutes: float | None = None,
    mixed_fill: bool = True,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    n_zero = 0
    for i in range(n):
        fill = None if mixed_fill else (fill_minutes if fill_minutes is not None else DEFAULT_FILL_MINUTES)
        sc = generate_one(i, seed + i, duration_h, fill)
        save_scenario(sc, out_dir)
        rec = {
            "scenario_id": sc.scenario_id,
            "seed": sc.seed,
            "n_leaks": len(sc.leaks),
            "leak_nodes": [lk.node for lk in sc.leaks],
            "fill_minutes": sc.fill_minutes,
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
        "mixed_fill": mixed_fill,
        "fill_minute_choices": list(FILL_MINUTE_CHOICES) if mixed_fill else [fill_minutes or DEFAULT_FILL_MINUTES],
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
    p.add_argument("--fill-minutes", type=float, default=None, help="Fix fill minutes. Default: mix 45–150.")
    p.add_argument("--fixed-fill", action="store_true", help="Use 75 min (or --fill-minutes) for every scenario.")
    args = p.parse_args()
    generate_library(
        args.n,
        out_dir=args.out,
        seed=args.seed,
        duration_h=args.duration_h,
        fill_minutes=args.fill_minutes,
        mixed_fill=not args.fixed_fill,
    )


if __name__ == "__main__":
    main()
