"""Compare the GNN ensemble to the baseline on the same held-out scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from baseline.graph_distance import match_leaks, pipe_graph
from model.dataset import load_split
from model.gnn import PressureGNN
from model.graph import build_graph
from model.train import predict_scenario
from sim.io import load_scenario
from sim.network import JUNCTION_NAMES


def load_ensemble(ckpt_dir: Path, in_dim: int, device: str) -> list[PressureGNN]:
    models = []
    for path in sorted(ckpt_dir.glob("gnn_*.pt")):
        m = PressureGNN(in_dim=in_dim).to(device)
        m.load_state_dict(torch.load(path, map_location=device, weights_only=True))
        m.eval()
        models.append(m)
    return models


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data/scenarios"))
    p.add_argument("--ckpt", type=Path, default=Path("model/checkpoints"))
    p.add_argument("--sensors-json", type=Path, default=Path("results/placement.json"))
    p.add_argument("--out", type=Path, default=Path("results/gnn_eval.json"))
    p.add_argument("--budget", type=int, default=10)
    args = p.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    placement = json.loads(args.sensors_json.read_text(encoding="utf-8"))
    sensors = placement["placements"][str(args.budget)]["sensors"]
    split_path = args.ckpt / "split.json"
    split = json.loads(split_path.read_text(encoding="utf-8")) if split_path.exists() else load_split(args.data)
    graph = build_graph(device)
    models = load_ensemble(args.ckpt, in_dim=8, device=device)
    if not models:
        raise SystemExit("no checkpoints")
    g = pipe_graph()
    names = list(JUNCTION_NAMES)
    rows = []
    for sid in split["test"]:
        preds_p, preds_q = [], []
        pack = None
        for i, m in enumerate(models):
            ph, qh, pack = predict_scenario(m, args.data, sid, sensors, graph, device, obs_seed=9 + i)
            preds_p.append(ph)
            preds_q.append(qh)
        p_stack = np.stack(preds_p)
        q_stack = np.stack(preds_q)
        p_mean = p_stack.mean(0)
        q_mean = q_stack.mean(0)
        p_std = p_stack.std(0)
        q_node = q_mean.mean(0)
        ranked = sorted(zip(names, q_node), key=lambda kv: kv[1], reverse=True)
        meta, _frames = load_scenario(args.data, sid)
        truth = [lk["node"] for lk in meta["leaks"]]
        detected = float(q_node.max()) >= 0.20
        pred = [n for n, v in ranked[: max(1, len(truth))]] if detected else []
        loc = match_leaks(pred, truth, g)
        rec_err = float(np.mean(np.abs(p_mean - pack["p"].numpy())))
        rows.append(
            {
                "id": sid,
                "n_true": len(truth),
                "detected": detected,
                "hops": loc["mean_hops"],
                "recon_mae_m": rec_err,
                "recon_spread_m": float(p_std.mean()),
                "pred": pred,
                "true": truth,
            }
        )
        print(sid, "hops", loc["mean_hops"], "mae", rec_err)
    leaked = [r for r in rows if r["n_true"] > 0]
    zero = [r for r in rows if r["n_true"] == 0]
    hops = [r["hops"] for r in leaked if r["detected"]]
    summary = {
        "budget": args.budget,
        "n_test": len(rows),
        "n_ensemble": len(models),
        "false_positive_rate": sum(1 for r in zero if r["detected"]) / max(len(zero), 1),
        "true_positive_rate": sum(1 for r in leaked if r["detected"]) / max(len(leaked), 1),
        "mean_hops_detected": float(np.mean(hops)) if hops else None,
        "frac_within_3_hops": sum(1 for h in hops if h <= 3) / max(len(hops), 1),
        "mean_recon_mae_m": float(np.mean([r["recon_mae_m"] for r in rows])),
        "mean_simulation_uncertainty_m": float(np.mean([r["recon_spread_m"] for r in rows])),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
