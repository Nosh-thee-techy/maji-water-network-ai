"""Static DMA graph tensors shared by every training sample."""

from __future__ import annotations

import torch

from sim.network import (
    HW_ROUGHNESS,
    JUNCTION_NAMES,
    base_demands_lps,
    junction_elevations,
    pipe_table,
)


def build_graph(device: str = "cpu") -> dict:
    names = list(JUNCTION_NAMES)
    idx = {n: i for i, n in enumerate(names)}
    elev = junction_elevations()
    demand = base_demands_lps()
    src, dst, length, diam, rough = [], [], [], [], []
    for _pid, a, b, L, D in pipe_table():
        if a not in idx or b not in idx:
            continue  # skip reservoir inlet; treated via inlet-flow feature
        i, j = idx[a], idx[b]
        src.extend([i, j])
        dst.extend([j, i])
        length.extend([L, L])
        diam.extend([D, D])
        rough.extend([HW_ROUGHNESS, HW_ROUGHNESS])
    edge_index = torch.tensor([src, dst], dtype=torch.long, device=device)
    edge_attr = torch.tensor(
        list(zip(length, diam, rough)),
        dtype=torch.float32,
        device=device,
    )
    node_static = torch.tensor(
        [[elev[n] / 20.0, demand[n] / 0.5] for n in names],
        dtype=torch.float32,
        device=device,
    )
    return {
        "names": names,
        "index": idx,
        "edge_index": edge_index,
        "edge_attr": edge_attr,
        "node_static": node_static,
        "elev_m": torch.tensor([elev[n] for n in names], dtype=torch.float32, device=device),
    }


def hazen_williams_q_lps(dh_m: torch.Tensor, length_m: torch.Tensor, diameter_m: torch.Tensor, c: float = 120.0) -> torch.Tensor:
    """Differentiable HW pipe flow (L/s) from head loss (m)."""
    # Q_m3s = ( |dh| * C^1.852 * D^4.87 / (10.67 * L) ) ** (1/1.852)
    num = dh_m.abs() * (c ** 1.852) * (diameter_m ** 4.87)
    den = 10.67 * length_m.clamp(min=1.0)
    q_m3s = (num / den).clamp(min=0.0) ** (1.0 / 1.852)
    return torch.sign(dh_m) * q_m3s * 1000.0
