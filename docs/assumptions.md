# Assumptions log

Every modelling choice that a technical panel is likely to probe.
Updated as the build proceeds. Dates are 2026.

## Network

- **One schematic DMA.** 18 junctions, 25 pipes, one reservoir. Looped core plus two dead-end laterals. Not a traced utility GIS extract. Multi-topology generalisation is future work.
- **Hazen–Williams C = 120** on every pipe (aged metallic / mixed). No per-pipe calibration.
- **Reservoir head 42 m.** With junction elevations 13.5–20 m this gives roughly 15–30 m of nodal head when the inlet is open.

## Intermittent supply

- **Rationing is a binary inlet-pipe status.** Open 05:00–09:00 and 17:00–21:00; closed otherwise. No gradual valve, no pump curve, no source-head variation.
- **“Drains when closed” is a pressure collapse, not an air–water transient.** EPANET / WNTR do not empty pipes of water. When the inlet is closed, pressure-driven demand drives nodal heads toward zero; we treat that slack state as drained. A fill / intrusion transient model is out of scope.
- **Hydraulic step = 5 minutes.** 48 h per scenario.

## Demand (storage-limited)

- Household tanks are **not** tank elements. Demand is a pattern that is active only for the first N minutes of each supply window, then zero. This is the storage-limited simplification named in the white paper and must stay visible in code comments and the report.
- Pressure-driven demand (EPANET 2.2 PDD), required pressure 20 m, minimum 0 m.

## Leaks

- Leaks are **emitters** (orifice outflow ∝ √P) at junctions, not mid-pipe breaks. Size is set as a fraction of that node’s base demand, converted to an emitter coefficient at a reference head.
- Scenarios include a **zero-leak** class. A solver that always predicts a leak fails this class.

## Water balance

- Real vs apparent loss needs inlet flow + billing, not pressure alone.
- Unmetered demand is a tagged share of customer demand at selected nodes.
- Meter bias is a hidden under-registration applied only when computing billed volume. Solvers never see the bias parameter.

## Sensors

- Solvers see only noisy, dropped-out pressure at the placed sensors, plus noisy inlet flow.
- Placement is greedy signature-separability on the hydraulic model, not a field survey.

## Confidence

- Ensemble spread is **simulation uncertainty**. We do not claim conformal coverage or calibrated confidence: there is no real-network calibration set.

## Benchmarks

- BattLeDIM 2020 (L-Town) and LeakDB are **continuously supplied**. They support “the same engine still works when the network stays full.” They are not intermittent-supply evidence. Results are never blended with our synthetic intermittent numbers.
