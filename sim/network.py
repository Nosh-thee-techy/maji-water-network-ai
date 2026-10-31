"""Kibera-scale schematic DMA: 18 junctions, looped core + laterals.

This is a *schematic* district metered area, not a traced utility GIS
extract. One reservoir feeds a single inlet; the rest is a gravity-
sloping grid with two dead-end branches. Elevations and pipe sizes are
chosen so that, with the inlet open, typical nodal heads sit in the
15–30 m range — enough to supply, low enough that a closed inlet
collapses pressure.

The network is the only topology used in this hackathon build. Claims
about multi-topology generalisation are out of scope (see docs/assumptions).
"""

from __future__ import annotations

from typing import Iterable

import wntr


# Reservoir / inlet
RESERVOIR_ID = "R1"
INLET_JUNCTION = "J00"
INLET_PIPE = "P_IN"

# Clockwise loop + laterals. J00 is the DMA inlet (zero customer demand).
# Coordinates are metres in a local plan; elevations are metres above datum.
_JUNCTIONS: dict[str, dict] = {
    # id: (x, y, elevation_m, base_demand_lps)
    # Base demand is the *potential* customer draw used later as a scale
    # for the storage-limited pattern. J00 is the metering point, not a
    # household cluster.
    "J00": dict(x=80.0, y=220.0, elev=20.0, demand=0.00),
    "J01": dict(x=160.0, y=280.0, elev=19.0, demand=0.35),
    "J02": dict(x=260.0, y=280.0, elev=18.5, demand=0.40),
    "J03": dict(x=360.0, y=280.0, elev=18.0, demand=0.30),
    "J04": dict(x=160.0, y=200.0, elev=18.0, demand=0.45),
    "J05": dict(x=260.0, y=200.0, elev=17.5, demand=0.50),
    "J06": dict(x=360.0, y=200.0, elev=17.0, demand=0.40),
    "J07": dict(x=460.0, y=200.0, elev=16.5, demand=0.25),  # east lateral
    "J08": dict(x=160.0, y=120.0, elev=17.0, demand=0.40),
    "J09": dict(x=260.0, y=120.0, elev=16.5, demand=0.45),
    "J10": dict(x=360.0, y=120.0, elev=16.0, demand=0.35),
    "J11": dict(x=160.0, y=40.0, elev=16.0, demand=0.30),
    "J12": dict(x=260.0, y=40.0, elev=15.5, demand=0.35),
    "J13": dict(x=360.0, y=40.0, elev=15.0, demand=0.30),
    "J14": dict(x=460.0, y=40.0, elev=14.5, demand=0.20),  # south-east lateral
    "J15": dict(x=80.0, y=40.0, elev=15.5, demand=0.25),  # south-west branch
    "J16": dict(x=80.0, y=-40.0, elev=14.5, demand=0.20),
    "J17": dict(x=80.0, y=-120.0, elev=13.5, demand=0.15),  # dead end
}

# (start, end, length_m, diameter_m). Lengths are rounded schematic values,
# not Euclidean — they stand in for real routing around streets.
# Diameters are small-district (50–110 mm), not transmission mains.
# The first-pass 80–200 mm layout had ~0.06 m of headloss at peak
# demand, so a leak was invisible against 0.3 m sensor noise. These
# sizes put peak headloss in the 2–8 m range, which is what leak
# localisation actually needs.
_PIPES: list[tuple[str, str, str, float, float]] = [
    # inlet
    (INLET_PIPE, RESERVOIR_ID, INLET_JUNCTION, 90.0, 0.080),
    # north spine
    ("P01", "J00", "J01", 110.0, 0.090),
    ("P02", "J01", "J02", 100.0, 0.080),
    ("P03", "J02", "J03", 100.0, 0.050),
    # mid spine
    ("P04", "J00", "J04", 90.0, 0.090),
    ("P05", "J04", "J05", 100.0, 0.080),
    ("P06", "J05", "J06", 100.0, 0.065),
    ("P07", "J06", "J07", 100.0, 0.050),
    # south spine
    ("P08", "J04", "J08", 80.0, 0.080),
    ("P09", "J08", "J09", 100.0, 0.065),
    ("P10", "J09", "J10", 100.0, 0.050),
    ("P11", "J08", "J11", 80.0, 0.065),
    ("P12", "J11", "J12", 100.0, 0.050),
    ("P13", "J12", "J13", 100.0, 0.050),
    ("P14", "J13", "J14", 100.0, 0.040),
    # south-west branch
    ("P15", "J11", "J15", 80.0, 0.050),
    ("P16", "J15", "J16", 80.0, 0.040),
    ("P17", "J16", "J17", 80.0, 0.040),
    # verticals that close the loops
    ("P18", "J01", "J04", 80.0, 0.065),
    ("P19", "J02", "J05", 80.0, 0.050),
    ("P20", "J03", "J06", 80.0, 0.040),
    ("P21", "J05", "J09", 80.0, 0.050),
    ("P22", "J06", "J10", 80.0, 0.040),
    ("P23", "J09", "J12", 80.0, 0.050),
    ("P24", "J10", "J13", 80.0, 0.040),
]

