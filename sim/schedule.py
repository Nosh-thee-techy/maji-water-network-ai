"""Rationing schedule: the inlet pipe opens only during supply windows.

Default windows (hours from midnight, local clock):
    05:00–09:00  and  17:00–21:00

The inlet starts CLOSED (simulation begins at midnight). Controls fire
at each window open/close over the requested duration. This is an
EPANET time-based LINK status control — not a valve curve — so the
network is hydraulically disconnected from the reservoir between
windows. With pressure-driven demand, nodal heads then collapse; we
treat that collapsed state as the drained / slack network. We do
**not** model air-water transients or pipe emptying (see
docs/assumptions.md).
"""

from __future__ import annotations

from typing import Sequence

import wntr
from wntr.network.controls import Control, ControlAction, SimTimeCondition
from wntr.network.model import LinkStatus

from sim.network import INLET_PIPE


# (start_hour, end_hour) on a 24-hour clock.
SUPPLY_WINDOWS_H: tuple[tuple[float, float], ...] = (
    (5.0, 9.0),
    (17.0, 21.0),
)

HYDRAULIC_TIMESTEP_S = 5 * 60  # 5-minute hydraulic / report step
DEFAULT_DURATION_H = 48.0


def hours_to_seconds(hours: float) -> int:
    return int(round(hours * 3600.0))


def expand_windows(
    duration_h: float = DEFAULT_DURATION_H,
    windows: Sequence[tuple[float, float]] = SUPPLY_WINDOWS_H,
) -> list[tuple[int, int]]:
    """Absolute (open_s, close_s) pairs covering ``duration_h`` hours."""
    out: list[tuple[int, int]] = []
    n_days = int(duration_h // 24) + (1 if duration_h % 24 else 0)
    horizon = hours_to_seconds(duration_h)
    for day in range(max(n_days, 1)):
        for start_h, end_h in windows:
            open_s = hours_to_seconds(day * 24 + start_h)
            close_s = hours_to_seconds(day * 24 + end_h)
            if open_s >= horizon:
                continue
            close_s = min(close_s, horizon)
            if close_s > open_s:
                out.append((open_s, close_s))
    return out


def is_supply_open(t_s: float, windows: Sequence[tuple[int, int]] | None = None) -> bool:
    if windows is None:
        windows = expand_windows()
    return any(start <= t_s < end for start, end in windows)


def apply_rationing_schedule(
    wn: wntr.network.WaterNetworkModel,
    *,
    inlet_pipe: str = INLET_PIPE,
    duration_h: float = DEFAULT_DURATION_H,
    windows: Sequence[tuple[float, float]] = SUPPLY_WINDOWS_H,
    timestep_s: int = HYDRAULIC_TIMESTEP_S,
) -> list[tuple[int, int]]:
    """Close the inlet outside supply windows. Returns the expanded windows.

    Also sets the hydraulic / quality / report step and the simulation
    duration so a subsequent ``EpanetSimulator`` run uses this schedule.
    """
    link = wn.get_link(inlet_pipe)
    link.initial_status = LinkStatus.Closed

    expanded = expand_windows(duration_h, windows)
    for i, (open_s, close_s) in enumerate(expanded):
        open_action = ControlAction(link, "status", LinkStatus.Open)
        close_action = ControlAction(link, "status", LinkStatus.Closed)
        open_cond = SimTimeCondition(wn, "==", open_s)
        close_cond = SimTimeCondition(wn, "==", close_s)
        wn.add_control(f"ration_open_{i}", Control(open_cond, open_action))
        wn.add_control(f"ration_close_{i}", Control(close_cond, close_action))

    duration_s = hours_to_seconds(duration_h)
    wn.options.time.duration = duration_s
    wn.options.time.hydraulic_timestep = timestep_s
    wn.options.time.quality_timestep = timestep_s
    wn.options.time.report_timestep = timestep_s
    wn.options.time.pattern_timestep = timestep_s
    wn.options.time.rule_timestep = timestep_s
    return expanded
