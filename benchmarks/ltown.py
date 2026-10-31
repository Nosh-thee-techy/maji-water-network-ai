"""Apply the emitter-calibration idea to the published L-Town (BattLeDIM) INP.

Downloads only L-TOWN.inp (nominal model). We inject *synthetic* junction
emitters and localise them from a 10-sensor subset. This is NOT an official
BattLeDIM 2018/2019 score — the year-long SCADA files are not used.
Label: continuous-supply benchmark, L-Town topology, synthetic leaks.
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import wntr
from scipy.optimize import minimize

INP_URL = "https://zenodo.org/records/4017659/files/L-TOWN.inp?download=1"


def fetch_inp(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    print(f"downloading {INP_URL}")
    urllib.request.urlretrieve(INP_URL, dest)
    return dest


def run_pressures(inp: Path, emitters: dict[str, float], duration_h: float = 2.0) -> tuple[list[str], np.ndarray]:
    wn = wntr.network.WaterNetworkModel(str(inp))
    wn.options.time.duration = int(duration_h * 3600)
    wn.options.time.hydraulic_timestep = 3600
    wn.options.time.report_timestep = 3600
    wn.options.hydraulic.demand_model = "PDA"
    for node, c in emitters.items():
        wn.get_node(node).emitter_coefficient = c
    sim = wntr.sim.EpanetSimulator(wn)
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp:
        res = sim.run_sim(file_prefix=str(Path(tmp) / "lt"))
    junctions = list(wn.junction_name_list)
    p = res.node["pressure"][junctions].mean(axis=0).to_numpy(dtype=float)
    return junctions, p


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--inp", type=Path, default=Path("data/raw/L-TOWN.inp"))
    p.add_argument("--out", type=Path, default=Path("results/ltown_synthetic.json"))
    p.add_argument("--n", type=int, default=8)
    args = p.parse_args()
    try:
        fetch_inp(args.inp)
    except Exception as exc:
        print("DOWNLOAD_FAILED", exc)
        args.out.write_text(json.dumps({"status": "not_run", "reason": str(exc)}), encoding="utf-8")
        return

    wn0 = wntr.network.WaterNetworkModel(str(args.inp))
    junctions = [n for n in wn0.junction_name_list if wn0.get_node(n).base_demand > 0]
    print(f"L-Town junctions with demand: {len(junctions)}")
    # 10 well-spaced sensors: pick every k-th by name order (no GIS tour).
    sensors = junctions[:: max(1, len(junctions) // 10)][:10]
    # Reference signatures on a 3-hour snapshot — L-Town is large; keep it short.
    print("baseline pressures…")
    names, p0 = run_pressures(args.inp, {}, duration_h=3.0)
    name_idx = {n: i for i, n in enumerate(names)}
    sensor_idx = [name_idx[s] for s in sensors if s in name_idx]
    rng = np.random.default_rng(4)
    # Build signatures for a subset of candidates (speed).
    candidates = list(rng.choice(junctions, size=min(20, len(junctions)), replace=False))
    q_ref = 2.0  # L/s
    c_ref = (q_ref / 1000.0) / math.sqrt(20.0)
    sigs = []
    for node in candidates:
        print("  sig", node)
        _names, p = run_pressures(args.inp, {node: c_ref}, duration_h=3.0)
        sigs.append(p - p0)
    S = -np.asarray(sigs)[:, sensor_idx].T  # [S, C]

    rows = []
    test_nodes = list(rng.choice(candidates, size=min(args.n, len(candidates)), replace=False))
    for node in test_nodes:
        _names, p = run_pressures(args.inp, {node: c_ref}, duration_h=3.0)
        r = (p0 - p)[sensor_idx]
        r = r + rng.normal(0, 0.30, size=r.shape)

        def obj(q):
            return float(np.sum((S @ q - r) ** 2) + 0.15 * np.sum(np.abs(q)))

        q0 = np.full(len(candidates), 0.1)
        res = minimize(obj, q0, method="L-BFGS-B", bounds=[(0, 8)] * len(candidates))
        q = np.clip(res.x, 0, None)
        pred = candidates[int(np.argmax(q))]
        rows.append({"true": node, "pred": pred, "hit": pred == node})
        print(node, "->", pred, "hit", pred == node)

    summary = {
        "label": "L-Town topology, synthetic 2 L/s emitters, NOT official BattLeDIM scoring",
        "n_junctions": len(wn0.junction_name_list),
        "n_tested": len(rows),
        "exact_node_hit_rate": sum(r["hit"] for r in rows) / max(len(rows), 1),
        "sensors": sensors,
        "rows": rows,
        "status": "ran",
    }
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
