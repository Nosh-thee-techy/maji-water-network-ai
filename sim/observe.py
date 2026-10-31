"""Corrupt clean hydraulic fields into the only signal solvers may see.

Solvers never receive the clean pressure field or leak labels. They
get what a chamber logger would *uplink*: noisy pressure at a sensor
subset, noisy inlet flow, and valve position.

The logger still *samples* every hydraulic step (5 min). The duty cycle
decides which steps leave the chamber (docs/iot_stack.md):

- Off-window: 15-minute heartbeat (sleep)
- Valve-open step, or ΔP ≳ 0.5 m: always uplink (burst)
- Fill (before t_sat): every 5 min (need the knee)
- After t_sat, 30 min hold: every 5 min, protected leftover
- Rest of the open window: 15 min (localisation, not detection)

A continuously supplied DMA never sleeps — there is no off-window.
Radio dropouts (default 3%) apply only to samples that were uplinked;
the after-fill hold uses a 1% cap so a KPLC blip does not erase the
one number that is the leak.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from sim.demand import DEFAULT_FILL_MINUTES
from sim.schedule import SUPPLY_WINDOWS_H, expand_windows


# Cheap 10-bar gauge, roughly ±0.3 m RMS after a crude field calibration.
# Full-scale ±1% of 10 bar would be ±1 m; we use a tighter value so the
# inverse problem is not dominated by noise on this small DMA.
DEFAULT_PRESSURE_SIGMA_M = 0.30
DEFAULT_FLOW_SIGMA_LPS = 0.15
DEFAULT_DROPOUT_P = 0.03

OFF_HEARTBEAT_S = 15 * 60
AFTER_HOLD_S = 30 * 60
INWINDOW_SPARSE_S = 15 * 60
DELTA_P_BURST_M = 0.5
AFTER_HOLD_RADIO_P = 0.01
CONTINUOUS_FLOW_LPS = 0.30


def corrupt_frame(
    clean: pd.DataFrame,
    columns: Iterable[str],
    rng: np.random.Generator,
    sigma: float,
    dropout_p: float = DEFAULT_DROPOUT_P,
) -> pd.DataFrame:
    """Return a copy of ``clean[columns]`` with noise and NaN dropouts."""
    cols = list(columns)
    values = clean[cols].to_numpy(dtype=float).copy()
    values += rng.normal(0.0, sigma, size=values.shape)
    if dropout_p > 0.0:
        mask = rng.random(values.shape) < dropout_p
        values[mask] = np.nan
    return pd.DataFrame(values, index=clean.index, columns=cols)


def _on_grid(times: np.ndarray, period_s: float, timestep_s: float) -> np.ndarray:
    """True when ``times`` lands on a ``period_s`` clock, within half a step."""
    return (times % period_s) < (timestep_s * 0.5 + 1e-9)


def looks_continuous_supply(
    times: np.ndarray,
    inlet_lps: np.ndarray,
    windows: list[tuple[int, int]],
) -> bool:
    """Off-window inlet still flowing → this is not a rationed DMA."""
    off = np.ones(len(times), dtype=bool)
    for open_s, close_s in windows:
        off[(times >= open_s) & (times < close_s)] = False
    q = np.asarray(inlet_lps, dtype=float)[off]
    q = q[np.isfinite(q)]
    return q.size > 5 and float(np.median(np.abs(q))) > CONTINUOUS_FLOW_LPS


def scheduled_valve_open(times: np.ndarray, windows: list[tuple[int, int]]) -> np.ndarray:
    open_ = np.zeros(len(times), dtype=float)
    for open_s, close_s in windows:
        open_[(times >= open_s) & (times < close_s)] = 1.0
    return open_


def duty_keep_mask(
    times: np.ndarray,
    pressure_m: np.ndarray,
    windows: list[tuple[int, int]],
    t_sat_s: list[float],
    *,
    timestep_s: float = 300.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Which hydraulic steps the logger uplinks.

    Returns ``(keep, after_hold)``. ``after_hold`` is the protected
    leftover window (t_sat … t_sat+30 min).
    """
    times = np.asarray(times, dtype=float)
    n = len(times)
    keep = np.zeros(n, dtype=bool)
    after_hold = np.zeros(n, dtype=bool)
    in_win = np.zeros(n, dtype=bool)
    for open_s, close_s in windows:
        m = (times >= open_s) & (times < close_s)
        in_win |= m
        idx = np.where(m)[0]
        if idx.size:
            keep[idx[0]] = True
        sats = [t for t in t_sat_s if open_s <= t < close_s]
        t_sat = float(sats[0]) if sats else float(open_s + DEFAULT_FILL_MINUTES * 60)
        t_sat = min(t_sat, float(close_s))
        hold_end = min(float(close_s), t_sat + AFTER_HOLD_S)
        fill = (times >= open_s) & (times < t_sat)
        hold = (times >= t_sat) & (times < hold_end)
        rest = (times >= hold_end) & (times < close_s)
        keep[fill] = True
        keep[hold] = True
        after_hold[hold] = True
        keep[rest] = _on_grid(times[rest], INWINDOW_SPARSE_S, timestep_s)

    off = ~in_win
    keep[off] = _on_grid(times[off], OFF_HEARTBEAT_S, timestep_s)

    if pressure_m is not None and np.asarray(pressure_m).size:
        p = np.asarray(pressure_m, dtype=float)
        if p.ndim == 1:
            pmean = p
        else:
            pmean = np.nanmean(p, axis=1)
        dp = np.zeros(n)
        finite = np.isfinite(pmean)
        for i in range(1, n):
            if not (finite[i] and finite[i - 1]):
                continue
            # Slack-pipe gauge noise is ~0.3 m RMS; do not treat that as a burst.
            if max(abs(pmean[i]), abs(pmean[i - 1])) < 2.0:
                continue
            if abs(pmean[i] - pmean[i - 1]) >= DELTA_P_BURST_M:
                keep[i] = True
    return keep, after_hold


