"""Leaks as junction emitters (orifice outflow ∝ √P).

Size is specified as a fraction of that node's base demand at a
reference head (default 20 m). EPANET reports emitter flow inside
``node['demand']``; we recompute Q = C √max(P, 0) so bookkeeping does
not depend on that convention.

Zero-leak scenarios leave every emitter coefficient at None / 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import wntr

from sim.network import customer_junctions


# Q = C * P ** EMITTER_EXPONENT, EPANET default exponent 0.5.
P_REF_M = 20.0
EMITTER_EXPONENT = 0.5


@dataclass(frozen=True)
class Leak:
    node: str
    fraction: float  # of that node's base demand at P_REF_M (bookkeeping)
    emitter_coeff: float  # m^{3}/s / m^{0.5}
    q_ref_lps: float = 0.0  # orifice flow at P_REF_M, litres/s


def emitter_coeff_from_q_lps(q_ref_lps: float, p_ref_m: float = P_REF_M) -> float:
    if q_ref_lps <= 0.0:
        return 0.0
    return (q_ref_lps / 1000.0) / math.sqrt(p_ref_m)


def emitter_coeff_from_fraction(
    base_demand_m3s: float,
    fraction: float,
    p_ref_m: float = P_REF_M,
) -> float:
    if fraction <= 0.0 or base_demand_m3s <= 0.0:
        return 0.0
    q_ref = fraction * base_demand_m3s
    return q_ref / math.sqrt(p_ref_m)


def leak_flow_m3s(coeff: float, pressure_m: float) -> float:
    """Outflow only. Negative EPANET pressures are treated as drained."""
    if coeff <= 0.0 or pressure_m <= 0.0:
        return 0.0
    return coeff * math.sqrt(pressure_m)


def apply_leaks(
    wn: wntr.network.WaterNetworkModel,
    leaks: list[Leak],
) -> None:
    allowed = set(customer_junctions())
    for leak in leaks:
        if leak.node not in allowed:
            raise ValueError(f"leak node {leak.node} is not a customer junction")
        wn.get_node(leak.node).emitter_coefficient = leak.emitter_coeff


def leaks_from_spec(
    wn: wntr.network.WaterNetworkModel,
    spec: list[tuple[str, float]],
) -> list[Leak]:
    """``spec`` is ``[(node, fraction_of_base_demand), ...]``."""
    out: list[Leak] = []
    for node, fraction in spec:
        base = wn.get_node(node).base_demand
        coeff = emitter_coeff_from_fraction(base, fraction)
        out.append(
            Leak(
                node=node,
                fraction=float(fraction),
                emitter_coeff=coeff,
                q_ref_lps=float(fraction * base * 1000.0),
            )
        )
    return out


def leaks_from_q_lps(
    wn: wntr.network.WaterNetworkModel,
    spec: list[tuple[str, float]],
) -> list[Leak]:
    """``spec`` is ``[(node, orifice_flow_lps_at_P_REF), ...]``."""
    out: list[Leak] = []
    for node, q_lps in spec:
        base = wn.get_node(node).base_demand
        coeff = emitter_coeff_from_q_lps(q_lps)
        fraction = (q_lps / 1000.0) / base if base > 0 else 0.0
        out.append(
            Leak(
                node=node,
                fraction=float(fraction),
                emitter_coeff=coeff,
                q_ref_lps=float(q_lps),
            )
        )
    return out


def leak_dict(leaks: list[Leak]) -> dict[str, dict]:
    return {
        lk.node: {
            "fraction": lk.fraction,
            "emitter_coeff": lk.emitter_coeff,
            "q_ref_lps": lk.q_ref_lps,
        }
        for lk in leaks
    }
