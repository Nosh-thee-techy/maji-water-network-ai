"""Sunday / post-saturation no-leak update (PUB ALF, crude).

The sensitivity matrix stays frozen. What we update is the *baseline
inlet* (and optionally nodal pressure) on the after-fill plateau, using
windows the detector already called clean.

Do not absorb a leak into the baseline: leftover must sit below the
detect threshold before a window is allowed to teach the model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from baseline.emitter_calibrate import DETECT_THRESHOLD_LPS
from baseline.saturation import detect_saturation


@dataclass
class Recalibration:
    inlet_noleak_lps: np.ndarray
    pressure_noleak: np.ndarray | None
    applied: bool
    leftover_before_lps: float
    n_after_updated: int
    reason: str


def _nanmean(values: np.ndarray) -> float:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float("nan")
    return float(v.mean())


def sunday_update(
    *,
    inlet_noleak_lps: np.ndarray,
    inlet_obs_lps: np.ndarray,
    after_mask: np.ndarray,
    leftover_lps: float,
    detect_threshold_lps: float = DETECT_THRESHOLD_LPS,
    pressure_noleak: np.ndarray | None = None,
    pressure_obs: np.ndarray | None = None,
    fill_mask: np.ndarray | None = None,
) -> Recalibration:
    """If this window is clean, match the no-leak after-fill to what we saw.

    Fill-window demand is left alone (tanks still draw). Only the leftover
    plateau is shifted, so a slow meter offset does not become a permanent
    leak alarm.
    """
    noleak = np.asarray(inlet_noleak_lps, dtype=float).copy()
    obs = np.asarray(inlet_obs_lps, dtype=float)
    after = np.asarray(after_mask, dtype=bool)
    p_new = None if pressure_noleak is None else np.asarray(pressure_noleak, dtype=float).copy()

    if leftover_lps >= detect_threshold_lps:
        return Recalibration(
            inlet_noleak_lps=noleak,
            pressure_noleak=p_new,
            applied=False,
            leftover_before_lps=float(leftover_lps),
            n_after_updated=0,
            reason="leftover still above threshold — refusing to absorb a leak",
        )
    if not after.any():
        return Recalibration(
            inlet_noleak_lps=noleak,
            pressure_noleak=p_new,
            applied=False,
            leftover_before_lps=float(leftover_lps),
            n_after_updated=0,
            reason="no after-fill mask",
        )

    finite = after & np.isfinite(obs)
    n = int(finite.sum())
    if n < 3:
        return Recalibration(
            inlet_noleak_lps=noleak,
            pressure_noleak=p_new,
            applied=False,
            leftover_before_lps=float(leftover_lps),
            n_after_updated=0,
            reason="after-fill too sparse to teach the baseline",
        )

    # Shift the whole after-fill plateau by the mean residual so the
    # shape of the no-leak model stays, but the leftover vanishes.
    delta = _nanmean(obs[finite] - noleak[finite])
    if not np.isfinite(delta):
        delta = 0.0
    noleak[after] = noleak[after] + delta

    n_p = 0
    if p_new is not None and pressure_obs is not None and fill_mask is not None:
        fill = np.asarray(fill_mask, dtype=bool)
        p_obs = np.asarray(pressure_obs, dtype=float)
        rows = fill & np.isfinite(p_obs).any(axis=1 if p_obs.ndim == 2 else 0)
        if int(rows.sum()) >= 3 and p_new.shape == p_obs.shape:
            # Sensor-wise mean shift during fill (localisation residual).
            if p_obs.ndim == 2:
                shift = np.nanmean(p_obs[rows] - p_new[rows], axis=0)
                shift = np.nan_to_num(shift, nan=0.0)
                p_new[fill] = p_new[fill] + shift
            n_p = int(rows.sum())

    return Recalibration(
        inlet_noleak_lps=noleak,
        pressure_noleak=p_new,
        applied=True,
        leftover_before_lps=float(leftover_lps),
        n_after_updated=n,
        reason=f"after-fill baseline shifted by {delta:.3f} L/s" + (f"; fill pressure {n_p} steps" if n_p else ""),
    )


def recalibrate_from_observations(
    times_s: np.ndarray,
    inlet_obs_lps: np.ndarray,
    inlet_noleak_lps: np.ndarray,
    duration_h: float,
    *,
    pressure_obs: np.ndarray | None = None,
    pressure_noleak: np.ndarray | None = None,
    valve_open: np.ndarray | None = None,
    detect_threshold_lps: float = DETECT_THRESHOLD_LPS,
) -> Recalibration:
    """Run saturation, then Sunday-update only if the event is no_leak."""
    sat = detect_saturation(
        times_s,
        inlet_obs_lps,
        duration_h,
        pressure_m=None if pressure_obs is None else np.nanmean(np.asarray(pressure_obs, dtype=float), axis=1)
        if np.asarray(pressure_obs).ndim == 2
        else pressure_obs,
        valve_open=valve_open,
        inlet_noleak_lps=inlet_noleak_lps,
        detect_threshold_lps=detect_threshold_lps,
    )
    if sat.event != "no_leak":
        return Recalibration(
            inlet_noleak_lps=np.asarray(inlet_noleak_lps, dtype=float).copy(),
            pressure_noleak=None if pressure_noleak is None else np.asarray(pressure_noleak, dtype=float).copy(),
            applied=False,
            leftover_before_lps=float(sat.leftover_lps),
            n_after_updated=0,
            reason=f"event is {sat.event} — only a clean after-fill teaches the baseline",
        )
    leftover = sat.leftover_lps
    return sunday_update(
        inlet_noleak_lps=inlet_noleak_lps,
        inlet_obs_lps=inlet_obs_lps,
        after_mask=sat.after_mask,
        leftover_lps=leftover,
        detect_threshold_lps=detect_threshold_lps,
        pressure_noleak=pressure_noleak,
        pressure_obs=pressure_obs,
        fill_mask=sat.fill_mask,
    )
