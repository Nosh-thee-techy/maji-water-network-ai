"""GNN pressure reconstruction — not a leak detector.

    python -m model.recon
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from model.dataset import scenario_tensors
from model.gnn import PressureGNN
from model.graph import build_graph
from model.train import predict_scenario, train_one, _collect
from sim.generate import generate_one
from sim.io import save_scenario
from sim.network import JUNCTION_NAMES

CKPT = Path("model/checkpoints/gnn_recon.pt")
DATA = Path("data/recon")
PLACE = Path("results/placement.json")
N_TRAIN = 20
EPOCHS = 25


def _sensors() -> list[str]:
    raw = json.loads(PLACE.read_text(encoding="utf-8"))
    return raw["placements"]["10"]["sensors"]


def ensure_train_set(n: int = N_TRAIN) -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    index_path = DATA / "index.json"
    if index_path.exists():
        return DATA
    rows = []
    for i in range(n):
        sc = generate_one(i, 3100 + i, 12.0, None)
        save_scenario(sc, DATA)
        rows.append({"scenario_id": sc.scenario_id, "n_leaks": len(sc.leaks), "fill_minutes": sc.fill_minutes})
        print(f"  recon train {sc.scenario_id} leaks={len(sc.leaks)} fill={sc.fill_minutes}")
    index_path.write_text(json.dumps({"scenarios": rows}, indent=2), encoding="utf-8")
    return DATA


def train_recon() -> Path:
    CKPT.parent.mkdir(parents=True, exist_ok=True)
    if CKPT.exists():
        return CKPT
    data = ensure_train_set()
    sensors = _sensors()
    ids = [r["scenario_id"] for r in json.loads((data / "index.json").read_text(encoding="utf-8"))["scenarios"]]
    x, p, q, d = _collect(data, ids, sensors, seed=3)
    print("recon train tensors", tuple(x.shape))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    graph = build_graph(device)
    model = train_one(x, p, q, d, graph, seed=11, epochs=EPOCHS, lr=1e-3, physics_w=0.05, device=device)
    torch.save(model.state_dict(), CKPT)
    print(f"wrote {CKPT}")
    return CKPT


def load_model(device: str = "cpu") -> PressureGNN | None:
    if not CKPT.exists():
        return None
    m = PressureGNN(in_dim=8).to(device)
    m.load_state_dict(torch.load(CKPT, map_location=device, weights_only=True))
    m.eval()
    return m


def reconstruct_window(sid: str, data_dir: Path, sensors: list[str], model: PressureGNN | None) -> dict:
    names = list(JUNCTION_NAMES)
    note = (
        "GNN reconstructs nodal pressure from sparse sensors. "
        "Leak TPR on the library was 0 — this panel is not the dig list."
    )
    if model is None:
        return {"available": False, "note": "No checkpoint. Run python -m model.recon", "snapshots": []}
    device = next(model.parameters()).device
    graph = build_graph(str(device))
    p_hat, q_hat, pack = predict_scenario(model, data_dir, sid, sensors, graph, str(device), obs_seed=9)
    p_true = pack["p"].numpy()
    labels = ["fill", "after"][: p_hat.shape[0]]
    snaps = []
    for i, lab in enumerate(labels):
        mae = float(np.mean(np.abs(p_hat[i] - p_true[i])))
        snaps.append(
            {
                "window": lab,
                "mae_m": mae,
                "p_hat_m": {n: float(p_hat[i, j]) for j, n in enumerate(names)},
                "p_true_m": {n: float(p_true[i, j]) for j, n in enumerate(names)},
            }
        )
    mae_all = float(np.mean(np.abs(p_hat - p_true)))
    return {
        "available": True,
        "mae_m": mae_all,
        "snapshots": snaps,
        "note": note,
        "leak_head_unused": True,
    }


def main() -> None:
    train_recon()


if __name__ == "__main__":
    main()
