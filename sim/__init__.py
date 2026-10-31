"""M.A.J.I hydraulic scenario layer.

Intermittent-supply DMA model, rationing schedule, and (later) leak /
demand / observation generators. This package never trains models; it
only produces physics scenarios that solvers may read.
"""

from sim.demand import apply_storage_limited_demand
from sim.network import JUNCTION_NAMES, build_dma, inlet_pipe_name
from sim.schedule import SUPPLY_WINDOWS_H, apply_rationing_schedule

__all__ = [
    "JUNCTION_NAMES",
    "SUPPLY_WINDOWS_H",
    "apply_rationing_schedule",
    "apply_storage_limited_demand",
    "build_dma",
    "inlet_pipe_name",
]
