"""EPANET runs that would fail if the scientific hook is only a comment."""

from __future__ import annotations

from sim.leaks import leaks_from_q_lps
from sim.network import JUNCTION_NAMES, build_dma
from sim.observe import DEFAULT_PRESSURE_SIGMA_M
from sim.scenario import run_scenario
from tests.conftest import after_times, closed_times, fill_times


def test_off_window_pressure_is_clamped_to_zero(noleak_12h):
    closed = closed_times(noleak_12h)
    assert closed
    assert float(noleak_12h.pressure_m.loc[closed].max().max()) == 0.0


def test_on_window_pressure_is_positive_and_in_operating_range(noleak_12h):
    fill = fill_times(noleak_12h)
    p = noleak_12h.pressure_m.loc[fill]
    assert float(p.min().min()) > 8.0
    assert float(p.max().max()) < 30.0


def test_inlet_is_shut_when_rationed(noleak_12h):
    closed = closed_times(noleak_12h)
    assert abs(float(noleak_12h.inlet_flow_lps.loc[closed].mean())) < 1e-4


def test_after_fill_inlet_is_zero_without_a_leak(noleak_12h):
    after = after_times(noleak_12h)
    q = float(noleak_12h.inlet_flow_lps.loc[after].mean())
    assert abs(q) < 0.05, f"no-leak after-fill inlet should be ~0, got {q} L/s"


def test_after_fill_inlet_tracks_the_emitter(noleak_12h, leak_j07_12h):
    after = after_times(leak_j07_12h)
    q_none = float(noleak_12h.inlet_flow_lps.loc[after].mean())
    q_leak = float(leak_j07_12h.inlet_flow_lps.loc[after].mean())
    assert q_leak > 1.0
    assert q_leak - q_none > 1.0
    # 1.5 L/s orifice at 20 m; residual head is near 20 m so flow should be close.
    assert 1.1 < q_leak < 1.9


def test_customer_volume_is_storage_limited_not_leak_driven(noleak_12h, leak_j07_12h):
    """A leak must not be booked as household demand.

    Pressure-driven demand means a leak *slightly lowers* delivered customer
    volume (less residual head during the fill window). That coupling is real
    and was 3.2% on this pair — so we do not claim independence. We claim:
    customer volume does not rise, and the PDD drop stays modest.
    """
    c0 = noleak_12h.water_balance_m3["customer"]
    c1 = leak_j07_12h.water_balance_m3["customer"]
    assert c0 > 10.0
    assert c1 <= c0 + 1e-6
    assert (c0 - c1) / c0 < 0.05


def test_leak_volume_shows_up_in_the_inlet(noleak_12h, leak_j07_12h):
    extra_inlet = leak_j07_12h.water_balance_m3["supplied"] - noleak_12h.water_balance_m3["supplied"]
    leaked = leak_j07_12h.water_balance_m3["leaked"]
    assert leaked > 5.0
    assert abs(extra_inlet - leaked) / leaked < 0.05


def test_mass_balance_residual_is_numerical_noise(noleak_12h, leak_j07_12h):
    for sc in (noleak_12h, leak_j07_12h):
        supplied = sc.water_balance_m3["supplied"]
        assert abs(sc.water_balance_m3["residual"]) < 0.02 * max(supplied, 1.0)


def test_meter_bias_does_not_change_hydraulics():
    wn = build_dma()
    leaks = leaks_from_q_lps(wn, [("J07", 1.5)])
    a = run_scenario(scenario_id="bias-a", leaks=leaks, duration_h=12, meter_bias=0.02)
    b = run_scenario(scenario_id="bias-b", leaks=leaks, duration_h=12, meter_bias=0.08)
    assert abs(a.water_balance_m3["supplied"] - b.water_balance_m3["supplied"]) < 1e-6
    assert abs(a.water_balance_m3["leaked"] - b.water_balance_m3["leaked"]) < 1e-6
    assert a.water_balance_m3["billed"] > b.water_balance_m3["billed"]


def test_unmetered_share_is_bookkeeping_only():
    a = run_scenario(scenario_id="u0", leaks=[], duration_h=12, unmetered_share={})
    b = run_scenario(scenario_id="u1", leaks=[], duration_h=12, unmetered_share={"J15": 0.5})
    assert abs(a.water_balance_m3["supplied"] - b.water_balance_m3["supplied"]) < 1e-6
    assert abs(a.water_balance_m3["customer"] - b.water_balance_m3["customer"]) < 1e-6
    assert b.water_balance_m3["unmetered"] > 0
    assert a.water_balance_m3["unmetered"] == 0


def test_one_percent_inflow_leak_is_below_sensor_noise(noleak_12h, tiny_leak_12h):
    """White-paper 1% target is not visible as a pressure residual on this DMA."""
    fill = fill_times(noleak_12h)
    dP = (
        noleak_12h.pressure_m.loc[fill, list(JUNCTION_NAMES)].mean()
        - tiny_leak_12h.pressure_m.loc[fill, list(JUNCTION_NAMES)].mean()
    )
    max_dp = float(dP.abs().max())
    assert max_dp < DEFAULT_PRESSURE_SIGMA_M, (
        f"1% leak produced {max_dp:.3f} m of peak dP; "
        "if this fails, the 1% claim became defensible and RESULTS.md must change"
    )


def test_zero_leak_class_has_zero_leak_volume(noleak_12h):
    assert noleak_12h.leaks == []
    assert noleak_12h.water_balance_m3["leaked"] == 0.0
