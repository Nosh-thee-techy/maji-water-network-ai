"""Save / load scenario records (JSON metadata + NPZ arrays)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sim.leaks import Leak
from sim.scenario import Scenario


def scenario_to_meta(sc: Scenario) -> dict[str, Any]:
    return {
        "scenario_id": sc.scenario_id,
        "seed": sc.seed,
        "fill_minutes": sc.fill_minutes,
        "duration_h": sc.duration_h,
        "timestep_s": sc.timestep_s,
        "meter_bias": sc.meter_bias,
        "unmetered_share": sc.unmetered_share,
        "leaks": [
            {
                "node": lk.node,
                "fraction": lk.fraction,
                "emitter_coeff": lk.emitter_coeff,
                "q_ref_lps": lk.q_ref_lps,
            }
            for lk in sc.leaks
        ],
        "n_leaks": len(sc.leaks),
        "water_balance_m3": sc.water_balance_m3,
        "times_s": sc.times_s,
    }


def save_scenario(sc: Scenario, directory: Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    meta_path = directory / f"{sc.scenario_id}.json"
    npz_path = directory / f"{sc.scenario_id}.npz"
    meta_path.write_text(json.dumps(scenario_to_meta(sc), indent=2), encoding="utf-8")
    np.savez_compressed(
        npz_path,
        times_s=np.asarray(sc.times_s, dtype=np.int32),
        pressure_m=sc.pressure_m.to_numpy(dtype=np.float32),
        pressure_raw_m=sc.pressure_raw_m.to_numpy(dtype=np.float32),
        head_m=sc.head_m.to_numpy(dtype=np.float32),
        customer_lps=sc.customer_lps.to_numpy(dtype=np.float32),
        inlet_flow_lps=sc.inlet_flow_lps.to_numpy(dtype=np.float32),
        junction_names=np.asarray(sc.pressure_m.columns.to_list()),
        leak_nodes=np.asarray([lk.node for lk in sc.leaks]),
        leak_lps=sc.leak_lps.to_numpy(dtype=np.float32)
        if len(sc.leak_lps.columns)
        else np.zeros((len(sc.times_s), 0), dtype=np.float32),
    )
    return meta_path


def load_scenario(directory: Path, scenario_id: str) -> tuple[dict, dict[str, pd.DataFrame | pd.Series]]:
    directory = Path(directory)
    meta = json.loads((directory / f"{scenario_id}.json").read_text(encoding="utf-8"))
    blob = np.load(directory / f"{scenario_id}.npz", allow_pickle=False)
    names = [str(x) for x in blob["junction_names"]]
    times = blob["times_s"]
    frames = {
        "pressure_m": pd.DataFrame(blob["pressure_m"], index=times, columns=names),
        "pressure_raw_m": pd.DataFrame(blob["pressure_raw_m"], index=times, columns=names),
        "head_m": pd.DataFrame(blob["head_m"], index=times, columns=names),
        "customer_lps": pd.DataFrame(blob["customer_lps"], index=times, columns=names),
        "inlet_flow_lps": pd.Series(blob["inlet_flow_lps"], index=times, name="inlet_flow_lps"),
    }
    leak_nodes = [str(x) for x in blob["leak_nodes"]]
    frames["leak_lps"] = pd.DataFrame(blob["leak_lps"], index=times, columns=leak_nodes)
    return meta, frames


def reconstruct_leaks(meta: dict) -> list[Leak]:
    return [
        Leak(
            node=row["node"],
            fraction=row["fraction"],
            emitter_coeff=row["emitter_coeff"],
            q_ref_lps=row.get("q_ref_lps", 0.0),
        )
        for row in meta["leaks"]
    ]
