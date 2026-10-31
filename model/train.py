"""Train a small GNN ensemble offline on cached scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from model.dataset import load_split, scenario_tensors
from model.gnn import PressureGNN, physics_residual
from model.graph import build_graph


def _collect(data_dir: Path, ids: list[str], sensors: list[str], seed: int):
    xs, ps, qs, ds = [], [], [], []
    for i, sid in enumerate(ids):
        pack = scenario_tensors(data_dir, sid, sensors, obs_seed=seed + i * 13)
        xs.append(pack["x"])
        ps.append(pack["p"])
        qs.append(pack["q"])
        ds.append(pack["d"])
    return (
        torch.cat(xs, 0),
        torch.cat(ps, 0),
        torch.cat(qs, 0),
        torch.cat(ds, 0),
    )


def train_one(
    x, p, q, d, graph, *, seed: int, epochs: int, lr: float, physics_w: float, device: str
) -> PressureGNN:
    torch.manual_seed(seed)
    model = PressureGNN(in_dim=x.size(-1)).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    ds = TensorDataset(x, p, q, d)
    loader = DataLoader(ds, batch_size=64, shuffle=True)
    edge_index = graph["edge_index"].to(device)
    edge_attr = graph["edge_attr"].to(device)
    elev = graph["elev_m"].to(device)
    model.train()
    for ep in range(epochs):
        total = 0.0
        n = 0
        for xb, pb, qb, db in loader:
            xb, pb, qb, db = xb.to(device), pb.to(device), qb.to(device), db.to(device)
            opt.zero_grad()
            phat, qhat = model(xb, edge_index, edge_attr)
            rec = torch.mean((phat - pb) ** 2)
            leak = torch.mean((qhat - qb) ** 2)
            phys = physics_residual(phat, qhat, db, elev, edge_index, edge_attr)
            loss = rec + 0.4 * leak + physics_w * phys
            loss.backward()
            opt.step()
            total += float(loss)
            n += 1
        if (ep + 1) % 5 == 0 or ep == 0:
            print(f"  seed {seed} epoch {ep+1}/{epochs} loss={total/max(n,1):.4f}")
    return model


@torch.no_grad()
def predict_scenario(model, data_dir, sid, sensors, graph, device, obs_seed):
    pack = scenario_tensors(data_dir, sid, sensors, obs_seed)
    edge_index = graph["edge_index"].to(device)
    edge_attr = graph["edge_attr"].to(device)
    p_hat, q_hat = [], []
    model.eval()
    for i in range(pack["x"].size(0)):
        ph, qh = model(pack["x"][i].to(device), edge_index, edge_attr)
        p_hat.append(ph.cpu().numpy())
        q_hat.append(qh.cpu().numpy())
    return np.stack(p_hat), np.stack(q_hat), pack


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data/scenarios"))
    p.add_argument("--out", type=Path, default=Path("model/checkpoints"))
    p.add_argument("--sensors-json", type=Path, default=Path("results/placement.json"))
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--ensemble", type=int, default=5)
    p.add_argument("--physics-w", type=float, default=0.05)
    p.add_argument("--budget", type=int, default=10)
    args = p.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    placement = json.loads(args.sensors_json.read_text(encoding="utf-8"))
    sensors = placement["placements"][str(args.budget)]["sensors"]
    split = load_split(args.data)
    print("loading train tensors…", len(split["train"]))
    x, pt, qt, dt = _collect(args.data, split["train"], sensors, seed=7)
    print("train samples", x.shape)
    graph = build_graph(device)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "split.json").write_text(json.dumps(split, indent=2), encoding="utf-8")
    for k in range(args.ensemble):
        print(f"ensemble member {k}")
        # subsample 80% of rows
        rng = np.random.default_rng(100 + k)
        n = x.size(0)
        pick = rng.choice(n, size=int(0.8 * n), replace=False)
        model = train_one(
            x[pick],
            pt[pick],
            qt[pick],
            dt[pick],
            graph,
            seed=100 + k,
            epochs=args.epochs,
            lr=1e-3,
            physics_w=args.physics_w,
            device=device,
        )
        torch.save(model.state_dict(), args.out / f"gnn_{k}.pt")
    print(f"wrote {args.ensemble} checkpoints to {args.out}")


if __name__ == "__main__":
    main()
