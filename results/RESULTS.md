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

Library: 300 scenarios × 48 h × 5 min, 57 zero-leak (19%). The table below was
scored under i.i.d. 3% radio dropouts (σ_P = 0.30 m, σ_Q = 0.15 L/s). Solvers
now see an IWS chamber-logger duty cycle instead; that model is scored on a
separate live 24 × 12 h mixed-fill set further down. Do not blend the two.
One topology only.

### Localisation error vs sensor count — emitter-calibration baseline

Same 300 scenarios, false-alarm rate held at the operating point of the
after-fill inlet-flow detector (threshold 0.35 L/s).

| Sensors | Mean hops (detected leaks) | % within 3 hops | FPR (n=57 zero-leak) | TPR (n=243) | Label |
| --- | ---: | ---: | ---: | ---: | --- |
| 5 | 1.71 | 86.8% | 0.00 | 1.00 | simulated |
| 10 | 0.77 | 95.9% | 0.00 | 1.00 | simulated |
| 15 | 0.30 | 98.4% | 0.00 | 1.00 | simulated |
| 18 (all junctions) | 0.23 | 97.5% | 0.00 | 1.00 | simulated |

Source: `results/baseline_eval.json` (i.i.d. 3% dropouts). Figure:
`fig_localisation_vs_sensors.png`. Observation-model note is slightly stale
relative to the duty-cycle solver; see the live duty-cycle table below.

Detection is the scientific hook (after-fill inlet residual). Localisation is
a sparse L1 fit of a sensitivity matrix. This is **not** a single “X% accuracy”
claim.

### Localisation vs leak size (budget 10)

Same detect threshold (0.35 L/s). Four sites × two noise seeds. Figure:
`fig_localisation_vs_leak_size.png`.

| Orifice at 20 m | ≈ % of peak inflow | Hook TPR | Hook mean hops (all) | Pressure-only TPR | Pressure-only hops (all) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.056 L/s | 1% | 0.00 | 6 (miss) | 0.00 | 6 (miss) |
| 0.15 L/s | ~3% | 0.00 | 6 | 0.00 | 6 |
| 0.25 L/s | ~4% | 0.00 | 6 | 0.00 | 6 |
| 0.40 L/s | ~7% | **1.00** | 4.25 | **0.00** | 6 |
| 0.80 L/s | ~14% | 1.00 | 1.38 | 1.00 | 1.50 |
| 1.50 L/s | ~27% | 1.00 | 0.88 | 1.00 | 0.88 |
| 2.50 L/s | ~45% | 1.00 | 1.00 | 1.00 | 0.75 |

The 1% white-paper target fails for both signals. The hook’s distinct work is
**detection at 0.40 L/s**, where pressure-only still reports no leak.
Localisation at that size is still poor (4.25 hops). From 0.80 L/s up, both
methods work.

### Hook vs pressure-only on the library (first 80 of 300, budget 10)

Library leaks are 0.8–3.0 L/s — the regime where pressure already works.

| Method | n | Zero-leak FPR | TPR | Mean hops (detected) | Within 3 hops |
| --- | ---: | ---: | ---: | ---: | ---: |
| After-fill inlet hook | 80 | 0.00 | 1.00 | 1.17 | 89.4% |
| Pressure only (same 0.35 L/s threshold on the L1 fit) | 80 | 0.00 | 1.00 | 0.83 | 93.9% |

On large leaks, pressure-only localises slightly better. Do not hide that.
The hook is not a better localiser; it is an earlier detector. Figure:
`fig_hook_vs_pressure_only.png`.

### Duty-cycle observe + mixed fill (live 24 × 12 h)

Chamber-logger uplinks (off-window 15 min heartbeat, dense through fill and
30 min after `t_sat`), mixed tank-fill 45–150 min, budget 10. Source:
`results/duty_cycle_eval.json`. **Do not blend** with the 300 × 48 h table.

| Metric | Result | Label |
| --- | --- | --- |
| TPR | 1.00 (18/18) | simulated, duty-cycle, mixed fill |
| FPR | 0.00 (0/6) | simulated; one 45-min zero-leak window was `sensor_failure`, not a leak |
| Mean hops (detected) | 0.81 | simulated |
| Within 3 hops | 94.4% (17/18) | simulated; one 45-min leak sat at 6 hops |
| Hydrograph `t_sat` used | 1.00 | simulated |

### `t_sat` vs true fill minutes

Each fill length run once with no leak and once with 1.5 L/s at J07, 12 h.
Source: `results/mixed_fill.json`. Figure: `fig_tsat_vs_fill.png`.

