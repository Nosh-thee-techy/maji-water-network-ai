# Assumptions log

Every modelling choice that a technical panel is likely to probe.
Updated as the build proceeds. Dates are 2026.

## Network

- **One schematic DMA.** 18 junctions, 25 pipes, one reservoir. Looped core plus two dead-end laterals. Not a traced utility GIS extract. Multi-topology generalisation is future work.
- **Hazen–Williams C = 120** on every pipe (aged metallic / mixed). No per-pipe calibration.
- **Pipe diameters 40–110 mm.** A first-pass 80–200 mm layout had ~0.06 m peak headloss, so leak signatures sat below the 0.3 m sensor noise. Diameters were reduced so peak headloss is a few metres — typical of a small aged district, and the minimum stiffness that makes sparse-pressure localisation a real inverse problem rather than a noise-fitting exercise.
- **Reservoir head 38 m.** With junction elevations 13.5–20 m this gives roughly 12–22 m of nodal head when the inlet is open.
- **Off-window pressure is set to 0 m after the EPANET run.** With the inlet closed and no outflow, EPANET reports a trapped residual head that is not a drained pipe. We treat off-window rows as slack / atmospheric. This is a post-process, not a two-phase model.

## Intermittent supply

- **Rationing is a binary inlet-pipe status.** Open 05:00–09:00 and 17:00–21:00; closed otherwise. No gradual valve, no pump curve, no source-head variation.
- **“Drains when closed” is a pressure collapse, not an air–water transient.** EPANET / WNTR do not empty pipes of water. When the inlet is closed, pressure-driven demand drives nodal heads toward zero; we treat that slack state as drained. A fill / intrusion transient model is out of scope.
- **Hydraulic step = 5 minutes.** 48 h per scenario.

## Demand (storage-limited)

- Household tanks are **not** tank elements. Demand is a pattern that is active only for the first N minutes of each supply window, then zero. This is the storage-limited simplification named in the white paper and must stay visible in code comments and the report.
- **The solver no longer assumes 75 minutes.** Detection finds tank saturation from the inlet hydrograph (two-means knee) and requires leftover flow to persist. The generator now draws fill length from {45, 60, 75, 90, 120, 150} min so `t_sat` is tested off the clock. 75 minutes remains a clock fallback only when the DMA looks continuously supplied. A missing after-fill record is a `sensor_failure`; a scheduled window with no fill surge is `valve_did_not_open`. Neither is reported as a clean DMA.
- Pressure-driven demand (EPANET 2.2 PDD), required pressure 20 m, minimum 0 m.
- **A leak slightly reduces delivered customer volume** under PDD (less residual head in the fill window). A 1.5 L/s leak at J07 cut 12 h customer volume by about 3%. Tests require that customer volume does not *rise* with a leak, and that the PDD drop stays under 5%. We do not claim leak and demand are independent.

## Leaks

- Leaks are **emitters** (orifice outflow ∝ √P) at junctions, not mid-pipe breaks. Size is set as a fraction of that node’s base demand, converted to an emitter coefficient at a reference head.
- Scenarios include a **zero-leak** class. A solver that always predicts a leak fails this class.

## Water balance

- Real vs apparent loss needs inlet flow + billing, not pressure alone.
- Unmetered demand is a tagged share of customer demand at selected nodes.
- Meter bias is a hidden under-registration applied only when computing billed volume. Solvers never see the bias parameter.
- A CIS export (`account_id`, `node`, `billed_m3`, `account_class`) is the partner surface for apparent loss. The residual after leftover and billed is **not** a leak alarm. Unmetered accounts are tagged, not punished. We do not split theft from meter error from that residual.

## Sensors

- Solvers see only what a chamber logger would uplink: noisy pressure at the placed sensors, noisy inlet flow, and valve position (1/0/NaN). They do not see the clean field or leak labels.
- **IWS duty cycle** (not i.i.d. holes): off-window 15-minute heartbeat; every 5 min through fill and a 30-minute after-`t_sat` hold; 15 min for the rest of the open window; always uplink on valve-open or ΔP ≳ 0.5 m. Radio dropouts (3%, 1% cap on the leftover hold) apply only to uplinked steps. A continuously supplied DMA does not sleep.
- Placement is greedy signature-separability on the hydraulic model, not a field survey.

## No-leak recalibration

- A Sunday / after-fill update may shift the **inlet leftover baseline** (and optionally fill-window pressure) only when leftover is below the 0.35 L/s detect threshold. The sensitivity matrix stays frozen. A leak-sized leftover is refused so the model cannot absorb a burst into “normal.”

## Event lifecycle

- An event is open → assign crew → repair → verify leftover fell (below 0.35 L/s or by ≥50%). The dashboard can *simulate* a successful repair; that is labelled, not a field close-out. We ingest a billed file; we do not implement TaKaDu’s work-order lock-in.

## Confidence

- Ensemble spread is **simulation uncertainty**. We do not claim conformal coverage or calibrated confidence: there is no real-network calibration set.

## Benchmarks

- BattLeDIM 2020 (L-Town) and LeakDB are **continuously supplied**. Official 2019 SCADA was scored with Table 3 prices (xmax 300 m, €0.80/m³, €500/crew). That score is a negative control, not intermittent-supply evidence. Results are never blended with our synthetic intermittent numbers.
