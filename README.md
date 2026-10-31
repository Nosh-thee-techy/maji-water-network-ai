# M.A.J.I

Sparse-sensor, physics-informed digital twin for **intermittently supplied** water networks.

Hackathon: Khalifa University–UNESCO Global Water Hackathon 2026, Theme 3.
Team RKO, registration CMAT-00064.

**Scientific hook.** Customer demand is storage-limited — once a household tank fills, draw stops regardless of pressure. A leak is an emitter — it keeps drawing as long as there is pressure. That difference is what lets sparse pressure separate leaks from normal use.

## What is simulated vs real

| Piece | Status |
| --- | --- |
| 18-node schematic DMA + rationing schedule | Simulated (this repo) |
| Storage-limited demand, leak emitters, sensor noise | Simulated (planned next) |
| Emitter-calibration baseline | Planned |
| Physics-informed GNN | Planned |
| BattLeDIM / LeakDB | Continuous-supply *benchmark*, not intermittent evidence |
| Hardware logger | Paper costing only — no firmware |

Current TRL and target TRL will be written in `results/RESULTS.md` once Steps 1–3 have numbers.

## Setup

```bash
python -m pip install -r requirements.txt
python -m sim.smoke_network
```

## Repository layout

```
sim/          scenario generator, network, schedule
placement/    greedy sensor placement
baseline/     emitter-calibration solver
model/        physics-informed GNN
benchmarks/   BattLeDIM / LeakDB runners
dashboard/    Streamlit decision views
results/      metrics, figures, RESULTS.md
docs/         hardware BOM, assumptions log
```

## Team

Blessings Wanjiku (lead), Ravine Rianga, Faruoq Muhammed, Francis Musau, Vivian Njoroge, Peter Kariuki.
Advisor: Prof. Easter Wega. Mentor: Prof. Sarah Mugo.
