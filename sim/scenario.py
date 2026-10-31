"""Run one intermittent-supply scenario and return clean fields + bookkeeping.

Observations (noise / dropouts / sensor subset) are applied later by
``sim.observe`` so the same scenario can be re-observed at 5 / 10 / 15 / 20
sensors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

import pandas as pd
import wntr

from sim.balance import customer_demand_lps, leak_flow_frame, water_balance_m3
from sim.demand import DEFAULT_FILL_MINUTES, apply_storage_limited_demand
from sim.leaks import Leak, apply_leaks
from sim.network import INLET_PIPE, JUNCTION_NAMES, build_dma
from sim.schedule import DEFAULT_DURATION_H, apply_rationing_schedule, is_supply_open


@dataclass
class Scenario:
    scenario_id: str
    seed: int
    fill_minutes: float
    leaks: list[Leak]
    unmetered_share: dict[str, float]
    meter_bias: float
    times_s: list[int]
    pressure_m: pd.DataFrame  # clamped >= 0, junctions only
    pressure_raw_m: pd.DataFrame
    head_m: pd.DataFrame
    customer_lps: pd.DataFrame
    leak_lps: pd.DataFrame
    inlet_flow_lps: pd.Series
    water_balance_m3: dict[str, float]
    duration_h: float
    timestep_s: int


def _clamp_pressure(raw: pd.DataFrame, inlet_closed: pd.Series | None = None) -> pd.DataFrame:
    """Turn EPANET slack-node artefacts into a drained (0 m) field.

    With the inlet closed and no outflow path, EPANET keeps a trapped
    residual head that is not a physical drained pipe. Off-window rows
    are therefore zeroed. Negative on-window pressures are clipped to 0.
    """
    out = raw.clip(lower=0.0)
    if inlet_closed is not None:
        out = out.copy()
        out.loc[inlet_closed.values] = 0.0
    return out


def run_scenario(
    *,
    scenario_id: str = "demo",
    seed: int = 0,
    leaks: list[Leak] | None = None,
    unmetered_share: Mapping[str, float] | None = None,
    meter_bias: float = 0.04,
    fill_minutes: float = DEFAULT_FILL_MINUTES,
    duration_h: float = DEFAULT_DURATION_H,
    continuous: bool = False,
) -> Scenario:
    """Build, schedule, simulate. ``continuous=True`` leaves the inlet open.

    ``continuous`` exists so the same engine can be pointed at an
    always-pressurised version of this DMA (not a substitute for
    BattLeDIM / LeakDB).
    """
    leaks = list(leaks or [])
    unmetered_share = dict(unmetered_share or {})

    wn = build_dma()
    if continuous:
        wn.options.time.duration = int(duration_h * 3600)
        wn.options.time.hydraulic_timestep = 300
        wn.options.time.report_timestep = 300
        wn.options.time.pattern_timestep = 300
        wn.options.time.quality_timestep = 300
        # Always-on demand pattern of ones so PDD still has a pattern handle.
        apply_storage_limited_demand(wn, fill_minutes=duration_h * 60)
    else:
        apply_rationing_schedule(wn, duration_h=duration_h)
        apply_storage_limited_demand(wn, fill_minutes=fill_minutes)
    apply_leaks(wn, leaks)

    sim = wntr.sim.EpanetSimulator(wn)
    # Unique prefix so two EPANET runs never clobber each other's temp.inp.
    with TemporaryDirectory(prefix="maji_en_") as tmp:
        results = sim.run_sim(file_prefix=str(Path(tmp) / "en"))

    junctions = list(JUNCTION_NAMES)
    pressure_raw = results.node["pressure"][junctions].astype(float)
    if continuous:
        closed_mask = pd.Series(False, index=pressure_raw.index)
    else:
        closed_mask = pd.Series(
            [not is_supply_open(float(t)) for t in pressure_raw.index],
            index=pressure_raw.index,
        )
    pressure = _clamp_pressure(pressure_raw, closed_mask)
    head = results.node["head"][junctions].astype(float)
    # Keep head consistent with the drained-pressure field.
    if not continuous:
        elev = {n: wn.get_node(n).elevation for n in junctions}
        for n in junctions:
            head.loc[closed_mask.values, n] = elev[n]
    demand = results.node["demand"][junctions].astype(float)
    inlet = results.link["flowrate"][INLET_PIPE].astype(float) * 1000.0  # L/s
    inlet.name = "inlet_flow_lps"

    customer = customer_demand_lps(demand, pressure, leaks)
    leak_lps = leak_flow_frame(pressure, leaks)
    timestep_s = int(wn.options.time.report_timestep)
    balance = water_balance_m3(
        inlet_flow_lps=inlet,
        customer_lps=customer,
        leak_lps=leak_lps,
        unmetered_share=unmetered_share,
        meter_bias=meter_bias,
        timestep_s=timestep_s,
    )

    return Scenario(
        scenario_id=scenario_id,
        seed=seed,
        fill_minutes=fill_minutes if not continuous else duration_h * 60,
        leaks=leaks,
        unmetered_share=unmetered_share,
        meter_bias=meter_bias,
        times_s=[int(t) for t in pressure.index.tolist()],
        pressure_m=pressure,
        pressure_raw_m=pressure_raw,
        head_m=head,
        customer_lps=customer,
        leak_lps=leak_lps,
        inlet_flow_lps=inlet,
        water_balance_m3=balance,
        duration_h=duration_h,
        timestep_s=timestep_s,
    )
