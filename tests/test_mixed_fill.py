"""t_sat must follow the demand pattern, not the 75-minute clock."""

from __future__ import annotations

from sim.generate import FILL_MINUTE_CHOICES, generate_one
from baseline.saturation import detect_saturation
from sim.leaks import leaks_from_q_lps
from sim.network import build_dma
from sim.scenario import run_scenario
import numpy as np


def test_generate_one_draws_a_listed_fill_when_unspecified():
    fills = {generate_one(i, 4000 + i, 12.0, None).fill_minutes for i in range(6)}
    assert fills <= set(FILL_MINUTE_CHOICES)
    assert len(fills) >= 2


def test_generate_one_honours_a_fixed_fill():
    sc = generate_one(0, 1, 12.0, 120.0)
    assert sc.fill_minutes == 120.0


def test_tsat_tracks_120_minute_fill_not_the_clock():
    wn = build_dma()
    leaks = leaks_from_q_lps(wn, [("J07", 1.5)])
    sc = run_scenario(scenario_id="fill120", leaks=leaks, fill_minutes=120, duration_h=12.0)
    times = np.asarray(sc.times_s, dtype=float)
    sat = detect_saturation(times, sc.inlet_flow_lps.to_numpy(dtype=float), 12.0)
    assert sat.used_change_point
    t_sat = next(w.t_sat_s for w in sat.windows if w.t_sat_s is not None)
    true = 5 * 3600 + 120 * 60
    clock = 5 * 3600 + 75 * 60
    assert abs(t_sat - true) <= 15 * 60
    assert abs(t_sat - clock) > 30 * 60
