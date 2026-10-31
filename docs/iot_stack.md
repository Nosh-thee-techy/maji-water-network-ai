# What we adopt, how we beat it, and the IoT stack

No firmware is built here. This note is the field architecture the
prototype is written against, and the product choices the report should
defend.

## Adopt (do not reinvent)

| Source | Steal this | Do not steal |
| --- | --- | --- |
| **Al-Washali / Zarqa** | Saturation from the **inlet hydrograph**, not a clock. Mechanical inlet meter with a published Qmin. 15-minute logging was enough to wait for tanks. Four pressure loggers + one inlet. | Converting the DMA to 24/7 for 63 hours. |
| **TaKaDu** | Event lifecycle: open → assign crew → repair → **verify the hydrograph fell**. One event per root cause, not alert spam. DMA-size vs smallest-detectable-leak honesty. | Historic-pattern ML that assumes a nightline. |
| **SmartTerra** | Billing / CIS for apparent loss. Crew confirm/correct → model improves. Works on messy existing SCADA + monthly reads. Field app for non-engineers. | Vendor 75% / 80% accuracy claims without a methods paper. |
| **i2O / Mueller** | They **schedule** the inlet; we **read** leftover flow on the same meter. Soft-open so the fill surge does not burst an empty main. Logger: 1–15 min log, 1 s–1 min sample, send 5 min–daily, ≥1 year local store, NB-IoT. Different alarm rules by time-of-day. | Competing on PRV control. |
| **HWM MultiLog** | Pseudo-log true min/max inside the interval. **Secondary logging** on alarm (our 1 Hz burst when ΔP ≳ 0.5 m). Remote firmware. | UK always-on nightline firmware defaults. |
| **PUB ALF** | Daily (or weekly) recalibration of the no-leak baseline. Separate **sensor-failure** events from leak events. Cluster anomalies into one event. | 90-sensor continuous twin as a year-1 target. |
| **WASREB / WaterWorX / Miya** | Payment unit: lump sum per DMA established + fee per **m³/day leakage reduced**. Manager tab emits that KPI. | “Digital twin” language. |
| **Upande WaSHMIS / addanode (Kenya)** | Pulse-read the meter that is already there. Private LoRaWAN where 4G dies. Buffer through KPLC so the after-fill record never has a hole. Job-card + GIS + CIS. Unprotected master meters get stolen — chamber, not a post. | Replacing every customer meter before the DMA has an inlet. |
| **Ashdown Park / VEI (Harare IWS)** | **Flow detects better than pressure** on intermittent DMAs. Utility supply irregularity is harder than customer demand. Bandwidth of expected values + a persistence window before alarm (Vitens DBM). Nairobi/Harare already prefer flow sensors. | Pressure-only grids as the first install. |
| **Syrinix** | High-resolution pressure only for the **open-window** transient. | Acoustics. They die when the pipe is empty. |
| **AVK VIDI / valve sensors** | Inlet **valve position**. Distinguishes scheduled-closed from failed-open from “we thought it opened.” | Household-tank IoT in year 1. |
| **Mexico City IWS nodes** | 5-minute pressure. Skip extra samples when P ≈ 0. | Continuous water-quality flush on a dry tap. |

## How we are better (if we stay in this lane)

The incumbents are better at always-on networks, event desks, and billing.
We are better only if we do the thing they skip:

1. **Each rationing window is a short MNF test.** Zarqa proved leftover
   flow after tank saturation *is* leakage. They needed 63 hours of
   continuous supply. We run the same test inside the 4-hour window,
   every window. Nobody ships that as a daily DMA product.
2. **Detect saturation from the hydrograph, not 75 minutes.** High
   plateau (tanks filling) → drop → lower plateau (leftover = leak).
   That change-point is the deployable hook. A clock is a lab convenience.
3. **Inlet-first SKU.** Ablation: hook works at 0.40 L/s; pressure-only
   misses. Ashdown Park and ThingsLog/addanode say the same in the field:
   inflow is the leak signal; pressure shrinks the dig. A 15-sensor
   pressure grid without a trusted inlet meter is the wrong BOM.
4. **Honest floor.** We say 0.40 L/s on this schematic DMA, 1% of inflow
   is invisible, GNN lost. That is more useful to a judge and a WSP
   than “75% accuracy.”
5. **IWS-aware duty cycle.** Sleep off-window. Burst on valve-open.
   Dense from fill until the change-point, then hold 1-minute samples
   on the after-fill plateau (the one number that is the leak).
   Always-on 1 Hz is a battery and a LoRaWAN suicide.
6. **PBC output, not a confidence score.** m³/day reduced, before/after
   hydrograph, hops to dig. That is how WASREB pays.
7. **Do not play BattLeDIM.** Decline TaKaDu/Syrinix on continuous DMAs
   except as a negative control.

Year-1 we are worse at: event desks, CIS/billing, acoustic pinpoint,
PRV control, daily twin calibration. Pair those. Do not rebuild them.

## The IoT stack (what the hook actually needs)

Three layers. Only layer 1 is required to *detect*. Layer 2 localises.
Layer 3 is someone else’s product.

### Layer 1 — detection (mandatory, one chamber)

