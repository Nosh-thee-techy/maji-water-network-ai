# M.A.J.I results (for the Final Report)

Every number is labelled **simulated**, **benchmark**, or **estimated**.
Nothing here is a field measurement. Leak orifices in the synthetic library
are 0.8–3.0 L/s at 20 m of head (about 14–55% of peak DMA inflow ≈ 5.6 L/s).
That is larger than the white paper’s “1% of DMA inflow” target; we did not
have a pressure residual above sensor noise at 1%, and we do not claim that
target.

Repo (public): https://github.com/Nosh-thee-techy/maji-water-network-ai
Tag: `v1-baseline` (scenario library + placement + emitter-calibration baseline).

Current TRL: **3–4** (analytical method + reproducible simulation prototype).
Target TRL: **5–6** after a 90-day single-DMA utility pilot (2027).

---

## Problem (context numbers; not produced by this repo)

| Claim | Number | Label |
| --- | --- | --- |
| Global NRW volume / value | 126 billion m³/y, ~US$39 billion | literature (Liemberger & Wyatt 2019) |
| Kenya public-provider NRW | 48% (2024/25) | WASREB, as cited in the white paper |
| People on intermittent supply | ~1 billion | literature (Taylor et al. 2018) |
| Intrusion prior | ~7 m (~10 psi) | literature (Kumpel & Nelson 2014); **starting prior, not a constant** |

---

## Solution / scientific hook (simulated)

On the 18-node schematic DMA, 12 h excerpt (`fig_storage_vs_leak.png`):

| Quantity | No leak | 1.5 L/s leak at J07 | Label |
| --- | --- | --- | --- |
| Inlet flow during tank-fill window | 5.55 L/s | higher by the orifice | simulated |
| Inlet flow after tank-fill, inlet still open | ≈ 0 L/s | 1.41 L/s | simulated |
| Off-window pressure (clamped) | 0 m | 0 m | simulated (post-process) |

Customer demand is a 75-minute pattern at the start of each 05:00–09:00 and
17:00–21:00 window, **not** a tank element. A leak is an emitter.

---

## Methodology & validation (simulated intermittent DMA)

Library: 300 scenarios × 48 h × 5 min, 57 zero-leak (19%). Solvers see noisy
pressure at the placed sensors plus noisy inlet flow (σ_P = 0.30 m, σ_Q = 0.15 L/s,
3% dropouts). One topology only.

### Localisation error vs sensor count — emitter-calibration baseline

Same 300 scenarios, false-alarm rate held at the operating point of the
after-fill inlet-flow detector (threshold 0.35 L/s).

| Sensors | Mean hops (detected leaks) | % within 3 hops | FPR (n=57 zero-leak) | TPR (n=243) | Label |
| --- | ---: | ---: | ---: | ---: | --- |
| 5 | 1.71 | 86.8% | 0.00 | 1.00 | simulated |
| 10 | 0.77 | 95.9% | 0.00 | 1.00 | simulated |
| 15 | 0.30 | 98.4% | 0.00 | 1.00 | simulated |
| 18 (all junctions) | 0.23 | 97.5% | 0.00 | 1.00 | simulated |

Source: `results/baseline_eval.json`. Figure: `fig_localisation_vs_sensors.png`.

Detection is the scientific hook (after-fill inlet residual). Localisation is
a sparse L1 fit of a sensitivity matrix. This is **not** a single “X% accuracy”
claim.

### Water-balance leak attribution

| Metric | Result | Label |
| --- | --- | --- |
| Mean \|leak% − truth\| (budget 10) | 1.68 percentage points | simulated |
| Median \|leak% − truth\| (budget 10) | 1.79 percentage points | simulated |

Apparent loss (unmetered + meter error) is recovered as customer − billed.
Pressure + inlet flow do **not** split unmetered from meter error; we do not
report that split as a solver output.

### Intrusion-risk windows

| Metric | Result | Label |
| --- | --- | --- |
| Off-window node-hours below 7 m prior | 32 h / 48 h (entire DMA) | simulated; **trivial** — drained by construction |
| In-window share of node-steps below 7 m | 0.023% | simulated |
| Leak scenarios with any in-window P < 7 m | 1.6% | simulated |

