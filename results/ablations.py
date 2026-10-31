"""Judge-facing ablations: leak-size curve, and hook vs pressure-only.

    python -m results.ablations
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from baseline.emitter_calibrate import estimate_leaks
from baseline.graph_distance import match_leaks, pipe_graph
from placement.greedy import compute_signatures, greedy_place
from sim.io import load_scenario
from sim.leaks import leaks_from_q_lps
from sim.network import JUNCTION_NAMES, build_dma
from sim.observe import make_observations
from sim.scenario import run_scenario

SENSORS_BUDGET = 10
DURATION_SIZE_H = 12.0
# 0.056 L/s ≈ 1% of the ~5.6 L/s fill-window inflow on this DMA.
LEAK_SIZES_LPS = (0.056, 0.15, 0.25, 0.40, 0.80, 1.50, 2.50)
LEAK_NODES = ("J05", "J07", "J12", "J17")
NOISE_SEEDS = (11, 29)


def _solve(sc, noleak, pack, sensors, seed, use_inlet_hook: bool):
    obs = make_observations(sc.pressure_m, sc.inlet_flow_lps, sensors, seed=seed)
    times = sc.times_s
    p0 = noleak.pressure_m.reindex(times).interpolate().bfill().ffill()
    q0 = noleak.inlet_flow_lps.reindex(times).interpolate().bfill().ffill()
    return estimate_leaks(
        pressure_obs=obs["pressure_m"].to_numpy(dtype=float),
        inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
        sensors=sensors,
        times_s=np.asarray(times),
        p_noleak=p0[list(JUNCTION_NAMES)].to_numpy(dtype=float),
        inlet_noleak_lps=q0.to_numpy(dtype=float),
        sensitivity=pack["signatures"],
        candidate_nodes=pack["leak_nodes"],
        duration_h=sc.duration_h,
        use_inlet_hook=use_inlet_hook,
    )


def _pred_nodes(est, n_true: int) -> list[str]:
    if not est.detected:
        return []
    k = max(1, n_true)
    return [n for n, _v in est.ranked[:k]]


def leak_size_sweep(pack, noleak, sensors, graph) -> dict:
    wn = build_dma()
    rows = []
    for q_lps in LEAK_SIZES_LPS:
        for node in LEAK_NODES:
            print(f"  size {q_lps:.3f} L/s at {node}")
            sc = run_scenario(
                scenario_id=f"sz-{node}-{q_lps}",
                leaks=leaks_from_q_lps(wn, [(node, q_lps)]),
                duration_h=DURATION_SIZE_H,
            )
            for seed in NOISE_SEEDS:
                for hook in (True, False):
                    est = _solve(sc, noleak, pack, sensors, seed, hook)
                    loc = match_leaks(_pred_nodes(est, 1), [node], graph)
                    rows.append(
                        {
                            "q_lps": q_lps,
                            "node": node,
                            "seed": seed,
                            "hook": hook,
                            "detected": est.detected,
                            "hops": loc["mean_hops"],
                            "pred": _pred_nodes(est, 1),
                        }
                    )
    by_size = {}
    for q_lps in LEAK_SIZES_LPS:
        for hook, key in ((True, "hook"), (False, "pressure_only")):
            sub = [r for r in rows if r["q_lps"] == q_lps and r["hook"] is hook]
            det = [r for r in sub if r["detected"]]
            by_size.setdefault(str(q_lps), {})[key] = {
                "n": len(sub),
                "tpr": sum(1 for r in sub if r["detected"]) / max(len(sub), 1),
                "mean_hops_detected": float(np.mean([r["hops"] for r in det])) if det else None,
                "mean_hops_all": float(np.mean([r["hops"] for r in sub])),
                "frac_within_3_detected": (
                    sum(1 for r in det if r["hops"] <= 3) / max(len(det), 1) if det else 0.0
                ),
            }
    return {"rows": rows, "by_size": by_size}


def hook_vs_pressure_library(pack, noleak, sensors, graph, data_dir: Path, max_n: int = 80) -> dict:
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    ids = [row["scenario_id"] for row in index["scenarios"]][:max_n]
    summary = {"hook": [], "pressure_only": []}
    for sid in ids:
        meta, frames = load_scenario(data_dir, sid)
        # wrap as a tiny object with the fields _solve expects
        class _SC:
            pass

        sc = _SC()
        sc.pressure_m = frames["pressure_m"]
        sc.inlet_flow_lps = frames["inlet_flow_lps"]
        sc.times_s = meta["times_s"]
        sc.duration_h = meta["duration_h"]
        truth = [lk["node"] for lk in meta["leaks"]]
        for hook, key in ((True, "hook"), (False, "pressure_only")):
            est = _solve(sc, noleak, pack, sensors, meta["seed"] + 10, hook)
            loc = match_leaks(_pred_nodes(est, len(truth)), truth, graph)
            summary[key].append(
                {
                    "id": sid,
                    "n_true": len(truth),
                    "detected": est.detected,
                    "hops": loc["mean_hops"],
                }
            )
        print(f"  library {sid}")
    out = {}
    for key, rows in summary.items():
        zero = [r for r in rows if r["n_true"] == 0]
        leaked = [r for r in rows if r["n_true"] > 0]
        hops = [r["hops"] for r in leaked if r["detected"]]
        out[key] = {
            "n": len(rows),
            "n_zero": len(zero),
            "n_leak": len(leaked),
            "fpr": sum(1 for r in zero if r["detected"]) / max(len(zero), 1),
            "tpr": sum(1 for r in leaked if r["detected"]) / max(len(leaked), 1),
            "mean_hops_detected": float(np.mean(hops)) if hops else None,
            "frac_within_3_detected": (
                sum(1 for h in hops if h <= 3) / max(len(hops), 1) if hops else 0.0
            ),
        }
    return out


def plot_leak_size(by_size: dict, out: Path) -> None:
    sizes = [float(k) for k in by_size]
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.2))
    for key, color, label in (
        ("hook", "#1f4e79", "after-fill inlet hook"),
        ("pressure_only", "#c0392b", "pressure only"),
    ):
        tpr = [100 * by_size[str(s)][key]["tpr"] for s in sizes]
        hops = [
            by_size[str(s)][key]["mean_hops_all"]
            if by_size[str(s)][key]["mean_hops_all"] is not None
            else np.nan
            for s in sizes
        ]
        axes[0].plot(sizes, tpr, "o-", color=color, lw=2, label=label)
        axes[1].plot(sizes, hops, "o-", color=color, lw=2, label=label)
    axes[0].axvline(0.056, color="#7f8c8d", ls=":", lw=1)
    axes[0].text(0.07, 12, "1% of\ninflow", color="#7f8c8d", fontsize=8)
    axes[0].set_xlabel("leak orifice at 20 m (L/s)")
    axes[0].set_ylabel("detection rate (%)")
    axes[0].set_ylim(-5, 105)
    axes[0].set_title("Detection vs leak size")
    axes[0].legend(frameon=False, loc="lower right")
    axes[1].axhline(3.0, color="#8e44ad", ls="--", lw=1, label="3-hop target")
    axes[1].axvline(0.056, color="#7f8c8d", ls=":", lw=1)
    axes[1].set_xlabel("leak orifice at 20 m (L/s)")
    axes[1].set_ylabel("mean hops (misses count as 6)")
    axes[1].set_title("Localisation vs leak size")
    axes[1].legend(frameon=False)
    fig.suptitle("Simulated intermittent DMA, budget = 10 sensors, 4 sites × 2 noise seeds")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    print("wrote", out)


def plot_hook_vs_pressure(lib: dict, out: Path) -> None:
    labels = ["False-positive\nrate (%)", "True-positive\nrate (%)", "Mean hops\n(detected)"]
    hook = [
        100 * lib["hook"]["fpr"],
        100 * lib["hook"]["tpr"],
        lib["hook"]["mean_hops_detected"] or 0,
    ]
    press = [
        100 * lib["pressure_only"]["fpr"],
        100 * lib["pressure_only"]["tpr"],
        lib["pressure_only"]["mean_hops_detected"] or 0,
    ]
    x = np.arange(len(labels))
    w = 0.35
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.bar(x - w / 2, hook, w, color="#1f4e79", label="after-fill inlet hook")
    ax.bar(x + w / 2, press, w, color="#c0392b", label="pressure only")
    ax.set_xticks(x, labels)
    ax.set_title(
        f"Same {lib['hook']['n']} library scenarios, budget 10 — hook vs pressure-only"
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    print("wrote", out)


def main() -> None:
    print("building signatures…")
    pack = compute_signatures(duration_h=12.0)
    sensors = greedy_place(pack["signatures"], pack["junctions"], SENSORS_BUDGET)
    print("sensors", sensors)
    noleak12 = run_scenario(scenario_id="ablate-noleak12", leaks=[], duration_h=DURATION_SIZE_H)
    graph = pipe_graph()

    print("leak-size sweep…")
    size_pack = leak_size_sweep(pack, noleak12, sensors, graph)

    lib = None
    data_dir = Path("data/scenarios")
    if (data_dir / "index.json").exists():
        print("hook vs pressure-only on library…")
        noleak48 = run_scenario(scenario_id="ablate-noleak48", leaks=[], duration_h=48.0)
        lib = hook_vs_pressure_library(pack, noleak48, sensors, graph, data_dir, max_n=80)
    else:
        print("no library on disk; library ablation skipped")

    out_json = {
        "sensors": sensors,
        "leak_size": size_pack["by_size"],
        "library_hook_vs_pressure": lib,
        "label": "simulated",
    }
    Path("results/ablations.json").write_text(json.dumps(out_json, indent=2), encoding="utf-8")
    plot_leak_size(size_pack["by_size"], Path("results/figures/fig_localisation_vs_leak_size.png"))
    if lib:
        plot_hook_vs_pressure(lib, Path("results/figures/fig_hook_vs_pressure_only.png"))
    print(json.dumps({k: v for k, v in out_json.items() if k != "leak_size"}, indent=2))
    print(json.dumps(out_json["leak_size"], indent=2))


if __name__ == "__main__":
    main()
