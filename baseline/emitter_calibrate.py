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

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from baseline.saturation import (
    EVENT_LEAK,
    EVENT_SENSOR,
    EVENT_VALVE,
    detect_saturation,
    leftover_m3_per_day,
)
from sim.demand import DEFAULT_FILL_MINUTES
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
    event: str = "no_leak"
    events: list[dict] = field(default_factory=list)
    leftover_m3_per_day: float = 0.0
    t_sat_s: list[float] = field(default_factory=list)
    used_change_point: bool = False


def window_slices(times: np.ndarray, duration_h: float) -> tuple[np.ndarray, np.ndarray]:
    """Clock fallback: first 75 minutes of each window vs the rest.

    Field detection uses ``detect_saturation`` (hydrograph knee). This
    helper stays for tests and continuous-supply runs that never drop.
    """
    expanded = expand_windows(duration_h, SUPPLY_WINDOWS_H)
    fill = np.zeros(len(times), dtype=bool)
    after = np.zeros(len(times), dtype=bool)
    fill_s = DEFAULT_FILL_MINUTES * 60
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
    use_inlet_hook: bool = True,
    valve_open: np.ndarray | None = None,
) -> LeakEstimate:
    junc = list(JUNCTION_NAMES)
    sensor_idx = [junc.index(s) for s in sensors]
    times = np.asarray(times_s)
    if pressure_obs.size:
        p_proxy = np.full(pressure_obs.shape[0], np.nan)
        valid = np.isfinite(pressure_obs).any(axis=1)
        if valid.any():
            p_proxy[valid] = np.nanmean(pressure_obs[valid], axis=1)
    else:
        p_proxy = None
    sat = detect_saturation(
        times,
        inlet_obs_lps,
        duration_h,
        pressure_m=p_proxy,
        valve_open=valve_open,
        inlet_noleak_lps=inlet_noleak_lps,
        detect_threshold_lps=detect_threshold_lps,
    )
    fill, after = sat.fill_mask, sat.after_mask
    if not after.any():
        fill, after = window_slices(times, duration_h)

    # Hook: after-fill inlet residual ≈ total leak (customer draw is zero).
    # Continuous-supply runs have no after-fill window — fall back to the
    # whole-horizon inlet residual against the no-leak model.
    flow_mask = after if after.any() else np.ones(len(after), dtype=bool)
    q_flow = sat.leftover_lps if sat.used_change_point else max(
        0.0, nanmean(inlet_obs_lps[flow_mask] - inlet_noleak_lps[flow_mask])
    )
    if not np.isfinite(q_flow):
        q_flow = max(0.0, nanmean(inlet_obs_lps[flow_mask] - inlet_noleak_lps[flow_mask]))

    events = [
        {
            "open_s": w.open_s,
            "close_s": w.close_s,
            "t_sat_s": w.t_sat_s,
            "leftover_lps": w.leftover_lps,
            "event": w.event,
        }
        for w in sat.windows
    ]
    t_sat = [w.t_sat_s for w in sat.windows if w.t_sat_s is not None]

    def _empty(event: str, q_total: float) -> LeakEstimate:
        return LeakEstimate(
            q_lps={n: 0.0 for n in candidate_nodes},
            q_total_lps=q_total,
            detected=False,
            ranked=[],
            residual_norm_m=0.0,
            event=event,
            events=events,
            leftover_m3_per_day=sat.leftover_m3_per_day if event == EVENT_LEAK else 0.0,
            t_sat_s=t_sat,
            used_change_point=sat.used_change_point,
        )

    if use_inlet_hook and sat.event in {EVENT_VALVE, EVENT_SENSOR}:
        return _empty(sat.event, 0.0)

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

    def fit_q(q_total_target: float | None) -> np.ndarray:
        def objective(q: np.ndarray) -> float:
            pred = S @ q
            loss = float(np.sum((pred - r) ** 2) + l1_weight * np.sum(q))
            if q_total_target is not None:
                loss += 0.4 * float((q.sum() - q_total_target) ** 2)
            return loss

        start = q_total_target if q_total_target and q_total_target > 0 else 0.3
        q0 = np.full(n_c, start / n_c)
        res = minimize(
            objective,
            q0,
            method="L-BFGS-B",
            bounds=[(0.0, 8.0)] * n_c,
            options={"maxiter": 400},
        )
        return np.clip(res.x, 0.0, None)

    if use_inlet_hook:
        q_total = q_flow
        if sat.used_change_point:
            detected = sat.event == EVENT_LEAK
            event = sat.event
        else:
            detected = q_total >= detect_threshold_lps
            event = EVENT_LEAK if detected else sat.event
        if not detected:
            return LeakEstimate(
                q_lps={n: 0.0 for n in candidate_nodes},
                q_total_lps=q_total,
                detected=False,
                ranked=[],
                residual_norm_m=float(np.linalg.norm(r)),
                event=event,
                events=events,
                leftover_m3_per_day=0.0,
                t_sat_s=t_sat,
                used_change_point=sat.used_change_point,
            )
        q = fit_q(q_total)
        thresh = max(0.08 * q.sum(), 0.15)
        q[q < thresh] = 0.0
        if q.sum() > 0:
            q *= q_total / q.sum()
    else:
        # Pressure-only: same 0.35 L/s detect threshold, but the scalar
        # comes from the L1 fit, not the after-fill inlet residual.
        q = fit_q(None)
        q_total = float(q.sum())
        detected = q_total >= detect_threshold_lps
        event = EVENT_LEAK if detected else sat.event
        if not detected:
            return LeakEstimate(
                q_lps={n: 0.0 for n in candidate_nodes},
                q_total_lps=q_total,
                detected=False,
                ranked=[],
                residual_norm_m=float(np.linalg.norm(r)),
                event=event,
                events=events,
                leftover_m3_per_day=0.0,
                t_sat_s=t_sat,
                used_change_point=sat.used_change_point,
            )
        thresh = max(0.08 * q.sum(), 0.15)
        q[q < thresh] = 0.0

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
        event=EVENT_LEAK,
        events=events,
        leftover_m3_per_day=leftover_m3_per_day(
            float(q_total),
            duration_h,
            expand_windows(duration_h, SUPPLY_WINDOWS_H),
        ),
        t_sat_s=t_sat,
        used_change_point=sat.used_change_point,
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
        duration_h=meta.get("duration_h"),
    )
    return obs


def default_candidates() -> list[str]:
    return list(customer_junctions())
