"""Storage-limited customer demand.

Household tanks are NOT modelled as EPANET tank elements. Demand is a
time pattern that is 1.0 for the first ``fill_minutes`` of each supply
window and 0.0 otherwise. After the tank is treated as full, draw stops
regardless of residual pressure. A leak (an emitter) does not stop —
that difference is the scientific hook.

This is an explicit simplification. A true tank would keep a volume
state, overflow, and refill from a lower starting level after a long
outage. We do not model those.
"""

from __future__ import annotations

from typing import Sequence

import wntr

from sim.network import customer_junctions
from sim.schedule import (
    DEFAULT_DURATION_H,
    HYDRAULIC_TIMESTEP_S,
    SUPPLY_WINDOWS_H,
    expand_windows,
    hours_to_seconds,
)

# First 75 minutes of each 4-hour window: households filling roof tanks.
# Remaining ~165 minutes of the window: customer draw is zero.
DEFAULT_FILL_MINUTES = 75
PATTERN_NAME = "storage_fill"


def storage_limited_multipliers(
    duration_h: float = DEFAULT_DURATION_H,
    fill_minutes: float = DEFAULT_FILL_MINUTES,
    timestep_s: int = HYDRAULIC_TIMESTEP_S,
    windows: Sequence[tuple[float, float]] = SUPPLY_WINDOWS_H,
) -> list[float]:
    """One multiplier per hydraulic step, covering ``[0, duration]`` inclusive."""
    duration_s = hours_to_seconds(duration_h)
    n_steps = duration_s // timestep_s + 1
    fill_s = fill_minutes * 60.0
    expanded = expand_windows(duration_h, windows)
    multipliers: list[float] = []
    for i in range(n_steps):
        t = i * timestep_s
        active = 0.0
        for open_s, close_s in expanded:
            if open_s <= t < close_s and (t - open_s) < fill_s:
                active = 1.0
                break
        multipliers.append(active)
    return multipliers


def apply_storage_limited_demand(
    wn: wntr.network.WaterNetworkModel,
    *,
    fill_minutes: float = DEFAULT_FILL_MINUTES,
    duration_h: float | None = None,
    timestep_s: int | None = None,
) -> list[float]:
    """Attach the storage-fill pattern to every customer junction.

    The inlet junction (base demand 0) is left untouched. Existing
    ``customer`` demand timeseries keep their base value and receive
    this pattern.
    """
    if duration_h is None:
        duration_h = wn.options.time.duration / 3600.0
    if timestep_s is None:
        timestep_s = int(wn.options.time.pattern_timestep)

    multipliers = storage_limited_multipliers(
        duration_h=duration_h,
        fill_minutes=fill_minutes,
        timestep_s=timestep_s,
    )
    if PATTERN_NAME in wn.pattern_name_list:
        wn.patterns[PATTERN_NAME].multipliers = multipliers
    else:
        wn.add_pattern(PATTERN_NAME, multipliers)

    for jid in customer_junctions():
        node = wn.get_node(jid)
        for ts in node.demand_timeseries_list:
            ts.pattern_name = PATTERN_NAME
    return multipliers
