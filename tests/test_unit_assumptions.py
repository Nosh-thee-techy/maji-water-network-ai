"""Fast tests: topology, schedule, demand pattern, bookkeeping, isolation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from baseline.graph_distance import hop_distance, match_leaks, pipe_graph
from sim.balance import water_balance_m3
from sim.demand import DEFAULT_FILL_MINUTES, storage_limited_multipliers
from sim.network import assert_topology, build_dma, customer_junctions, summarise
from sim.observe import make_observations
from sim.schedule import expand_windows, is_supply_open


def test_dma_is_18_junctions_looped_and_branched():
    wn = build_dma()
    assert_topology(wn)
    info = summarise(wn)
    assert info["junctions"] == 18
    assert info["loop_excess_pipes"] >= 3
    assert wn.options.hydraulic.demand_model in {"PDA", "PDD"}


def test_inlet_is_not_a_customer_node():
    assert "J00" not in customer_junctions()


def test_rationing_windows_cover_two_days():
    windows = expand_windows(48.0)
    assert windows == [
        (5 * 3600, 9 * 3600),
        (17 * 3600, 21 * 3600),
        (29 * 3600, 33 * 3600),
        (41 * 3600, 45 * 3600),
    ]
    assert is_supply_open(5 * 3600)
    assert not is_supply_open(5 * 3600 - 1)
    assert not is_supply_open(9 * 3600)
    assert is_supply_open(17 * 3600 + 60)


def test_storage_pattern_is_not_a_tank_and_only_covers_fill_minutes():
    mult = storage_limited_multipliers(duration_h=24.0, fill_minutes=DEFAULT_FILL_MINUTES)
    # 05:00 is fill; 06:20 (80 min in) is after-fill; 04:00 is closed.
    step = 300
    assert mult[int(5 * 3600 / step)] == 1.0
    assert mult[int((5 * 3600 + 70 * 60) / step)] == 1.0
    assert mult[int((5 * 3600 + 80 * 60) / step)] == 0.0
    assert mult[int(4 * 3600 / step)] == 0.0
    assert sum(mult) > 0
    # Two windows × 75 min / 5 min = 30 ones per day, plus the inclusive end step.
    ones = sum(1 for m in mult if m == 1.0)
    assert 28 <= ones <= 32


def test_water_balance_splits_apparent_loss_only_with_billing():
    idx = [0, 1000]
    inlet = pd.Series([10.0, 0.0], index=idx)
    customer = pd.DataFrame({"J01": [8.0, 0.0]}, index=idx)
    leak = pd.DataFrame({"J07": [2.0, 0.0]}, index=idx)
    bal = water_balance_m3(
        inlet_flow_lps=inlet,
        customer_lps=customer,
        leak_lps=leak,
        unmetered_share={"J01": 0.25},
        meter_bias=0.10,
        timestep_s=1000.0,
    )
    # Rectangle rule uses all-but-last step: 10 L/s * 1000 s / 1000 = 10 m³.
    assert abs(bal["supplied"] - 10.0) < 1e-9
    assert abs(bal["leaked"] - 2.0) < 1e-9
    assert abs(bal["customer"] - 8.0) < 1e-9
    assert abs(bal["unmetered"] - 2.0) < 1e-9
    assert abs(bal["meter_error"] - 0.6) < 1e-9
    assert abs(bal["residual"]) < 1e-9


def test_observations_never_include_hidden_labels():
    times = [0, 300, 600]
    pressure = pd.DataFrame({"J01": [20.0, 20.0, 0.0], "J07": [18.0, 18.0, 0.0]}, index=times)
    inlet = pd.Series([5.0, 5.0, 0.0], index=times)
    obs = make_observations(pressure, inlet, ["J01"], seed=1, dropout_p=0.0)
    assert set(obs.keys()) <= {
        "sensors",
        "pressure_sigma_m",
        "flow_sigma_lps",
        "dropout_p",
        "duty_cycle",
        "pressure_m",
        "inlet_flow_lps",
        "valve_open",
        "duty_keep",
        "after_hold",
        "t_sat_s",
    }
    assert "J07" not in obs["pressure_m"].columns
    assert list(obs["pressure_m"].columns) == ["J01"]
    # Noise moved the reading; solvers do not get the clean field.
    assert not np.allclose(obs["pressure_m"]["J01"].to_numpy(), pressure["J01"].to_numpy())


def test_dropouts_are_nan_not_zeros():
    times = list(range(0, 3000, 300))
    pressure = pd.DataFrame({"J01": [20.0] * len(times)}, index=times)
    inlet = pd.Series([5.0] * len(times), index=times)
    obs = make_observations(pressure, inlet, ["J01"], seed=0, dropout_p=0.5)
    assert obs["pressure_m"].isna().any().any()


def test_hop_distance_on_the_schematic_graph():
    g = pipe_graph()
    assert hop_distance("J00", "J00", g) == 0
    assert hop_distance("J16", "J17", g) == 1
    assert hop_distance("J00", "J17", g) >= 4
    miss = match_leaks([], ["J07"], g)
    assert miss["mean_hops"] == 6
    perfect = match_leaks(["J07"], ["J07"], g)
    assert perfect["perfect"] is True
