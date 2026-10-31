"""Offline samples from the cached scenario library. No EPANET here."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from model.graph import build_graph
from sim.io import load_scenario
from sim.observe import make_observations
from sim.schedule import expand_windows


def _window_flags(times: list[int], duration_h: float) -> tuple[np.ndarray, np.ndarray]:
    fill = np.zeros(len(times), dtype=np.float32)
    after = np.zeros(len(times), dtype=np.float32)
    for open_s, close_s in expand_windows(duration_h):
        for i, t in enumerate(times):
            if open_s <= t < close_s:
                if (t - open_s) < 75 * 60:
                    fill[i] = 1.0
                else:
                    after[i] = 1.0
    return fill, after


def load_split(data_dir: Path, seed: int = 0) -> dict[str, list[str]]:
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    ids = [row["scenario_id"] for row in index["scenarios"]]
    rng = np.random.default_rng(seed)
    rng.shuffle(ids)
    n = len(ids)
    n_train = int(0.70 * n)
    n_val = int(0.15 * n)
    return {
        "train": ids[:n_train],
        "val": ids[n_train : n_train + n_val],
        "test": ids[n_train + n_val :],
    }


def scenario_tensors(
    data_dir: Path,
    scenario_id: str,
    sensors: list[str],
    obs_seed: int,
) -> dict:
    meta, frames = load_scenario(data_dir, scenario_id)
    g = build_graph()
    names = g["names"]
    times = meta["times_s"]
    fill, after = _window_flags(times, meta["duration_h"])
    supply = (fill + after) > 0
    obs = make_observations(
        frames["pressure_m"],
        frames["inlet_flow_lps"],
        sensors,
        seed=obs_seed,
    )
    p_true = frames["pressure_m"][names].to_numpy(dtype=np.float32)
    p_obs = obs["pressure_m"]
    leak = np.zeros_like(p_true)
    for node in frames["leak_lps"].columns:
        leak[:, names.index(node)] = frames["leak_lps"][node].to_numpy(dtype=np.float32)
    demand = frames["customer_lps"][names].to_numpy(dtype=np.float32)
    inlet = obs["inlet_flow_lps"].to_numpy(dtype=np.float32)
    is_sensor = np.array([1.0 if n in sensors else 0.0 for n in names], dtype=np.float32)
    # pack only supply-window rows
    xs, ys_p, ys_q, ys_d = [], [], [], []
    for i, keep in enumerate(supply):
        if not keep:
            continue
        p_row = np.zeros(len(names), dtype=np.float32)
        miss = np.ones(len(names), dtype=np.float32)
        for j, n in enumerate(names):
            if n in sensors:
                val = p_obs[n].iloc[i]
                if np.isfinite(val):
                    p_row[j] = val / 30.0
                    miss[j] = 0.0
        inlet_i = inlet[i] if np.isfinite(inlet[i]) else 0.0
        dyn = np.stack(
            [
                is_sensor,
                p_row,
                miss,
                np.full(len(names), fill[i]),
                np.full(len(names), after[i]),
                np.full(len(names), inlet_i / 10.0),
            ],
            axis=1,
        )
        x = np.concatenate([g["node_static"].numpy(), dyn], axis=1)
        xs.append(x)
        ys_p.append(p_true[i])
        ys_q.append(leak[i])
        ys_d.append(demand[i])
    return {
        "x": torch.tensor(np.stack(xs), dtype=torch.float32),
        "p": torch.tensor(np.stack(ys_p), dtype=torch.float32),
        "q": torch.tensor(np.stack(ys_q), dtype=torch.float32),
        "d": torch.tensor(np.stack(ys_d), dtype=torch.float32),
        "meta": meta,
    }