| Channel | Why | Hardware class |
| --- | --- | --- |
| **Inlet flow** | After-fill residual *is* the leak. | Pulse / Modbus from the existing bulk meter. If none: compound or electromagnetic, sized so **Qmin ≤ 0.2 L/s** (0.72 m³/h). A DN100 turbine (Zarqa’s Sensus WP-Dynamic Qmin 0.80 m³/h ≈ 0.22 L/s) is just adequate for a 0.40 L/s hook; do not go larger. Clamp-on ultrasonic is a check tool, not a permanent inlet (theft, full-pipe assumption, IWS air). |
| **Inlet pressure** | Confirms the window is actually pressurised; feeds FAVAD later. | 0–10 bar gauge, 4–20 mA, same logger. |
| **Valve position** | Scheduled-closed ≠ failed-open ≠ “SCADA said open.” Without this the hydrograph is uninterpretable. | Reed / limit switch on the inlet valve, or AVK-class positioner. |

One logger, chamber-mounted, IP68, magnetic antenna, **≥7 days local
buffer** (after-fill must survive a KPLC / Safaricom outage). Commercial
class: ThingsLog NRW set, i2O DMA logger, HWM MultiLog, Upande pulse
node. Not a $60 post on a stick.

### Layer 2 — localisation (only after detection works)

4–8 pressure loggers at greedy-separable nodes (dead-ends + loop
splits). Our budget-10 curve is a simulation result, not a year-1
install. Ashdown Park and Zarqa both ran **four** pressure points.

No acoustics in the supply-off hours. Optional Syrinix-class burst
on the open-window transient only.

### Layer 3 — do not build

i2O/PRV control, TaKaDu event desk, SmartTerra/Upande CIS+job-card,
Utilis satellite screen, customer smart meters (Eldowas/Safaricom is a
multi-year programme). Integrate by API. DMA bulk metering delivers a
loss map in weeks; household AMR takes years ([addanode](https://addanode.com/ke/non-revenue-water/)).

## IWS duty cycle (the part that is ours)

Off-the-shelf DMA loggers default to “15 minutes forever.” That wastes
battery off-window and is too coarse at the saturation knee.

| Phase | How we know | Sample | Uplink |
| --- | --- | --- | --- |
| Off-window | Valve closed, P ≈ 0, Q ≈ 0 | 15 min heartbeat | Daily or on exception |
| Open transient | Valve opens or ΔP ≳ 0.5 m | 1 Hz × 30–60 s | Immediate (intrusion / burst) |
| Fill | Valve open, Q high plateau | 1 min flow + pressure | 15 min batch |
| Saturation | Change-point: Q drops and stays | — | Flag `t_sat` |
| After-fill plateau | Valve still open, post `t_sat` | **1 min for ≥30 min** | Immediate if residual > threshold |
| Rest of window | After the 30 min hold | 5 min | 15 min batch |

A missing after-fill window is a **sensor-failure event**, not a
“no leak.” Steal that from ALF.

Kenya connectivity: Safaricom NB-IoT at the inlet if the chamber has
signal (Eldowas / Kisumu / Embu already use it). Private LoRaWAN
gateway at the DMA for the pressure nodes and for chambers with no
cellular (Upande, addanode, CityTaps/Kerlink already do this).
Store-and-forward either way. `sim/observe.py` dropouts are this
model, not lost days.

## Cost honesty

| SKU | What it is | Est. USD | Label |
| --- | --- | --- | --- |
| Paper $60 node | DIY pressure logger, LoRaWAN + solar | 52–76 | estimated; not utility-grade |
| ThingsLog-class pressure node | Commercial LoRa/NB-IoT | ~520–660 list | vendor list (Oz Robotics) |
| Ayyeka Wavelet | 4G/LoRa industrial logger | ~1,800–2,500 | vendor list (DKK) |
| **Detection-only DMA** | 1× inlet flow + P + valve logger, chamber | **800–1,500** | estimated; **year-1 SKU** |
| Detection + 5 pressure | above + 5 DIY nodes | ~1,200–1,900 | estimated |
| Detection + 5 commercial pressure | above + 5 ThingsLog-class | ~3,500–5,000 | estimated |

The white paper’s “under US$1,000 of sensor hardware” holds for
**detection-only** if the bulk meter already has a pulse output, or
for detection + DIY pressure. It does not hold for a 10-node
commercial pressure grid. Say that.

## Software that now matches

1. Change-point `t_sat` from inlet Q — `baseline/saturation.py`. 75 minutes
   is simulation demand + continuous-supply fallback only.
2. Persist-N samples before a leak event (Vitens DBM, default 4 steps).
3. Event types: `leak` / `no_leak` / `valve_did_not_open` / `sensor_failure`
   / `still_filling`. Missing after-fill is not a clean DMA.
4. Manager KPI: leftover m³/day (after-fill residual × open hours / day).
5. `sim/observe.py` is the logger: valve position + IWS duty cycle
   (sleep off-window, dense fill and after-`t_sat` hold, 15-minute rest
   of window, burst on ΔP). Radio 3% only on uplinks; leftover hold
   capped at 1%. Continuous-supply runs do not sleep.

Firmware stays out of this repo. The field stack is “buy a DMA logger,
pulse the meter, sense the valve, run our after-fill logic.”
