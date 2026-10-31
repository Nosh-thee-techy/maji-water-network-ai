"""Ground-truth water balance. Solvers do not see these totals.

supplied  = ∫ inlet flow
leaked    = ∫ C √max(P, 0) at leak nodes
customer  = ∫ actual household draw (PDD demand minus leak outflow)
unmetered = tagged share of customer draw at selected nodes
metered   = customer − unmetered
billed    = metered × (1 − meter_bias)
meter_err = metered − billed

Meter bias is hidden from solvers; it exists so the water-balance
attribution task has a true apparent-loss term.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from sim.leaks import Leak, leak_flow_m3s


LPS_PER_M3S = 1000.0


def _integrate_lps(series_lps: pd.Series, timestep_s: float) -> float:
    """Trapezoid-ish: step integral of L/s → m³."""
    vals = np.nan_to_num(series_lps.to_numpy(dtype=float), nan=0.0)
    if len(vals) == 0:
        return 0.0
    # EPANET reports a stepwise-constant hydraulic state. Rectangle rule.
    return float(np.sum(vals[:-1]) * timestep_s / LPS_PER_M3S) if len(vals) > 1 else 0.0


def customer_demand_lps(
    reported_demand_m3s: pd.DataFrame,
    pressure_m: pd.DataFrame,
    leaks: list[Leak],
) -> pd.DataFrame:
    """Strip emitter outflow from EPANET nodal demand; clamp tiny noise."""
    leak_by_node = {lk.node: lk.emitter_coeff for lk in leaks}
    out = {}
    for col in reported_demand_m3s.columns:
        dem = reported_demand_m3s[col].to_numpy(dtype=float)
        p = pressure_m[col].to_numpy(dtype=float)
        coeff = leak_by_node.get(col, 0.0)
        leak = np.array([leak_flow_m3s(coeff, pi) for pi in p])
        customer = dem - leak
        customer[p <= 0.0] = 0.0
        customer = np.clip(customer, 0.0, None)
        out[col] = customer * LPS_PER_M3S
    return pd.DataFrame(out, index=reported_demand_m3s.index)


def leak_flow_frame(
    pressure_m: pd.DataFrame,
    leaks: list[Leak],
) -> pd.DataFrame:
    data = {}
    for lk in leaks:
        p = pressure_m[lk.node].to_numpy(dtype=float)
        data[lk.node] = [leak_flow_m3s(lk.emitter_coeff, pi) * LPS_PER_M3S for pi in p]
    if not data:
        return pd.DataFrame(index=pressure_m.index)
    return pd.DataFrame(data, index=pressure_m.index)


def water_balance_m3(
    *,
    inlet_flow_lps: pd.Series,
    customer_lps: pd.DataFrame,
    leak_lps: pd.DataFrame,
    unmetered_share: Mapping[str, float],
    meter_bias: float,
    timestep_s: float,
) -> dict[str, float]:
    supplied = _integrate_lps(inlet_flow_lps, timestep_s)
    leaked = float(
        sum(_integrate_lps(leak_lps[c], timestep_s) for c in leak_lps.columns)
    )
    customer = float(
        sum(_integrate_lps(customer_lps[c], timestep_s) for c in customer_lps.columns)
    )
    unmetered = 0.0
    for node, share in unmetered_share.items():
        if node in customer_lps.columns and share > 0.0:
            unmetered += share * _integrate_lps(customer_lps[node], timestep_s)
    metered = customer - unmetered
    billed = metered * (1.0 - meter_bias)
    meter_error = metered - billed
    residual = supplied - leaked - customer
    return {
        "supplied": supplied,
        "leaked": leaked,
        "customer": customer,
        "unmetered": unmetered,
        "metered_true": metered,
        "billed": billed,
        "meter_error": meter_error,
        "residual": residual,  # numerical leftover; should be near 0
    }
