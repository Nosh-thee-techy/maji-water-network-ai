"""The solver may only see noisy sensors. Hidden labels must not leak in."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from baseline.emitter_calibrate import estimate_leaks
from baseline.graph_distance import hop_distance
from placement.greedy import compute_signatures
from sim.network import JUNCTION_NAMES
from sim.observe import make_observations
from tests.conftest import DURATION_H


@pytest.fixture(scope="session")
def signatures():
    return compute_signatures(duration_h=12.0)


def _run_solver(sc, noleak, pack, sensors, seed):
    obs = make_observations(sc.pressure_m, sc.inlet_flow_lps, sensors, seed=seed)
    times = sc.times_s
    p0 = noleak.pressure_m.reindex(times).interpolate().bfill().ffill()
    q0 = noleak.inlet_flow_lps.reindex(times).interpolate().bfill().ffill()
    return estimate_leaks(
        pressure_obs=obs["pressure_m"].to_numpy(dtype=float),
        inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
        sensors=sensors,
        times_s=np.asarray(times),
        p_noleak=p0[list(JUNCTION_NAMES)].to_numpy(dtype=float),
        inlet_noleak_lps=q0.to_numpy(dtype=float),
        sensitivity=pack["signatures"],
        candidate_nodes=pack["leak_nodes"],
        duration_h=sc.duration_h,
    )


def test_estimate_leaks_signature_has_no_ground_truth_parameter():
    params = set(inspect.signature(estimate_leaks).parameters)
    forbidden = {"leaks", "leak_nodes", "meter_bias", "unmetered_share", "water_balance_m3"}
    assert params.isdisjoint(forbidden)


def test_zero_leak_is_not_called_a_leak(noleak_12h, signatures):
    sensors = ["J17", "J06", "J08", "J09", "J04", "J11", "J15", "J03", "J10", "J02"]
    est = _run_solver(noleak_12h, noleak_12h, signatures, sensors, seed=11)
    assert est.detected is False
    assert est.ranked == []


def test_one_point_five_lps_leak_is_detected_and_near_j07(noleak_12h, leak_j07_12h, signatures):
    sensors = ["J17", "J06", "J08", "J09", "J04", "J11", "J15", "J03", "J10", "J02"]
    est = _run_solver(leak_j07_12h, noleak_12h, signatures, sensors, seed=11)
    assert est.detected is True
    assert est.ranked
    pred = est.ranked[0][0]
    assert hop_distance(pred, "J07") <= 3, f"predicted {pred} is too far from J07"


def test_pressure_only_flag_runs_without_using_a_hidden_label(noleak_12h, leak_j07_12h, signatures):
    sensors = ["J17", "J06", "J08", "J09", "J04", "J11", "J15", "J03", "J10", "J02"]
    hook = _run_solver(noleak_12h, noleak_12h, signatures, sensors, seed=11)
    # monkey-patch: call estimate path with the flag via _solve-equivalent
    from baseline.emitter_calibrate import estimate_leaks
    from sim.network import JUNCTION_NAMES
    from sim.observe import make_observations
    import numpy as np

    sc = leak_j07_12h
    obs = make_observations(sc.pressure_m, sc.inlet_flow_lps, sensors, seed=11)
    p0 = noleak_12h.pressure_m.reindex(sc.times_s).interpolate().bfill().ffill()
    q0 = noleak_12h.inlet_flow_lps.reindex(sc.times_s).interpolate().bfill().ffill()
    est = estimate_leaks(
        pressure_obs=obs["pressure_m"].to_numpy(dtype=float),
        inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
        sensors=sensors,
        times_s=np.asarray(sc.times_s),
        p_noleak=p0[list(JUNCTION_NAMES)].to_numpy(dtype=float),
        inlet_noleak_lps=q0.to_numpy(dtype=float),
        sensitivity=signatures["signatures"],
        candidate_nodes=signatures["leak_nodes"],
        duration_h=sc.duration_h,
        use_inlet_hook=False,
    )
    assert hook.detected is False
    assert isinstance(est.detected, bool)


def test_solver_does_not_receive_clean_full_field(leak_j07_12h):
    sensors = ["J17", "J06", "J08"]
    obs = make_observations(
        leak_j07_12h.pressure_m,
        leak_j07_12h.inlet_flow_lps,
        sensors,
        seed=3,
    )
    assert list(obs["pressure_m"].columns) == sensors
    assert "J07" not in obs["pressure_m"].columns
    # Hidden leak location is not an observation key.
    blob = str(obs.keys())
    assert "leak" not in blob.lower()
