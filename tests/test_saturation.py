"""Hydrograph change-point and IWS event types. No EPANET required except one hook."""

from __future__ import annotations

import numpy as np

from baseline.emitter_calibrate import estimate_leaks
from baseline.saturation import (
    EVENT_FILLING,
    EVENT_LEAK,
    EVENT_NO_LEAK,
    EVENT_SENSOR,
    EVENT_VALVE,
    change_point_index,
    detect_saturation,
    leftover_m3_per_day,
    leftover_persists,
)
from dashboard.views import event_banner
from placement.greedy import compute_signatures
from sim.network import JUNCTION_NAMES
from sim.observe import make_observations, valve_open_for_solver
from tests.conftest import DURATION_H


STEP = 300
FILL_LPS = 5.5
CLOCK_SAT_S = 5 * 3600 + 75 * 60  # 06:15


def _times(duration_h: float = 12.0) -> np.ndarray:
    return np.arange(0, int(duration_h * 3600) + 1, STEP, dtype=float)


def _hydrograph(
    times: np.ndarray,
    *,
    fill_minutes: float = 75.0,
    leftover: float = 0.0,
    open_s: float = 5 * 3600,
    close_s: float = 9 * 3600,
    noise: float = 0.0,
    seed: int = 0,
    after_nan: bool = False,
    closed_window: bool = False,
) -> np.ndarray:
    q = np.zeros(len(times), dtype=float)
    sat = open_s + fill_minutes * 60.0
    for i, t in enumerate(times):
        if closed_window or not (open_s <= t < close_s):
            q[i] = 0.0
        elif t < sat:
            q[i] = FILL_LPS + leftover
        else:
            q[i] = leftover
            if after_nan:
                q[i] = np.nan
    if noise:
        rng = np.random.default_rng(seed)
        q = q + rng.normal(0.0, noise, size=q.shape)
        q[times < open_s] = 0.0
        q[times >= close_s] = 0.0
        if after_nan:
            q[(times >= sat) & (times < close_s)] = np.nan
        if closed_window:
            q[(times >= open_s) & (times < close_s)] = 0.0
    return q


def test_change_point_finds_the_knee_not_the_clock():
    times = _times()
    q = _hydrograph(times, fill_minutes=120.0, leftover=1.4)
    window = q[(times >= 5 * 3600) & (times < 9 * 3600)]
    k = change_point_index(window, min_fill_steps=4, min_after_steps=6)
    assert k is not None
    t_sat = times[(times >= 5 * 3600) & (times < 9 * 3600)][k]
    # 05:00 + 120 min = 07:00. Must not snap to the 75-minute clock (06:15).
    assert abs(t_sat - (5 * 3600 + 120 * 60)) <= 2 * STEP
    assert abs(t_sat - CLOCK_SAT_S) > 30 * 60


def test_no_leak_after_fill_is_no_leak_event():
    times = _times()
    q = _hydrograph(times, leftover=0.0, noise=0.12, seed=3)
    sat = detect_saturation(times, q, 12.0, detect_threshold_lps=0.35)
    assert sat.event == EVENT_NO_LEAK
    assert sat.used_change_point
    assert sat.leftover_lps < 0.35
    assert abs(sat.windows[0].t_sat_s - CLOCK_SAT_S) <= 3 * STEP


def test_leftover_persists_as_leak():
    times = _times()
    q = _hydrograph(times, leftover=1.4, noise=0.12, seed=4)
    sat = detect_saturation(times, q, 12.0, detect_threshold_lps=0.35)
    assert sat.event == EVENT_LEAK
    assert 1.0 < sat.leftover_lps < 1.8
    assert sat.leftover_m3_per_day > 20.0  # ~1.4 L/s × 8 h/day


def test_valve_did_not_open():
    times = _times()
    q = _hydrograph(times, closed_window=True)
    p = np.zeros(len(times))
    sat = detect_saturation(times, q, 12.0, pressure_m=p)
    assert sat.event == EVENT_VALVE
    assert sat.leftover_lps == 0.0


def test_explicit_valve_closed_flag():
    times = _times()
    q = _hydrograph(times, leftover=1.4)
    valve = np.zeros(len(times), dtype=bool)
    sat = detect_saturation(times, q, 12.0, valve_open=valve)
    assert sat.event == EVENT_VALVE


def test_missing_after_fill_is_sensor_failure():
    times = _times()
    q = _hydrograph(times, leftover=1.4, after_nan=True)
    sat = detect_saturation(times, q, 12.0)
    assert sat.event == EVENT_SENSOR


def test_never_drops_is_still_filling():
    times = _times()
    q = _hydrograph(times, fill_minutes=240.0, leftover=0.0)
    sat = detect_saturation(times, q, 12.0)
    # Whole 4 h window is the high plateau — no knee, not a clean DMA.
    assert sat.event == EVENT_FILLING
    assert not sat.used_change_point
    assert sat.leftover_lps == 0.0


def test_persist_rejects_a_two_sample_spike():
    series = np.array([0.0, 0.9, 0.8, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert leftover_persists(series, 0.35, persist_steps=4) is False
    series = np.array([0.9, 0.8, 0.7, 0.85, 0.9, 0.8])
    assert leftover_persists(series, 0.35, persist_steps=4) is True


def test_leftover_m3_per_day_is_open_hours_not_24h():
    # 1 L/s during 8 open hours/day = 28.8 m³/day, not 86.4.
    windows = [(5 * 3600, 9 * 3600), (17 * 3600, 21 * 3600)]
    m3 = leftover_m3_per_day(1.0, 24.0, windows)
    assert abs(m3 - 28.8) < 0.05


def test_event_banner_does_not_call_a_dead_logger_a_clean_dma():
    dead = event_banner("sensor_failure", 0.0, 0.0)
    assert dead["is_actionable_fault"]
    assert not dead["is_leak"]
    leak = event_banner("leak", 1.4, 40.0)
    assert leak["is_leak"]


def test_estimate_leaks_uses_change_point_on_epanet_hook(noleak_12h, leak_j07_12h):
    pack = compute_signatures(duration_h=12.0)
    sensors = ["J17", "J06", "J08", "J09", "J04", "J11", "J15", "J03", "J10", "J02"]
    obs = make_observations(
        leak_j07_12h.pressure_m,
        leak_j07_12h.inlet_flow_lps,
        sensors,
        seed=11,
        duration_h=DURATION_H,
    )
    p0 = noleak_12h.pressure_m.reindex(leak_j07_12h.times_s).interpolate().bfill().ffill()
    q0 = noleak_12h.inlet_flow_lps.reindex(leak_j07_12h.times_s).interpolate().bfill().ffill()
    est = estimate_leaks(
        pressure_obs=obs["pressure_m"].to_numpy(dtype=float),
        inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
        sensors=sensors,
        times_s=np.asarray(leak_j07_12h.times_s),
        p_noleak=p0[list(JUNCTION_NAMES)].to_numpy(dtype=float),
        inlet_noleak_lps=q0.to_numpy(dtype=float),
        sensitivity=pack["signatures"],
        candidate_nodes=pack["leak_nodes"],
        duration_h=DURATION_H,
        valve_open=valve_open_for_solver(obs),
    )
    assert est.detected is True
    assert est.event == EVENT_LEAK
    assert est.used_change_point
    assert est.t_sat_s
    assert abs(est.t_sat_s[0] - CLOCK_SAT_S) <= 4 * STEP
    assert est.leftover_m3_per_day > 0