HW_ROUGHNESS = 120.0  # Hazen–Williams C, aged metallic / mixed
RESERVOIR_HEAD_M = 38.0
RESERVOIR_XY = (0.0, 220.0)

# Required / minimum pressure for EPANET 2.2 pressure-driven demand.
# These are hydraulic solver settings, not the intrusion-risk threshold
# (that lives in the health view and is a per-deployment prior).
REQUIRED_PRESSURE_M = 20.0
MINIMUM_PRESSURE_M = 0.0

JUNCTION_NAMES: tuple[str, ...] = tuple(_JUNCTIONS.keys())


def inlet_pipe_name() -> str:
    return INLET_PIPE


def customer_junctions() -> tuple[str, ...]:
    """Junctions that can carry household demand (excludes the inlet)."""
    return tuple(j for j, spec in _JUNCTIONS.items() if spec["demand"] > 0.0)


def build_dma(name: str = "maji-dma-v1") -> wntr.network.WaterNetworkModel:
    """Return a fresh WNTR model of the schematic DMA.

    The inlet pipe is created OPEN. Call ``apply_rationing_schedule``
    afterwards to close it outside the supply windows.
    """
    wn = wntr.network.WaterNetworkModel()
    wn.name = name

    wn.add_reservoir(
        RESERVOIR_ID,
        base_head=RESERVOIR_HEAD_M,
        coordinates=RESERVOIR_XY,
    )

    for jid, spec in _JUNCTIONS.items():
        # WNTR / EPANET store demand in m3/s.
        wn.add_junction(
            jid,
            base_demand=spec["demand"] / 1000.0,
            elevation=spec["elev"],
            coordinates=(spec["x"], spec["y"]),
            demand_category="customer",
        )

    for pid, start, end, length, diameter in _PIPES:
        wn.add_pipe(
            pid,
            start,
            end,
            length=length,
            diameter=diameter,
            roughness=HW_ROUGHNESS,
            minor_loss=0.0,
        )

    wn.options.hydraulic.demand_model = "PDD"
    wn.options.hydraulic.required_pressure = REQUIRED_PRESSURE_M
    wn.options.hydraulic.minimum_pressure = MINIMUM_PRESSURE_M
    wn.options.hydraulic.headloss = "H-W"
    wn.options.report.energy = "NO"
    return wn


def junction_coordinates() -> dict[str, tuple[float, float]]:
    return {jid: (spec["x"], spec["y"]) for jid, spec in _JUNCTIONS.items()}


def junction_elevations() -> dict[str, float]:
    return {jid: spec["elev"] for jid, spec in _JUNCTIONS.items()}


def base_demands_lps() -> dict[str, float]:
    return {jid: spec["demand"] for jid, spec in _JUNCTIONS.items()}


def pipe_table() -> list[tuple[str, str, str, float, float]]:
    return list(_PIPES)


def summarise(wn: wntr.network.WaterNetworkModel) -> dict:
    n_j = wn.num_junctions
    n_p = wn.num_pipes
    n_r = wn.num_reservoirs
    looped = n_p - (n_j + n_r - 1)  # extra pipes beyond a spanning tree
    return {
        "junctions": n_j,
        "pipes": n_p,
        "reservoirs": n_r,
        "inlet_pipe": INLET_PIPE,
        "loop_excess_pipes": looped,
        "customer_junctions": list(customer_junctions()),
    }


def assert_topology(wn: wntr.network.WaterNetworkModel) -> None:
    """Sanity checks used by the first-commit smoke test."""
    assert wn.num_junctions == 18, wn.num_junctions
    assert RESERVOIR_ID in wn.reservoir_name_list
    assert INLET_PIPE in wn.pipe_name_list
    link = wn.get_link(INLET_PIPE)
    start, end = link.start_node_name, link.end_node_name
    assert {start, end} == {RESERVOIR_ID, INLET_JUNCTION}
    # Looped + branched: more pipes than a tree, and at least one degree-1
    # customer node (the dead-end).
    degrees = {n: 0 for n in wn.junction_name_list}
    for pipe in wn.pipe_name_list:
        s = wn.get_link(pipe).start_node_name
        e = wn.get_link(pipe).end_node_name
        if s in degrees:
            degrees[s] += 1
        if e in degrees:
            degrees[e] += 1
    dead_ends = [n for n, d in degrees.items() if d == 1 and n != INLET_JUNCTION]
    assert dead_ends, "expected a branched dead-end"
    extra = wn.num_pipes - (wn.num_junctions + wn.num_reservoirs - 1)
    assert extra >= 3, extra


def iter_customer_nodes(wn: wntr.network.WaterNetworkModel) -> Iterable[str]:
    for name in customer_junctions():
        if name in wn.node_name_list:
            yield name
