# M.A.J.I

Sparse-sensor, physics-informed digital twin for **intermittently supplied** water networks.

Hackathon: Khalifa University–UNESCO Global Water Hackathon 2026, Theme 3.
Team RKO, registration CMAT-00064.

**Hosted operator desk:** https://maji-iws.fly.dev/

Public repo: https://github.com/Nosh-thee-techy/maji-water-network-ai  
Final report: [`docs/MAJI_Final_Report.pdf`](docs/MAJI_Final_Report.pdf)

**Scientific hook.** Customer demand is storage-limited — once a household tank fills, draw stops regardless of pressure. A leak is an emitter — it keeps drawing as long as there is pressure. That difference is what lets sparse pressure (and the inlet meter) separate leaks from normal use.

Fallback tag: `v1-baseline` (scenario library + placement + emitter-calibration baseline).

## What is simulated vs real

| Piece | Status |
| --- | --- |
| 18-node schematic DMA, rationing, storage-limited demand, leak emitters, sensor noise | **Simulated** (this repo) |
| Emitter-calibration baseline + localisation-vs-sensor curve | **Simulated**, 300 × 48 h scenarios |
| Physics-informed GNN ensemble | Trained. Reconstructs pressure (1.15 m MAE) but **does not beat the baseline on leaks** |
| Always-on copy of this DMA | **Simulated continuous variant** — not BattLeDIM |
| Official BattLeDIM 2019 SCADA | **Ran** as a labelled continuous negative control (TPR 0.30, €144k vs winners ~€261–265k). Do not blend with IWS numbers |
| CIS / billed file | Partner ingest. Apparent residual is not a leak alarm |
| Hardware logger | Paper costing only — no firmware |

**Current TRL 3–4.** Target TRL 5–6 after a 90-day single-DMA pilot. One topology only; multi-network generalisation is future work. Ensemble spread is simulation uncertainty, not conformal coverage.

Leak orifices in the library are **0.8–3.0 L/s at 20 m**, not 1% of DMA inflow. Smaller leaks sat below the 0.3 m sensor noise on this network; we do not invent a 1% result.

## Setup

```bash
python -m pip install -r requirements.txt
python -m sim.smoke_network
python -m pytest tests -v
python -m sim.demo_library
```

Operator UI (React + FastAPI) — this is the frontend to show:

```bash
pip install fastapi uvicorn
cd web && npm install && npm run dev
# other terminal:
uvicorn api.main:app --port 8000
```

Open http://localhost:5173. The API is http://127.0.0.1:8000. Streamlit (`streamlit run dashboard/app.py`) remains as a lab console.

To skip local setup, use the hosted desk: **https://maji-iws.fly.dev/**. It sleeps when idle; the first click after a pause can take about 30 seconds.

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
python -m model.recon          # pressure twin only — leak TPR was 0; never used to call a leak
python -m model.train --data data/scenarios --epochs 12 --ensemble 5
python -m model.evaluate
python -m benchmarks.continuous_dma --n 40
python -m benchmarks.battledim
```

## Repository layout

```
sim/          scenario generator, network, schedule, leaks, noise
placement/    greedy sensor placement
baseline/     emitter-calibration solver (the fallback)
model/        physics-informed GNN (offline; no EPANET in the loop)
benchmarks/   continuous-DMA and L-Town runners
dashboard/    Streamlit: Crew / Manager / Health / Events / CIS
results/      metrics.json, RESULTS.md, captioned figures
docs/         hardware BOM, assumptions log
```

**Live desk:** https://maji-iws.fly.dev/  
Final report (PDF): [`docs/MAJI_Final_Report.pdf`](docs/MAJI_Final_Report.pdf). Source and numbers: [`docs/MAJI_Final_Report.md`](docs/MAJI_Final_Report.md), [`results/RESULTS.md`](results/RESULTS.md).

## Team

Blessings Wanjiku (lead), Ravine Rianga, Faruoq Muhammed, Francis Musau, Vivian Njoroge, Peter Kariuki.
Advisor: Prof. Easter Wega. Mentor: Prof. Sarah Mugo.

GitHub collaborators were not added: public handles for the other five members were not in the brief.
