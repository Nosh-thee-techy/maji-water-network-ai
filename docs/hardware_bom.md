# Pressure-logger bill of materials (paper costing only)

No firmware is built in this repository. The node is specified so the
capital-cost claim in the report can be checked.

**Sampling.** Not 1 Hz continuous. A 5-minute baseline matches the
hydraulic step used in the twin. The node raises the rate (1 Hz burst
for 30–60 s) only when pressure changes by more than ~0.5 m between
slow samples. That is what a battery or a LoRaWAN duty cycle can
actually carry.

**Target:** about US$60 per node, solar or primary-battery, chamber or
post-mounted, LoRaWAN or NB-IoT.

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
the observation model (`sim/observe.py`), not a lost day.

**DMA capital (target).** 10 nodes × US$60 = US$600 of hardware,
before installation, SIM/LoRa fees, and software. The white paper’s
“under US$1,000 of sensor hardware” holds only at the low end of this
table and with LoRaWAN (no per-node cellular plan).
