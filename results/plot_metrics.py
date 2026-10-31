"""Captioned figures from evaluation JSON. python -m results.plot_metrics"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def plot_localisation_curve(eval_path: Path, out: Path) -> None:
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    budgets = sorted(int(b) for b in data["budgets"])
    hops = [data["budgets"][str(b)]["mean_hops_detected"] for b in budgets]
    within = [data["budgets"][str(b)]["frac_within_3_hops_detected"] for b in budgets]
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.plot(budgets, hops, "o-", color="#1f4e79", lw=2, label="mean hop error (detected leaks)")
    ax.axhline(3.0, color="#c0392b", ls="--", lw=1, label="white-paper target (3 segments)")
    ax.set_xlabel("pressure-sensor budget")
    ax.set_ylabel("mean localisation error (pipe hops)")
    ax.set_xticks(budgets)
    ax.set_ylim(0, max(3.5, max(h + 0.4 for h in hops if h is not None)))
    ax2 = ax.twinx()
    ax2.plot(budgets, [100 * w for w in within], "s--", color="#1e8449", label="% within 3 hops")
    ax2.set_ylabel("% of detected leaks within 3 hops")
    ax2.set_ylim(0, 105)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc="center right")
    ax.set_title("Localisation error vs sensor count (simulated intermittent DMA)")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    print("wrote", out)


def plot_water_balance_demo(eval_path: Path, out: Path) -> None:
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    rows = data["rows"]["10"]
    true = [r["leak_pp_true"] for r in rows]
    hat = [r["leak_pp_hat"] for r in rows]
    fig, ax = plt.subplots(figsize=(5.6, 5.2))
    ax.scatter(true, hat, s=18, c="#1f4e79", alpha=0.7)
    lim = max(max(true), max(hat), 1) * 1.05
    ax.plot([0, lim], [0, lim], "--", color="#7f8c8d")
    ax.set_xlabel("true leak share of supplied (%)")
    ax.set_ylabel("estimated leak share of supplied (%)")
    ax.set_title("Water-balance leak attribution (budget = 10, simulated)")
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    print("wrote", out)


def main() -> None:
    here = Path("results")
    # Prefer the official 48 h eval; fall back to the 24 h debug run.
    src = here / "baseline_eval.json"
    if not src.exists():
        src = here / "baseline_eval_24h.json"
    plot_localisation_curve(src, here / "figures" / "fig_localisation_vs_sensors.png")
    plot_water_balance_demo(src, here / "figures" / "fig_water_balance_leak.png")


if __name__ == "__main__":
    main()
