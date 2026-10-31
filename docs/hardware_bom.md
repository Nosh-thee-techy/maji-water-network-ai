# Hardware bill of materials (paper costing only)

No firmware is built in this repository. The stack is specified so the
capital-cost claim in the report can be checked. Full architecture:
`docs/iot_stack.md`.

**Year-1 SKU is the inlet, not a 10-node pressure grid.** Detection is
the after-fill inlet residual. Localisation pressure loggers come
after that residual is trusted.

**Sampling (IWS-aware, not 1 Hz continuous).** Off-window 15-minute
heartbeat. 1 Hz burst for 30–60 s on valve-open or ΔP ≳ 0.5 m. 1-minute
samples from fill until a hydrograph change-point, then 1-minute for
≥30 min on the after-fill plateau (that plateau *is* the leak). 5-minute
for the rest of the open window. A battery or a LoRaWAN duty cycle can
carry that; always-on 1 Hz cannot.

**Pressure-node target:** about US$60 DIY, solar or primary-battery,
**chamber** (not a roadside post — Kericho pilots lost unprotected
master meters to theft). LoRaWAN or NB-IoT. Commercial equivalents
are ~US$520–660 (ThingsLog-class), which is what a WSP actually buys.

| Item | Example class | Qty | Est. USD |
| --- | --- | --- | --- |
| Gauge pressure transducer, 0–10 bar, ±1% FS | industrial 4–20 mA / 0–3.3 V | 1 | 18–28 |
| MCU + radio (LoRaWAN) | STM32WL or ESP32 + SX1276 module | 1 | 8–14 |
| NB-IoT option (instead of LoRa) | SIM7080-class module | 1 | 12–18 |
| LiFePO₄ 18650 + charger / 2 W solar panel | 2000–3000 mAh | 1 | 8–12 |
| IP68 enclosure, cable gland, desiccant | polycarbonate, in-chamber | 1 | 6–10 |
| Brass fitting / isolation valve / pigtail | 1/4" NPT | 1 | 4–6 |
| PCB, passives, antenna, assembly | — | 1 | 4–6 |
| **Total (LoRaWAN + solar, mid)** | | | **~52–76** |

±1% of a 10 bar full scale is ±1 m of head. Reconstruction targets of
±2 m therefore spend half their budget on the gauge. Burst-mode is
what makes a cheap logger useful for a transient; the twin itself
runs on the 5-minute series.

Connectivity is store-and-forward. A dropped uplink is a dropout in
the observation model (`sim/observe.py`), not a lost day. A missing
after-fill window is a sensor-failure event, not a “no leak.”

**DMA capital (honest).**

| SKU | What | Est. USD | Label |
| --- | --- | --- | --- |
| Detection-only | 1 inlet logger: pulse flow + pressure + valve position, chamber | 800–1,500 | estimated; **year-1** |
| Detection + 5 DIY pressure | above + 5 × ~US$60 nodes | 1,200–1,900 | estimated |
| White-paper “10 × US$60” | pressure nodes only, no inlet meter | 600 | estimated; **insufficient** |

The white paper’s “under US$1,000 of sensor hardware” holds for
detection-only if the bulk meter already pulses, or for detection +
DIY pressure. It does not hold for a 10-node commercial grid
(ThingsLog-class ~US$520–660/node). Inlet Qmin must be ≤ 0.2 L/s
or the 0.40 L/s hook is below the meter’s floor.
