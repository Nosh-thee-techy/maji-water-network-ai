# How this use case actually works, and who already occupies it

M.A.J.I. is not a general leak-detection app. It is an attempt to do
**minimum-night-flow logic on a network that has no night**. That is
the use case. Everything else (GNNs, 15 sensors, BattLeDIM) is
secondary.

## The operational fact

On a continuously supplied DMA, leakage is estimated from **minimum
night flow** (typically 02:00–04:00): customers are asleep, inflow ≈
leakage + a small legitimate night use (Farley & Trow; Lambert;
Liemberger).

On intermittent supply that identity is false. Household tanks keep
drawing until they are full, even at 03:00. Al-Washali et al. (2019)
showed this on Zarqa, Jordan: one-day MNF cannot be used; the DMA had
to be held in continuous supply for **~63 hours** until tanks
saturated and the inflow curve started to repeat. Only then was the
leftover flow leakage. Doing that regularly is operationally
unrealistic on a rationed network
([Water 11(1):48](https://www.mdpi.com/2073-4441/11/1/48);
[Resour. Conserv. Recycl. 2019](https://doi.org/10.1016/j.resconrec.2019.104515)).

Kumpel & Nelson (2014) add the health side: when pressure falls,
indicator bacteria appear even with chlorine present. Intrusion is a
low-pressure / empty-pipe problem, not a separate water-quality
product.

**M.A.J.I.’s after-fill inlet residual is the Zarqa idea applied
inside each rationing window** instead of converting the DMA to
24/7 for three days. After the tanks stop drawing, leftover inlet
flow is the leak. Our ablation says that is real at ~0.40 L/s and
invisible at 1% of inflow.

## What existing platforms do (and where they break on IWS)

| Platform | What it actually does | Assumes | On intermittent supply |
| --- | --- | --- | --- |
| **TaKaDu** ([takadu.com](https://www.takadu.com/solution/)) | Cloud event management: learn historic DMA flow/pressure, declare an “event”, track repair to close. Integrates SCADA, meters, acoustics. | Continuous DMA, months of history, MNF-like patterns | Historic-pattern ML misfires when the “normal” day is a 4-hour pulse. Night-flow features do not exist. |
| **Syrinix PIPEMINDER + RADAR** | High-resolution pressure, transients, burst localisation, network calming. Pairs with TaKaDu. | Always-on mains, 128–256 Hz bursts | Useful for the *open-window* transient when the inlet valve slams open (fill surge). Useless off-window. Complementary, not a competitor. |
| **i2O / Mueller Advanced Pressure Management** ([i2owater](https://en.i2owater.com/solutions/advanced-pressure-management/)) | Control PRVs/pumps; schedule pressure including **rationing**; eThekwini (Durban) cut bursts ~67%. Selangor used it to cut and restore supply on a clock. | There is a PRV or pump to command | They *create* the schedule M.A.J.I. treats as given. Partner layer: they open/close; we read the leftover flow. |
| **Gutermann / Aquarius Spectrum** | Permanent acoustic loggers. | Water in the pipe, some pressure | Acoustics die when the pipe is empty. Can only run inside the supply window. |
| **Aganova Nautilus** | In-pipe sphere, <1 m location, large diameters. | Flow to carry the device | Hard on IWS: short windows, low/no flow, air. Not a DMA daily tool. |
| **Utilis** (satellite) | Soil-moisture / SAR screen for wet ground. | Leak has been wet long enough | Works *regardless of pressure*. Complements IWS (leaks that run during the window still wet the ground). Coarse; not pipe-level. |
| **Miya, WaterWorX, SEURECA** | People + DMA build + PBC. Nairobi WaterWorX uses DMAs (e.g. Mirema). NAWASCO (Nanyuki) tendered an NRW PBC in 2025. WASREB 2022 guidelines pay per m³/day leakage reduction. | Utility will isolate a DMA and accept a contractor | This is the *buyer*, not the algorithm. M.A.J.I. should speak PBC language, not “AI platform”. |
| **PUB Singapore ALF** (Eng. Proc. 2024) | Daily-recalibrated physics + data-driven models on 90+ sensors, 1000 km. Field confirmation ~220 m from the alert. | Continuous, dense SCADA | Shows the bar for a real twin: **daily calibration**. We do not have that. |
| **BattLeDIM 2020 winners** (Tongji / Under Pressure) | Hybrid: model-based EPANET search where sensors are sparse; graph interpolation where they are dense. Winning TPR ~56–65%, not 100%. | Continuous L-Town | Our GNN loss on an 18-node *known* model is consistent with this: when the hydraulics are known, optimisation beats a small GNN. |
| **Paryai GRID** (Bengaluru blog) | Claims IWS-aware residuals + SCADA/billing; marketed 75% leak / 80% meter accuracy. | Utility SCADA | Same tank-fill observation we use. Treat the percentages as marketing until a methods paper exists. They have the integration we lack. |
| **MAYIEDGE** (IJISRT 2025) | Offline-first edge + EPANET/WNTR *architecture* for IWS. Explicitly has not run a twin or field system. | — | Closer in *setting* than TaKaDu. We are ahead on hydraulics; they are ahead on store-and-forward honesty. |

Bluefield’s DMA vs non-DMA split matters: most of the developing world
never built UK-style DMAs. M.A.J.I. still assumes a metered inlet.
That is a product prerequisite, not a given.

## What to optimize (in order)

1. **Stop fixing tank-fill at 75 minutes.** Utilities do not know that
   number. Detect saturation from the **inlet hydrograph**: high
   plateau (tanks filling) then a drop to a lower plateau (leftover =
   leak). That is Al-Washali’s saturation test, per window. It is the
   single change that makes the hook deployable. A change-point on
   inlet flow beats another GNN.

2. **Sell the inlet meter first, pressure second.** The ablation
   already says detection lives on after-fill flow. A 15-sensor
   pressure grid without a reliable inlet meter is the wrong BOM.
   Dead-end pressure sensors earn their keep only *after* detection,
   for the dig radius.

3. **Speak WASREB / PBC, not “digital twin”.** Kenyan buyers already
   have a payment unit: KES or USD per m³/day leakage reduced, plus a
   lump sum per DMA established. The manager tab should output that
   KPI, not a neural-net confidence.

4. **Recalibrate, even crudely.** ALF and BattLeDIM winners spend
   their intelligence on updating the no-leak model. Our sensitivity
   matrix is frozen. A weekly “no-leak Sunday” or a 2-hour
   post-saturation window used as the new baseline is more valuable
   than ensemble spread.

5. **Do not compete with TaKaDu or Syrinix on always-on networks.**
   BattLeDIM/L-Town is their home game. Our continuous-DMA result is
   only a sanity check. The report should say we *decline* that
   comparison except as a negative control.

6. **Pair, do not replace, pressure management.** i2O already
   schedules intermittent valves. M.A.J.I. should read the same
   inlet. Intrusion risk is “do not slam the valve into an empty
   main” plus the 7 m prior — an i2O control problem as much as a
   sensing problem.

7. **Apparent loss needs the billing file.** Every serious NRW stack
   (TaKaDu, Miya, WASREB) splits real vs commercial loss with meters
   and the customer information system. Pressure will never do that.
   The next product slice is: billed volume in, unmetered residual
   out — with the non-punitive rule kept.

8. **Event lifecycle.** TaKaDu’s actual lock-in is not ML; it is
   open → assign crew → repair → verify the hydrograph fell. Our
   dig list is step one of four.

## One line for the report

> Existing leak platforms assume a pressurised night. Intermittent
> networks do not have one. M.A.J.I. treats each supply window as a
> short MNF test: once household tanks stop drawing, leftover inlet
> flow is leakage. That is established IWS water-loss practice
> (Al-Washali / Zarqa), automated, not a new neural-net.

## Sources (for the reference list)

- Al-Washali et al., 2019. *Water* 11(1):48. MNF under intermittent supply, Zarqa.
- Al-Washali, 2020. *Water Loss Assessment in Distribution Networks* (CRC). Same argument at book length.
- Kumpel & Nelson, 2014. *Environ. Sci. Technol.* Low pressure and contamination.
- Taylor, Slocum & Whittle, 2018. *PLOS ONE*. Scaling leakage/intrusion in IWS.
- Liemberger & Wyatt, 2019. Global NRW.
- WASREB, 2022. *NRW Management Standards* — PBC payment per m³/day.
- Vrachimis et al., 2022. BattLeDIM paper, *J. Water Resour. Plann. Manage.*
- PUB / ALF, 2024. *Eng. Proc.* 69:147. Daily-calibrated twin, Singapore.
- TaKaDu solution brief; Syrinix–TaKaDu note (2020); i2O APM + eThekwini case; Bluefield “To DMA or Not to DMA”.
- WaterWorX Nairobi (World Waternet); NAWASCO NRW PBC prequal 2025.
- MAYIEDGE, IJISRT 2025 (architecture only).