Headline: while the inlet is closed the DMA is slack and intrusion is possible
at any opening. During supply, this schematic DMA stays at ~12–22 m, so the
7 m prior almost never fires. A weaker feeder or a much larger leak would
change that. Threshold is a per-deployment prior.

Nodal reconstruction (GNN ensemble, two supply-window snapshots, budget 10):
**1.15 m MAE** on 45 held-out simulated scenarios. That meets the ±2 m
*simulation* target. It is not a real-network calibration.

### Physics-informed GNN vs baseline

Trained offline on the same library (no EPANET in the training loop), budget = 10,
5 seeds, 80% row subsets. Ensemble spread is **simulation uncertainty**, not
conformal coverage. The GNN saw two aggregated windows per scenario (fill /
after-fill), not the full 5-minute sequence.

| Metric | GNN ensemble | Baseline (budget 10) | Label |
| --- | --- | --- | --- |
| Leak TPR | 0.00 | 1.00 | simulated |
| Leak FPR | 0.00 | 0.00 | simulated |
| Mean hops (detected) | — (none detected) | 0.77 | simulated |
| Pressure recon MAE | 1.15 m | n/a (baseline is not a full-field reconstructor) | simulated |
| Mean ensemble spread | 0.61 m | — | simulation uncertainty |

**The GNN did not beat the baseline on leak localisation.** We ship the
emitter-calibration baseline for the dig-here list. The GNN is kept as a
pressure reconstructor (and as a negative result in Section 6).

### Continuous-supply check (same topology — not BattLeDIM)

40 always-pressurised copies of this DMA, budget 10:

| Metric | Result | Label |
| --- | --- | --- |
| FPR | 0.00 | simulated, continuous variant |
| TPR | 1.00 | simulated, continuous variant |
| Mean hops | 0.48 | simulated, continuous variant |

Source: `results/continuous_eval.json`. Do **not** blend with the intermittent table.

### BattLeDIM 2020 / LeakDB

Official year-long L-Town SCADA scoring: **not run** (550 MB dataset).

A short synthetic-leak pass on the published `L-TOWN.inp` (782 junctions, 10
name-strided sensors, 20 candidate nodes, 2 L/s emitters, 8 tests) **did not
recover the true node** (0/8 exact hits). That is not a BattLeDIM score. It
only shows that dropping the same cheap solver onto L-Town without its SCADA
layout and without a hop-aware metric is not enough. Continuous-supply
evidence we *will* stand behind is the 40-scenario always-on copy of our DMA.

---

## Feasibility

| Item | Number | Label |
| --- | --- | --- |
| Logger BOM, LoRaWAN + solar mid | ~US$52–76 / node | estimated (paper costing) |
| Sampling | 5 min baseline, 1 Hz burst on ΔP ≳ 0.5 m | specification |
| DMA hardware at 10 nodes | ~US$600 at the US$60 target | estimated |
| Topologies trained | 1 schematic DMA | fact |
| Field data | none | fact |

Multi-topology generalisation is future work.

---

## Tests (what was actually checked)

`python -m pytest tests -v` runs EPANET, not just mocks.

What passed: mass-balance residual; after-fill inlet ≈ 0 without a leak and ≈ orifice flow with one; off-window pressure clamped to 0; meter bias and unmetered tags do not change hydraulics; solvers never receive leak labels or the clean field; zero-leak scenarios are not called leaks; a 1.5 L/s leak at J07 is found within 3 hops from noisy sensors; a **1% of inflow** leak stays below 0.3 m sensor noise; the 300-scenario library has a real zero-leak class.

What the suite caught: customer volume is **not** independent of a leak. PDD lowers delivered household volume by ~3% for a 1.5 L/s leak. The report must not say the two are decoupled.

What the suite cannot do: field validation, official BattLeDIM scoring, hardware bench tests.

## How to reproduce

```bash
python -m sim.smoke_network
python -m sim.generate -n 300 --duration-h 48
python -m placement.greedy
python -m baseline.evaluate --data data/scenarios --duration-h 48
python -m results.plot_metrics
streamlit run dashboard/app.py
```