def valve_open_for_solver(obs: dict) -> np.ndarray | None:
    """Float 1/0/NaN valve series for ``estimate_leaks``, or None."""
    v = obs.get("valve_open")
    if v is None:
        return None
    return np.asarray(v, dtype=float)


def make_observations(
    pressure_m: pd.DataFrame,
    inlet_flow_lps: pd.Series,
    sensors: list[str],
    *,
    seed: int,
    pressure_sigma_m: float = DEFAULT_PRESSURE_SIGMA_M,
    flow_sigma_lps: float = DEFAULT_FLOW_SIGMA_LPS,
    dropout_p: float = DEFAULT_DROPOUT_P,
    duration_h: float | None = None,
    duty_cycle: bool = True,
    valve_open: pd.Series | np.ndarray | None = None,
) -> dict:
    rng = np.random.default_rng(seed)
    times = np.asarray(pressure_m.index, dtype=float)
    if duration_h is None:
        duration_h = float(times[-1] / 3600.0) if len(times) else 0.0
    timestep_s = float(np.median(np.diff(times))) if len(times) > 1 else 300.0
    windows = expand_windows(duration_h, SUPPLY_WINDOWS_H)

    cols = list(sensors)
    p_local = pressure_m[cols].to_numpy(dtype=float).copy()
    p_local += rng.normal(0.0, pressure_sigma_m, size=p_local.shape)
    q_local = inlet_flow_lps.to_numpy(dtype=float).copy()
    q_local += rng.normal(0.0, flow_sigma_lps, size=q_local.shape)

    if valve_open is None:
        valve_local = scheduled_valve_open(times, windows)
    else:
        valve_local = np.asarray(valve_open, dtype=float).reshape(-1)
        if valve_local.size != len(times):
            raise ValueError("valve_open length must match the time index")

    continuous = looks_continuous_supply(times, q_local, windows)
    used_duty = bool(duty_cycle) and (not continuous) and bool(windows)

    t_sat: list[float] = []
    keep = np.ones(len(times), dtype=bool)
    after_hold = np.zeros(len(times), dtype=bool)
    if used_duty:
        # Local 5-minute buffer still has every step. The logger finds
        # t_sat on that buffer, then decides what to uplink.
        from baseline.saturation import detect_saturation

        with np.errstate(all="ignore"):
            p_mean = np.nanmean(p_local, axis=1) if p_local.size else None
        sat = detect_saturation(
            times,
            q_local,
            duration_h,
            pressure_m=p_mean,
            valve_open=valve_local,
            detect_threshold_lps=0.35,
            timestep_s=timestep_s,
        )
        t_sat = [w.t_sat_s for w in sat.windows if w.t_sat_s is not None]
        keep, after_hold = duty_keep_mask(
            times, p_local, windows, t_sat, timestep_s=timestep_s
        )

    p_up = p_local.copy()
    q_up = q_local.copy()
    v_up = valve_local.copy()
    p_up[~keep] = np.nan
    q_up[~keep] = np.nan
    v_up[~keep] = np.nan

    if dropout_p > 0.0:
        radio = rng.random(q_up.shape) < dropout_p
        radio &= keep
        if after_hold.any():
            radio[after_hold] = rng.random(int(after_hold.sum())) < min(dropout_p, AFTER_HOLD_RADIO_P)
        q_up[radio] = np.nan
        v_up[radio] = np.nan
        radio_p = rng.random(p_up.shape) < dropout_p
        radio_p &= keep[:, None]
        if after_hold.any():
            hold_rows = np.where(after_hold)[0]
            radio_p[hold_rows] = rng.random((hold_rows.size, p_up.shape[1])) < min(
                dropout_p, AFTER_HOLD_RADIO_P
            )
        p_up[radio_p] = np.nan

    return {
        "sensors": list(sensors),
        "pressure_sigma_m": pressure_sigma_m,
        "flow_sigma_lps": flow_sigma_lps,
        "dropout_p": dropout_p,
        "duty_cycle": used_duty,
        "pressure_m": pd.DataFrame(p_up, index=pressure_m.index, columns=cols),
        "inlet_flow_lps": pd.Series(q_up, index=inlet_flow_lps.index, name="inlet_flow_lps"),
        "valve_open": pd.Series(v_up, index=inlet_flow_lps.index, name="valve_open"),
        "duty_keep": pd.Series(keep, index=inlet_flow_lps.index, name="duty_keep"),
        "after_hold": pd.Series(after_hold, index=inlet_flow_lps.index, name="after_hold"),
        "t_sat_s": t_sat,
    }
