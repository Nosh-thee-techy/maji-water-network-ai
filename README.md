# M.A.J.I

Sparse-sensor, physics-informed digital twin for **intermittently supplied** water networks.

Hackathon: Khalifa University–UNESCO Global Water Hackathon 2026, Theme 3.
Team RKO, registration CMAT-00064.

**Scientific hook.** Customer demand is storage-limited — once a household tank fills, draw stops regardless of pressure. A leak is an emitter — it keeps drawing as long as there is pressure. That difference is what lets sparse pressure (and the inlet meter) separate leaks from normal use.

Public repo: https://github.com/Nosh-thee-techy/maji-water-network-ai
Fallback tag: `v1-baseline` (scenario library + placement + emitter-calibration baseline).

## What is simulated vs real

| Piece | Status |
| --- | --- |
| 18-node schematic DMA, rationing, storage-limited demand, leak emitters, sensor noise | **Simulated** (this repo) |
| Emitter-calibration baseline + localisation-vs-sensor curve | **Simulated**, 300 × 48 h scenarios |
| Physics-informed GNN ensemble | Trained. Reconstructs pressure (1.15 m MAE) but **does not beat the baseline on leaks** |
| Always-on copy of this DMA | **Simulated continuous variant** — not BattLeDIM |
| Official BattLeDIM 2020 / LeakDB scoring | **Not run** (time). Optional synthetic-leak pass on `L-TOWN.inp` is labelled separately |
| Hardware logger | Paper costing only — no firmware |

**Current TRL 3–4.** Target TRL 5–6 after a 90-day single-DMA pilot. One topology only; multi-network generalisation is future work. Ensemble spread is simulation uncertainty, not conformal coverage.

Leak orifices in the library are **0.8–3.0 L/s at 20 m**, not 1% of DMA inflow. Smaller leaks sat below the 0.3 m sensor noise on this network; we do not invent a 1% result.

## Setup

```bash
python -m pip install -r requirements.txt
python -m sim.smoke_network
```

Regenerate and evaluate (several minutes):

```bash
python -m sim.generate -n 300 --duration-h 48
python -m placement.greedy
python -m baseline.evaluate --data data/scenarios --duration-h 48
python -m results.plot_metrics
streamlit run dashboard/app.py
```

Optional:

```bash
python -m model.train --data data/scenarios --epochs 12 --ensemble 5
python -m model.evaluate
python -m benchmarks.continuous_dma --n 40
```

## Repository layout

```
sim/          scenario generator, network, schedule, leaks, noise
placement/    greedy sensor placement
baseline/     emitter-calibration solver (the fallback)
model/        physics-informed GNN (offline; no EPANET in the loop)
benchmarks/   continuous-DMA and L-Town runners
dashboard/    Streamlit: Crew / Manager / Health
results/      metrics.json, RESULTS.md, captioned figures
docs/         hardware BOM, assumptions log
```

Numbers for the 15-page report live in [`results/RESULTS.md`](results/RESULTS.md).

## Team

Blessings Wanjiku (lead), Ravine Rianga, Faruoq Muhammed, Francis Musau, Vivian Njoroge, Peter Kariuki.
Advisor: Prof. Easter Wega. Mentor: Prof. Sarah Mugo.

GitHub collaborators were not added: public handles for the other five members were not in the brief.
