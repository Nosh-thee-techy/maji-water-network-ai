"""Hop distance on the DMA pipe graph (one hop = one pipe segment)."""

from __future__ import annotations

import networkx as nx
import numpy as np
from scipy.optimize import linear_sum_assignment

from sim.network import pipe_table


def pipe_graph() -> nx.Graph:
    g = nx.Graph()
    for _pid, start, end, _length, _dia in pipe_table():
        g.add_edge(start, end)
    return g


def hop_distance(a: str, b: str, graph: nx.Graph | None = None) -> int:
    g = graph or pipe_graph()
    if a not in g or b not in g:
        return 99
    try:
        return int(nx.shortest_path_length(g, a, b))
    except nx.NetworkXNoPath:
        return 99


def match_leaks(
    predicted: list[str],
    truth: list[str],
    graph: nx.Graph | None = None,
) -> dict:
    """Hungarian match of predicted leak nodes to true leak nodes.

    Extra predictions or misses are charged as ``miss_cost`` hops (6).
    """
    g = graph or pipe_graph()
    miss_cost = 6
    if not truth and not predicted:
        return {"mean_hops": 0.0, "pairs": [], "n_true": 0, "n_pred": 0, "perfect": True}
    if not truth:
        return {
            "mean_hops": float(miss_cost),
            "pairs": [],
            "n_true": 0,
            "n_pred": len(predicted),
            "perfect": False,
        }
    if not predicted:
        return {
            "mean_hops": float(miss_cost),
            "pairs": [],
            "n_true": len(truth),
            "n_pred": 0,
            "perfect": False,
        }
    cost = np_cost(predicted, truth, g, miss_cost)
    # Pad to square
    n = max(len(predicted), len(truth))
    padded = np.full((n, n), miss_cost, dtype=float)
    padded[: cost.shape[0], : cost.shape[1]] = cost
    ri, ci = linear_sum_assignment(padded)
    hops = [float(padded[i, j]) for i, j in zip(ri, ci)]
    pairs = []
    for i, j in zip(ri, ci):
        if i < len(predicted) and j < len(truth):
            pairs.append(
                {
                    "pred": predicted[i],
                    "true": truth[j],
                    "hops": hop_distance(predicted[i], truth[j], g),
                }
            )
    return {
        "mean_hops": float(sum(hops) / len(hops)),
        "pairs": pairs,
        "n_true": len(truth),
        "n_pred": len(predicted),
        "perfect": all(p["hops"] == 0 for p in pairs) and len(predicted) == len(truth),
    }


def np_cost(predicted, truth, graph, miss_cost):
    import numpy as np

    c = np.zeros((len(predicted), len(truth)))
    for i, p in enumerate(predicted):
        for j, t in enumerate(truth):
            c[i, j] = hop_distance(p, t, graph)
    return c
