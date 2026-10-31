"""Small message-passing net: sparse pressure in, full field + leak q out."""

from __future__ import annotations

import torch
import torch.nn as nn

from model.graph import hazen_williams_q_lps


class MPLayer(nn.Module):
    def __init__(self, hidden: int, edge_dim: int = 3):
        super().__init__()
        self.msg = nn.Sequential(
            nn.Linear(hidden * 2 + edge_dim, hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
        )
        self.upd = nn.Sequential(
            nn.Linear(hidden * 2, hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
        )

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor, edge_attr: torch.Tensor) -> torch.Tensor:
        src, dst = edge_index
        batched = x.dim() == 3
        if batched:
            bsz = x.size(0)
            e_attr = edge_attr.unsqueeze(0).expand(bsz, -1, -1)
            m = self.msg(torch.cat([x[:, src], x[:, dst], e_attr], dim=-1))
            agg = torch.zeros_like(x)
            index = dst.view(1, -1, 1).expand(bsz, -1, x.size(-1))
            agg = agg.scatter_add(1, index, m)
            deg = torch.zeros(bsz, x.size(1), 1, device=x.device)
            deg = deg.scatter_add(1, dst.view(1, -1, 1).expand(bsz, -1, 1), torch.ones(bsz, src.size(0), 1, device=x.device))
            agg = agg / deg.clamp(min=1.0)
            return x + self.upd(torch.cat([x, agg], dim=-1))
        m = self.msg(torch.cat([x[src], x[dst], edge_attr], dim=-1))
        agg = torch.zeros_like(x)
        agg.index_add_(0, dst, m)
        deg = torch.zeros(x.size(0), 1, device=x.device).index_add_(0, dst, torch.ones(src.size(0), 1, device=x.device))
        agg = agg / deg.clamp(min=1.0)
        return x + self.upd(torch.cat([x, agg], dim=-1))


class PressureGNN(nn.Module):
    def __init__(self, in_dim: int = 8, hidden: int = 64, layers: int = 3):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(in_dim, hidden), nn.GELU())
        self.layers = nn.ModuleList([MPLayer(hidden) for _ in range(layers)])
        self.p_head = nn.Linear(hidden, 1)
        self.q_head = nn.Sequential(nn.Linear(hidden, hidden), nn.GELU(), nn.Linear(hidden, 1), nn.Softplus())

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor, edge_attr: torch.Tensor):
        h = self.enc(x)
        for layer in self.layers:
            h = layer(h, edge_index, edge_attr)
        pressure = self.p_head(h).squeeze(-1)
        leak_q = self.q_head(h).squeeze(-1)
        return pressure, leak_q


def physics_residual(
    pressure_m: torch.Tensor,
    leak_lps: torch.Tensor,
    demand_lps: torch.Tensor,
    elev_m: torch.Tensor,
    edge_index: torch.Tensor,
    edge_attr: torch.Tensor,
) -> torch.Tensor:
    """Soft nodal mass-balance using HW flows from predicted heads."""
    head = pressure_m + elev_m
    src, dst = edge_index
    undirected = torch.arange(0, src.size(0), 2, device=src.device)
    s = src[undirected]
    d = dst[undirected]
    length = edge_attr[undirected, 0]
    diam = edge_attr[undirected, 1]
    if pressure_m.dim() == 2:
        dh = head[:, s] - head[:, d]
        q = hazen_williams_q_lps(dh, length.unsqueeze(0), diam.unsqueeze(0))
        bal = demand_lps + leak_lps
        bal = bal.clone()
        index_s = s.view(1, -1).expand(bal.size(0), -1)
        index_d = d.view(1, -1).expand(bal.size(0), -1)
        bal = bal.scatter_add(1, index_s, q)
        bal = bal.scatter_add(1, index_d, -q)
        return bal[:, 1:].pow(2).mean()
    dh = head[s] - head[d]
    q = hazen_williams_q_lps(dh, length, diam)
    bal = (demand_lps + leak_lps).clone()
    bal.index_add_(0, s, q)
    bal.index_add_(0, d, -q)
    return bal[1:].pow(2).mean()
