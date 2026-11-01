"""Tiny scenario pack the dashboard can open without the 300-row library.

    python -m sim.demo_library
"""

from __future__ import annotations

import json
from pathlib import Path

from sim.io import save_scenario
from sim.leaks import leaks_from_q_lps
from sim.network import build_dma
from sim.scenario import run_scenario

DEFAULT_OUT = Path("results/demo")
DURATION_H = 12.0


def _valve_never_opened(sc):
    """Scheduled window, no fill surge — detector should say valve_did_not_open."""
    sc.inlet_flow_lps.loc[:] = 0.0
    sc.pressure_m.loc[:, :] = 0.0
    sc.pressure_raw_m.loc[:, :] = 0.0
    return sc


def write_demo(out_dir: Path = DEFAULT_OUT) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wn = build_dma()
    leak = leaks_from_q_lps(wn, [("J07", 1.5)])
    specs = [
        ("demo-clean", "Clean window — tanks fill, no leftover", [], 75.0, False),
        ("demo-leak", "Leak — 1.5 L/s leftover at J07", leak, 75.0, False),
        ("demo-longfill", "Long fill — 120 min tanks, same leak", leak, 120.0, False),
        ("demo-valve", "Valve did not open — no fill surge", [], 75.0, True),
    ]
    index = []
    for sid, label, leaks, fill, dead in specs:
        sc = run_scenario(
            scenario_id=sid,
            seed=2026,
            leaks=leaks,
            unmetered_share={"J01": 0.30} if sid == "demo-leak" else {},
            meter_bias=0.04,
            fill_minutes=fill,
            duration_h=DURATION_H,
        )
        if dead:
            sc = _valve_never_opened(sc)
        save_scenario(sc, out_dir)
        index.append(
            {
                "scenario_id": sid,
                "label": label,
                "seed": sc.seed,
                "n_leaks": len(sc.leaks),
                "leak_nodes": [lk.node for lk in sc.leaks],
                "fill_minutes": sc.fill_minutes,
                "water_balance_m3": sc.water_balance_m3,
            }
        )
        print(f"  {sid}: {label}")
    summary = {
        "n": len(index),
        "duration_h": DURATION_H,
        "purpose": "dashboard demo — not the 300-scenario library",
        "out_dir": str(out_dir),
    }
    (out_dir / "index.json").write_text(
        json.dumps({"summary": summary, "scenarios": index}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {len(index)} demo scenarios to {out_dir}")
    return summary


def ensure_demo_library(out_dir: Path = DEFAULT_OUT) -> Path:
    out_dir = Path(out_dir)
    if (out_dir / "index.json").exists():
        return out_dir
    write_demo(out_dir)
    return out_dir


def main() -> None:
    write_demo(DEFAULT_OUT)


if __name__ == "__main__":
    main()
