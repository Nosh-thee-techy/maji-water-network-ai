# Figure captions

**fig_dma_network.png** — Schematic 18-junction DMA used for every intermittent-supply result in this repository. Looped core plus two dead-end laterals; one reservoir inlet. Not a traced utility GIS extract.

**fig_storage_vs_leak.png** — Scientific hook. After the 75-minute tank-fill window, inlet flow drops to ~0 without a leak and stays at the orifice flow with a leak. Pressure at the leak node falls by a fraction of a metre to ~1 m depending on size. Simulated, 12 h excerpt.

**fig_localisation_vs_sensors.png** — Mean hop error and % of leaks located within 3 pipe segments vs pressure-sensor budget, emitter-calibration baseline, 300 simulated 48 h scenarios. Leak orifices 0.8–3.0 L/s at 20 m. False-positive rate on 57 zero-leak scenarios was 0 at every budget.

**fig_water_balance_leak.png** — Estimated vs true leak share of supplied volume (percentage points), budget = 10 sensors, same 300 scenarios.

**fig_dashboard_crew.png** — Crew-tab stand-in: DMA with budget-10 sensors and a true leak (scenario s0000).

**fig_dashboard_manager.png** — Manager-tab stand-in: IWA-style water balance for s0000 (simulated m³ / 48 h).

**fig_dashboard_health.png** — Health-tab stand-in: pressure at the leak node vs the 7 m intrusion prior.

**fig_localisation_vs_leak_size.png** — Detection rate and mean hop error vs orifice size (0.056–2.5 L/s), budget 10. The 1% of inflow point fails for both signals. The after-fill hook detects 0.40 L/s; pressure-only does not. Simulated, 4 sites × 2 noise seeds.

**fig_hook_vs_pressure_only.png** — Same 80 library scenarios (leaks 0.8–3.0 L/s): hook vs pressure-only at the same 0.35 L/s threshold. On this large-leak set, pressure-only localises slightly better. The hook’s value is not this panel; it is the 0.40 L/s column of the size curve.

**fig_tsat_vs_fill.png** — Hydrograph `t_sat` vs true tank-fill minutes (45–150). The 75-minute clock is a horizontal line; `t_sat` tracks the demand pattern on no-leak and 1.5 L/s-at-J07 runs. Simulated, 12 h.
