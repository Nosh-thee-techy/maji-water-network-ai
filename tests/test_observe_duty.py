"""IWS logger duty cycle: sleep off-window, protect the after-fill hold."""

from __future__ import annotations

import numpy as np
import pandas as pd

from sim.observe import (
    AFTER_HOLD_S,
    OFF_HEARTBEAT_S,
    make_observations,
    valve_open_for_solver,
)
from tests.test_saturation import CLOCK_SAT_S, FILL_LPS, STEP, _hydrograph, _times


def _obs(times, q, *, leftover=0.0, dropout_p=0.0, valve=None, seed=2):
    in_win = (times >= 5 * 3600) & (times < 9 * 3600)
    p = np.where(in_win, 16.0, 0.0).astype(float)
    pressure = pd.DataFrame({"J01": p}, index=times)
    inlet = pd.Series(q, index=times, name="inlet_flow_lps")
    return make_observations(
        pressure,
        inlet,
        ["J01"],
        seed=seed,
        dropout_p=dropout_p,
        duration_h=12.0,
        valve_open=valve,
    )


def test_off_window_is_a_15_minute_heartbeat():
    times = _times(12.0)
    q = _hydrograph(times, leftover=0.0)
    obs = _obs(times, q)
    assert obs["duty_cycle"] is True
    off = (times < 5 * 3600) | (times >= 9 * 3600)
    keep_off = obs["duty_keep"].to_numpy()[off]
    # 5-min steps, 15-min clock → about one in three.
    assert 0.28 < keep_off.mean() < 0.40
    assert not keep_off.all()
    finite_off = np.isfinite(obs["inlet_flow_lps"].to_numpy()[off])
    assert finite_off.sum() == keep_off.sum()


def test_fill_and_after_hold_stay_dense():
    times = _times(12.0)
    q = _hydrograph(times, leftover=1.4, noise=0.05, seed=4)
    obs = _obs(times, q, leftover=1.4)
    fill = (times >= 5 * 3600) & (times < CLOCK_SAT_S)
    hold = (times >= CLOCK_SAT_S) & (times < CLOCK_SAT_S + AFTER_HOLD_S)
    assert obs["duty_keep"].to_numpy()[fill].all()
    assert obs["duty_keep"].to_numpy()[hold].all()
    assert obs["after_hold"].to_numpy()[hold].all()
    rest = (times >= CLOCK_SAT_S + AFTER_HOLD_S) & (times < 9 * 3600)
    keep_rest = obs["duty_keep"].to_numpy()[rest]
    assert keep_rest.any()
    assert keep_rest.mean() < 0.55  # 15-min rest of window


def test_continuous_supply_does_not_sleep():
    times = _times(12.0)
    q = np.full(len(times), FILL_LPS)
    pressure = pd.DataFrame({"J01": np.full(len(times), 16.0)}, index=times)
    obs = make_observations(
        pressure,
        pd.Series(q, index=times),
        ["J01"],
        seed=1,
        dropout_p=0.0,
        duration_h=12.0,
    )
    assert obs["duty_cycle"] is False
    assert bool(obs["duty_keep"].all())
    assert np.isfinite(obs["inlet_flow_lps"]).all()


def test_valve_position_is_an_observation_not_a_hidden_label():
    times = _times(12.0)
    q = _hydrograph(times, leftover=0.0)
    obs = _obs(times, q, dropout_p=0.0)
    assert "valve_open" in obs
    v = valve_open_for_solver(obs)
    assert v is not None
    keep = obs["duty_keep"].to_numpy()
    in_win = (times >= 5 * 3600) & (times < 9 * 3600)
    kept_open = v[keep & in_win]
    kept_open = kept_open[np.isfinite(kept_open)]
    assert kept_open.size
    assert np.all(kept_open > 0.5)
    blob = str(obs.keys())
    assert "leak" not in blob.lower()


def test_forced_closed_valve_reaches_the_solver():
    times = _times(12.0)
    q = _hydrograph(times, leftover=1.4)
    valve = np.zeros(len(times))
    obs = _obs(times, q, valve=valve)
    v = valve_open_for_solver(obs)
    known = v[np.isfinite(v)]
    assert known.size
    assert np.all(known < 0.5)


def test_pressure_burst_is_uplinked_off_window():
    times = _times(12.0)
    q = _hydrograph(times, leftover=0.0)
    in_win = (times >= 5 * 3600) & (times < 9 * 3600)
    p = np.where(in_win, 16.0, 0.0).astype(float)
    # Spike at 03:05 — not on the 15-min clock (03:00 is, 03:05 is not).
    spike_t = 3 * 3600 + 5 * 60
    p[times == spike_t] = 8.0
    pressure = pd.DataFrame({"J01": p}, index=times)
    obs = make_observations(
        pressure,
        pd.Series(q, index=times),
        ["J01"],
        seed=1,
        dropout_p=0.0,
        duration_h=12.0,
    )
    keep = obs["duty_keep"].to_numpy()
    assert keep[times == spike_t][0]
    # 03:20 is off-clock and after the spike has settled.
    assert not keep[times == 3 * 3600 + 20 * 60][0]


def test_heartbeat_lands_on_quarter_hours():
    times = _times(12.0)
    q = _hydrograph(times, leftover=0.0)
    obs = _obs(times, q)
    off = (times < 5 * 3600) | (times >= 9 * 3600)
    kept_t = times[off & obs["duty_keep"].to_numpy()]
    assert kept_t.size
    assert np.all((kept_t % OFF_HEARTBEAT_S) == 0)