| True fill (min) | `t_sat` no-leak / leak (h) | Clock (75 min) error |
| ---: | --- | ---: |
| 45 | 5.75 / 5.75 | +30 min |
| 60 | 6.00 / 6.00 | +15 min |
| 75 | 6.25 / 6.25 | 0 |
| 90 | 6.50 / 6.50 | −15 min |
| 120 | 7.00 / 7.00 | −45 min |
| 150 | 7.50 / 7.50 | −75 min |

Hydrograph `t_sat` error is 0 min at every length on this DMA. The 75-minute
clock is only right when the tanks really fill in 75 minutes.

### Event lifecycle and Sunday no-leak update

Implemented and unit-tested, not scored on a library:

- Events: open → assign crew → repair → verify leftover fell below 0.35 L/s
  or by ≥50%. Repair before assign is refused. A simulated repair is labelled.
- Sunday update: shift the after-fill inlet baseline only if leftover is
  already clean. A leak-sized leftover is refused so the frozen sensitivity
  matrix cannot absorb a burst.

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

Official **2019** L-Town SCADA, Table 3 economic score (Vrachimis et al. 2022).
Detector: daily minimum-night-flow residual + 6-hour inflow persist; location
= incident pipe of the loudest pressure drop. **Not** the IWS leftover hook.
Source: `results/battledim_2019.json`. Downloaded evaluation-year CSVs +
nominal INP (~38 MB), not `L-TOWN_Real.inp`.

| Metric | M.A.J.I. (this run) | BattLeDIM winners | Perfect | Label |
| --- | ---: | ---: | ---: | --- |
| TPR | 0.30 (7/23) | 0.57–0.65 | 1.00 | official 2019 SCADA |
| False positives | 52 | (lower) | 0 | official 2019 SCADA |
| Economic score | €144,030 | €260,562–€264,873 | €523,124 | official Table 3 |

We lost, as expected. Night-flow on a 782-node always-on network without a
calibrated EPANET search floods the crew (123 alarms, 64 repeats ignored).
This is a **negative control**. Do **not** blend with the IWS leftover-flow
library. The continuous-supply result we will still stand behind on *our*
topology is the 40-scenario always-on copy of this DMA above.

A short synthetic-leak pass on `L-TOWN.inp` (10 name-strided sensors, 20
candidate nodes, 2 L/s emitters, 8 tests) still **did not** recover the true
node (0/8 exact hits). That remains a topology probe, not a BattLeDIM score.

### CIS / billed file

Partner surface, not a billing product. Leftover inlet flow is real loss; the
billed file gives the commercial residual. Pressure cannot split theft from
meter error or unmetered use. Unmetered accounts are tagged, not alarmed.
Dashboard tab **CIS — billed file** ingests a CSV (`account_id`, `node`,
`billed_m3`) or exports a *simulated* extract from the hidden water balance.
No leak event is opened from the apparent residual.

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

What passed (67 tests): mass-balance residual; after-fill inlet ≈ 0 without a leak and ≈ orifice flow with one; off-window pressure clamped to 0; meter bias and unmetered tags do not change hydraulics; solvers never receive leak labels or the clean field; zero-leak scenarios are not called leaks; a 1.5 L/s leak at J07 is found within 3 hops from noisy sensors; a **1% of inflow** leak stays below 0.3 m sensor noise; leftover 1 L/s × 8 open hours = 28.8 m³/day (not 86.4); Sunday update refuses a leak-sized leftover and absorbs a clean meter offset; event repair before assign is refused; `t_sat` on a 120-minute fill tracks the demand pattern, not the 75-minute clock; CIS apparent residual does not open a leak; official BattLeDIM Table 3 scorer credits on-time exact-link detections and charges €500 per false positive.

What the suite caught: customer volume is **not** independent of a leak. PDD lowers delivered household volume by ~3% for a 1.5 L/s leak. The report must not say the two are decoupled.

What the suite cannot do: field validation, hardware bench tests. Official BattLeDIM 2019 scoring is a separate runner (`python -m benchmarks.battledim`), not a pytest.

## How to reproduce

```bash
python -m sim.smoke_network
python -m sim.generate -n 300 --duration-h 48
python -m placement.greedy
python -m baseline.evaluate --data data/scenarios --duration-h 48
python -m results.mixed_fill
python -m results.duty_eval
python -m benchmarks.battledim
python -m results.plot_metrics
streamlit run dashboard/app.py
```
