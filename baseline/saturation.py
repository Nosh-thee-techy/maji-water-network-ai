"""Tank-saturation change-point and IWS event types.

The 75-minute fill is a *simulation* convenience. In the field the utility
does not know that number. After-fill leftover inlet flow is still the
leak — but only after the hydrograph itself shows tanks have stopped
drawing (Al-Washali / Zarqa saturation test, per rationing window).

Event types (one per supply window, then aggregated):

- ``leak`` — leftover persisted above the detect threshold
- ``no_leak`` — leftover persisted below the threshold
- ``valve_did_not_open`` — scheduled window, no fill surge
- ``sensor_failure`` — after-fill (or the whole window) is missing
- ``still_filling`` — window stayed on the high plateau (no knee)

A missing after-fill record is a sensor-failure event, not a clean DMA.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sim.demand import DEFAULT_FILL_MINUTES
from sim.schedule import SUPPLY_WINDOWS_H, expand_windows


# First 20 min of a window must show a fill surge, or the valve never opened.
OPEN_CHECK_MINUTES = 20
# Do not declare saturation in the first 20 min (valve transient / air).
MIN_FILL_MINUTES = 20
# Need ≥30 min of after-fill to trust the leftover (IoT duty-cycle hold).
MIN_AFTER_MINUTES = 30
# Drop from fill plateau to leftover plateau. ~5× flow-noise sigma (0.15 L/s).
MIN_DROP_LPS = 0.80
# Scheduled-open but Q below this in the first 20 min → valve did not open.
VALVE_CLOSED_LPS = 0.30
VALVE_CLOSED_PRESSURE_M = 1.0
# Fraction of finite samples required before we trust a window.
MIN_FINITE_FRAC = 0.40
# DBM-style persistence: leftover must stay above threshold this many steps.
PERSIST_STEPS = 4
# Clock fallback only — never the field default.
CLOCK_FILL_MINUTES = DEFAULT_FILL_MINUTES


EVENT_LEAK = "leak"
EVENT_NO_LEAK = "no_leak"
EVENT_VALVE = "valve_did_not_open"
EVENT_SENSOR = "sensor_failure"
EVENT_FILLING = "still_filling"


@dataclass
class WindowSat:
    open_s: int
    close_s: int
    t_sat_s: float | None
    fill_mean_lps: float
    after_mean_lps: float
    leftover_lps: float
    n_after_finite: int
    n_after_total: int
    persisted: bool
    event: str
    used_change_point: bool


@dataclass
class SaturationReport:
    windows: list[WindowSat] = field(default_factory=list)
    fill_mask: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))
    after_mask: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))
    leftover_lps: float = 0.0
    leftover_m3_per_day: float = 0.0
    event: str = EVENT_NO_LEAK
    used_change_point: bool = False
    used_clock_fallback: bool = False


def _nanmean(values: np.ndarray) -> float:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float("nan")
    return float(v.mean())


def leftover_m3_per_day(
    leftover_lps: float,
    duration_h: float,
    windows: list[tuple[int, int]],
) -> float:
    """IWS leak volume: leftover rate × open seconds, scaled to one day.

    Off-window the DMA is slack, so the leak does not run 24 h. WASREB
    PBC language is m³/day reduced — this is that unit on a rationed DMA.
    """
    if leftover_lps <= 0 or duration_h <= 0:
        return 0.0
    open_s = float(sum(c - o for o, c in windows))
    days = duration_h / 24.0
    if days <= 0 or open_s <= 0:
        return 0.0
    return leftover_lps * (open_s / days) / 1000.0


def leftover_persists(
    series: np.ndarray,
    threshold: float,
    persist_steps: int = PERSIST_STEPS,
) -> bool:
    """True if leftover stays ≥ threshold for ``persist_steps`` samples.

    Short after-fill: fall back to median over at least ``persist_steps``
    finite samples (Vitens DBM persistence, then a small-n median).
    """
    run = 0
    max_run = 0
    for v in series:
        if np.isfinite(v) and v >= threshold:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    if max_run >= persist_steps:
        return True
    ok = np.asarray(series, dtype=float)
    ok = ok[np.isfinite(ok)]
    return ok.size >= persist_steps and float(np.median(ok)) >= threshold


def change_point_index(
    q: np.ndarray,
    *,
    min_fill_steps: int,
    min_after_steps: int,
    min_drop_lps: float = MIN_DROP_LPS,
) -> int | None:
    """Two-means knee: argmax mean(q[:k]) − mean(q[k:]) with a minimum drop.

    ``q`` is one supply window, already sliced. Returns the first after-fill
    index inside ``q``, or None if the plateau never drops.
    """
    q = np.asarray(q, dtype=float)
    n = len(q)
    if n < min_fill_steps + min_after_steps:
        return None
    best_k: int | None = None
    best_drop = min_drop_lps
    for k in range(min_fill_steps, n - min_after_steps + 1):
        a = q[:k]
        b = q[k:]
        a = a[np.isfinite(a)]
        b = b[np.isfinite(b)]
        if a.size < max(3, min_fill_steps // 2):
            continue
        if b.size < max(3, min_after_steps // 2):
            continue
        drop = float(a.mean() - b.mean())
        if drop > best_drop:
            best_drop = drop
            best_k = k
    return best_k


def _clock_masks(times: np.ndarray, windows: list[tuple[int, int]]) -> tuple[np.ndarray, np.ndarray]:
    fill = np.zeros(len(times), dtype=bool)
    after = np.zeros(len(times), dtype=bool)
    fill_s = CLOCK_FILL_MINUTES * 60.0
    for open_s, close_s in windows:
        for i, t in enumerate(times):
            if open_s <= t < close_s:
                if (t - open_s) < fill_s:
                    fill[i] = True
                else:
                    after[i] = True
    return fill, after


def detect_saturation(
    times_s: np.ndarray,
    inlet_lps: np.ndarray,
    duration_h: float,
    *,
    pressure_m: np.ndarray | None = None,
    valve_open: np.ndarray | None = None,
    inlet_noleak_lps: np.ndarray | None = None,
    detect_threshold_lps: float = 0.35,
    persist_steps: int = PERSIST_STEPS,
    timestep_s: float = 300.0,
) -> SaturationReport:
    """Find ``t_sat`` in each rationing window and classify the event.

    Change-point runs on the *observed* inlet hydrograph. Leftover is the
    residual against the no-leak model when that series is given, else the
    absolute after-fill flow (Zarqa: customer draw is then zero).
    """
    times = np.asarray(times_s, dtype=float)
    q = np.asarray(inlet_lps, dtype=float)
    p = None if pressure_m is None else np.asarray(pressure_m, dtype=float)
    vlv = None if valve_open is None else np.asarray(valve_open, dtype=float)
    q0 = None if inlet_noleak_lps is None else np.asarray(inlet_noleak_lps, dtype=float)

    windows = expand_windows(duration_h, SUPPLY_WINDOWS_H)
    fill_mask = np.zeros(len(times), dtype=bool)
    after_mask = np.zeros(len(times), dtype=bool)
    clock_fill, clock_after = _clock_masks(times, windows)

    min_fill_steps = max(3, int(round(MIN_FILL_MINUTES * 60 / timestep_s)))
    min_after_steps = max(3, int(round(MIN_AFTER_MINUTES * 60 / timestep_s)))
    open_check_steps = max(2, int(round(OPEN_CHECK_MINUTES * 60 / timestep_s)))

    rows: list[WindowSat] = []
    any_cp = False

    for open_s, close_s in windows:
        idx = np.where((times >= open_s) & (times < close_s))[0]
        if idx.size == 0:
            continue
        q_w = q[idx]
        finite_frac = float(np.isfinite(q_w).mean())
        head = q_w[: min(open_check_steps, q_w.size)]
        head_ok = head[np.isfinite(head)]

        p_med = float("nan")
        if p is not None:
            p_w = p[idx]
            p_ok = p_w[np.isfinite(p_w)]
            if p_ok.size:
                p_med = float(np.median(p_ok))

        valve_closed = False
        valve_known = False
        if vlv is not None:
            known = vlv[idx]
            known = known[np.isfinite(known)]
            if known.size:
                # All finite in-window readings closed → valve did not open.
                # All-NaN (duty-cycle hole) is unknown — fall through to Q/P.
                valve_closed = not bool(np.any(known > 0.5))
                valve_known = True
        if (not valve_known) and head_ok.size and float(np.median(head_ok)) < VALVE_CLOSED_LPS:
            if not np.isfinite(p_med) or p_med < VALVE_CLOSED_PRESSURE_M:
                valve_closed = True

        if finite_frac < MIN_FINITE_FRAC and not valve_closed:
            rows.append(
                WindowSat(
                    open_s=open_s,
                    close_s=close_s,
                    t_sat_s=None,
                    fill_mean_lps=float("nan"),
                    after_mean_lps=float("nan"),
                    leftover_lps=float("nan"),
                    n_after_finite=0,
                    n_after_total=int(idx.size),
                    persisted=False,
                    event=EVENT_SENSOR,
                    used_change_point=False,
                )
            )
            continue

        if valve_closed:
            rows.append(
                WindowSat(
                    open_s=open_s,
                    close_s=close_s,
                    t_sat_s=None,
                    fill_mean_lps=_nanmean(q_w),
                    after_mean_lps=float("nan"),
                    leftover_lps=0.0,
                    n_after_finite=0,
                    n_after_total=int(idx.size),
                    persisted=False,
                    event=EVENT_VALVE,
                    used_change_point=False,
                )
            )
            continue

        k = change_point_index(
            q_w,
            min_fill_steps=min_fill_steps,
            min_after_steps=min_after_steps,
        )
        if k is None:
            rows.append(
                WindowSat(
                    open_s=open_s,
                    close_s=close_s,
                    t_sat_s=None,
                    fill_mean_lps=_nanmean(q_w),
                    after_mean_lps=float("nan"),
                    leftover_lps=float("nan"),
                    n_after_finite=0,
                    n_after_total=int(idx.size),
                    persisted=False,
                    event=EVENT_FILLING,
                    used_change_point=False,
                )
            )
            continue

        after_idx = idx[k:]
        fill_idx = idx[:k]
        after_q = q[after_idx]
        if q0 is not None:
            leftover_series = after_q - q0[after_idx]
        else:
            leftover_series = after_q
        leftover = max(0.0, _nanmean(leftover_series))
        if not np.isfinite(leftover):
            leftover = float("nan")
        n_fin = int(np.isfinite(leftover_series).sum())
        if n_fin < max(3, persist_steps) or n_fin / max(len(after_idx), 1) < MIN_FINITE_FRAC:
            event = EVENT_SENSOR
            persisted = False
        else:
            persisted = leftover_persists(leftover_series, detect_threshold_lps, persist_steps)
            event = EVENT_LEAK if persisted else EVENT_NO_LEAK
            if not persisted and np.isfinite(leftover) and leftover >= detect_threshold_lps:
                # Mean is high but it did not persist — do not hide a leak
                # behind one dropout; call it a leak if the median is high.
                med = leftover_series[np.isfinite(leftover_series)]
                if med.size and float(np.median(med)) >= detect_threshold_lps:
                    event = EVENT_LEAK
                    persisted = True

        fill_mask[fill_idx] = True
        after_mask[after_idx] = True
        any_cp = True
        rows.append(
            WindowSat(
                open_s=open_s,
                close_s=close_s,
                t_sat_s=float(times[idx[k]]),
                fill_mean_lps=_nanmean(q[fill_idx]),
                after_mean_lps=_nanmean(after_q),
                leftover_lps=0.0 if not np.isfinite(leftover) else leftover,
                n_after_finite=n_fin,
                n_after_total=int(after_idx.size),
                persisted=persisted,
                event=event,
                used_change_point=True,
            )
        )

    kinds = [r.event for r in rows]
    if EVENT_LEAK in kinds:
        primary = EVENT_LEAK
    elif EVENT_NO_LEAK in kinds:
        primary = EVENT_NO_LEAK
    elif kinds and all(k == EVENT_VALVE for k in kinds):
        primary = EVENT_VALVE
    elif EVENT_SENSOR in kinds and EVENT_NO_LEAK not in kinds and EVENT_LEAK not in kinds:
        primary = EVENT_SENSOR
    elif EVENT_FILLING in kinds and EVENT_LEAK not in kinds and EVENT_NO_LEAK not in kinds:
        primary = EVENT_FILLING
    elif EVENT_VALVE in kinds:
        primary = EVENT_VALVE
    else:
        primary = EVENT_NO_LEAK

    used_clock = False
    off = np.ones(len(times), dtype=bool)
    for open_s, close_s in windows:
        off[(times >= open_s) & (times < close_s)] = False
    q_off = q[off]
    q_off = q_off[np.isfinite(q_off)]
    looks_continuous = q_off.size > 5 and float(np.median(q_off)) > VALVE_CLOSED_LPS

    if not after_mask.any() and looks_continuous:
        # Always-on DMA: no knee, but leftover is residual vs the no-leak model.
        # Do not do this on IWS still-filling — that is the clock bug we are
        # retiring (75 min of fill leftover is still customer draw).
        fill_mask = clock_fill
        after_mask = clock_after
        used_clock = bool(after_mask.any())
        if used_clock:
            series = q[after_mask] - q0[after_mask] if q0 is not None else q[after_mask]
            leftover_clock = max(0.0, _nanmean(series))
            persisted = leftover_persists(series, detect_threshold_lps, persist_steps)
            primary = EVENT_LEAK if persisted else EVENT_NO_LEAK

    leak_rows = [r for r in rows if r.event == EVENT_LEAK and np.isfinite(r.leftover_lps)]
    clean_rows = [r for r in rows if r.event == EVENT_NO_LEAK and np.isfinite(r.leftover_lps)]
    if leak_rows:
        leftover = float(np.mean([r.leftover_lps for r in leak_rows]))
    elif clean_rows:
        leftover = float(np.mean([r.leftover_lps for r in clean_rows]))
    elif after_mask.any():
        if q0 is not None:
            leftover = max(0.0, _nanmean(q[after_mask] - q0[after_mask]))
        else:
            leftover = max(0.0, _nanmean(q[after_mask]))
        if not np.isfinite(leftover):
            leftover = 0.0
    else:
        leftover = 0.0

    return SaturationReport(
        windows=rows,
        fill_mask=fill_mask,
        after_mask=after_mask,
        leftover_lps=float(leftover) if np.isfinite(leftover) else 0.0,
        leftover_m3_per_day=leftover_m3_per_day(
            float(leftover) if np.isfinite(leftover) else 0.0,
            duration_h,
            windows,
        ),
        event=primary,
        used_change_point=any_cp,
        used_clock_fallback=used_clock and not any_cp,
    )
