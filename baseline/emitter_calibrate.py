"""Sparse emitter calibration against pressure residuals + after-fill inlet flow.

The utility model (same DMA, no leaks) predicts the pressure field and
inlet flow. After the storage-fill window, customer draw is zero, so a
non-zero inlet flow *is* leakage. That scalar is the scientific hook.
Spatial localisation then distributes that total onto nodes by matching
the observed pressure residual to a precomputed sensitivity matrix
(ΔP at sensors per 1 L/s orifice at each candidate node).

No EPANET call inside the optimiser — the sensitivity matrix is built
once offline. An L1 penalty prefers few non-zero emitters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from sim.network import JUNCTION_NAMES, customer_junctions
from sim.observe import (
    DEFAULT_DROPOUT_P,
    DEFAULT_FLOW_SIGMA_LPS,
    DEFAULT_PRESSURE_SIGMA_M,
    make_observations,
)
from sim.schedule import SUPPLY_WINDOWS_H, expand_windows


# After-fill inlet flow below this is called "no leak". 0.35 L/s is
# ~2× the flow-noise sigma and well below the smallest generated leak.
DETECT_THRESHOLD_LPS = 0.35
L1_WEIGHT = 0.15


@dataclass
class LeakEstimate:
    q_lps: dict[str, float]
    q_total_lps: float
    detected: bool
    ranked: list[tuple[str, float]]
    residual_norm_m: float


def window_slices(times: np.ndarray, duration_h: float) -> tuple[np.ndarray, np.ndarray]:
    """Boolean masks: in-window fill minutes, and in-window post-fill minutes."""
    expanded = expand_windows(duration_h, SUPPLY_WINDOWS_H)
    fill = np.zeros(len(times), dtype=bool)
    after = np.zeros(len(times), dtype=bool)
    fill_s = 75 * 60
    for open_s, close_s in expanded:
        for i, t in enumerate(times):
            if open_s <= t < close_s:
                if (t - open_s) < fill_s:
                    fill[i] = True
                else:
                    after[i] = True
    return fill, after


def nanmean(values: np.ndarray) -> float:
    v = values[np.isfinite(values)]
    if v.size == 0:
        return 0.0
    return float(v.mean())


def estimate_leaks(
    *,
    pressure_obs: np.ndarray,  # [T, n_sensors]
    inlet_obs_lps: np.ndarray,  # [T]
    sensors: list[str],
    times_s: np.ndarray,
    p_noleak: np.ndarray,  # [T, n_junctions] aligned to JUNCTION_NAMES
    inlet_noleak_lps: np.ndarray,
    sensitivity: np.ndarray,  # [n_candidates, n_junctions] dP per 1 L/s
    candidate_nodes: list[str],
    duration_h: float,
    detect_threshold_lps: float = DETECT_THRESHOLD_LPS,
    l1_weight: float = L1_WEIGHT,
) -> LeakEstimate:
    junc = list(JUNCTION_NAMES)
    sensor_idx = [junc.index(s) for s in sensors]
    fill, after = window_slices(np.asarray(times_s), duration_h)

    # Hook: after-fill inlet residual ≈ total leak (customer draw is zero).
    # Continuous-supply runs have no after-fill window — fall back to the
    # whole-horizon inlet residual against the no-leak model.
    flow_mask = after if after.any() else np.ones(len(after), dtype=bool)
    q_total = nanmean(inlet_obs_lps[flow_mask] - inlet_noleak_lps[flow_mask])
    q_total = max(0.0, q_total)
    detected = q_total >= detect_threshold_lps

    # Pressure residual during fill (richer headloss) at the sensors.
    p_mask = fill if fill.any() else flow_mask
    p_obs_fill = pressure_obs[p_mask]
    p_mod_fill = p_noleak[p_mask][:, sensor_idx]
    r = np.nanmean(p_mod_fill - p_obs_fill, axis=0)  # drop: model − obs
    r = np.nan_to_num(r, nan=0.0)

    # Sensitivity at sensors: expected drop per L/s at each candidate.
    # `sensitivity` is (P_leak - P_noleak), i.e. negative numbers. Flip to drop.
    S = -sensitivity[:, sensor_idx].T  # [S, C]
    n_c = len(candidate_nodes)

    if not detected:
        zeros = {n: 0.0 for n in candidate_nodes}
        return LeakEstimate(
            q_lps=zeros,
            q_total_lps=q_total,
            detected=False,
            ranked=[],
            residual_norm_m=float(np.linalg.norm(r)),
        )

    def objective(q: np.ndarray) -> float:
        pred = S @ q
        return float(np.sum((pred - r) ** 2) + l1_weight * np.sum(q) + 0.4 * (q.sum() - q_total) ** 2)

    q0 = np.full(n_c, q_total / n_c)
    res = minimize(
        objective,
        q0,
        method="L-BFGS-B",
        bounds=[(0.0, 8.0)] * n_c,
        options={"maxiter": 400},
    )
    q = np.clip(res.x, 0.0, None)
    # Re-sparsify: keep coefficients that explain at least 8% of total.
    thresh = max(0.08 * q.sum(), 0.15)
    q[q < thresh] = 0.0
    if q.sum() > 0:
        q *= q_total / q.sum()

    q_map = {n: float(qi) for n, qi in zip(candidate_nodes, q)}
    ranked = sorted(q_map.items(), key=lambda kv: kv[1], reverse=True)
    ranked = [(n, v) for n, v in ranked if v > 0]
    pred_r = S @ q
    return LeakEstimate(
        q_lps=q_map,
        q_total_lps=float(q_total),
        detected=True,
        ranked=ranked,
        residual_norm_m=float(np.linalg.norm(pred_r - r)),
    )


def observe_scenario(frames: dict, sensors: list[str], seed: int, meta: dict) -> dict:
    obs = make_observations(
        frames["pressure_m"],
        frames["inlet_flow_lps"],
        sensors,
        seed=seed,
        pressure_sigma_m=DEFAULT_PRESSURE_SIGMA_M,
        flow_sigma_lps=DEFAULT_FLOW_SIGMA_LPS,
        dropout_p=DEFAULT_DROPOUT_P,
    )
    return obs


def default_candidates() -> list[str]:
    return list(customer_junctions())
