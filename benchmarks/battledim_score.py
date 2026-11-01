"""Official BattLeDIM 2019 economic score (Vrachimis et al. 2022, Table 3).

This is a *continuous-supply* negative control. It is not intermittent-
supply evidence and must not be blended with the IWS leftover-flow table.

Table 3 (competition):
    xmax = 300 m   (crew search radius)
    cw   = €0.80 / m³
    cr   = €500 / detection (max crew cost)
Perfect score published ≈ €523,124. Winners ~€261–265k at TPR 56–65%.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Official Table 3 — do not invent other prices.
XMAX_M = 300.0
CW_EUR_PER_M3 = 0.80
CR_EUR = 500.0
STEP_S = 5 * 60
PERFECT_SCORE_EUR = 523124.0


@dataclass
class LeakEvent:
    link: str
    start: datetime
    end: datetime
    q_m3h: pd.Series  # indexed by timestamp, m³/h


@dataclass
class Detection:
    time: datetime
    link: str


@dataclass
class ScoreCard:
    economic_eur: float
    n_leaks: int
    n_detections: int
    true_positives: int
    false_positives: int
    repeats_ignored: int
    true_positive_rate: float
    water_saved_m3: float
    crew_cost_eur: float
    xmax_m: float = XMAX_M
    cw: float = CW_EUR_PER_M3
    cr: float = CR_EUR
    perfect_eur: float = PERFECT_SCORE_EUR
    rows: list[dict] = field(default_factory=list)
    label: str = (
        "official BattLeDIM 2019 economic score — continuous L-Town, "
        "not intermittent-supply evidence"
    )


def read_battledim_csv(path: Path) -> pd.DataFrame:
    """Zenodo CSVs: semicolon sep, comma decimal, Timestamp index."""
    df = pd.read_csv(path, sep=";", decimal=",")
    ts_col = df.columns[0]
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df.set_index(ts_col)
    df.index.name = "timestamp"
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def leak_events_from_timeseries(leak_df: pd.DataFrame, *, eps_m3h: float = 0.05) -> list[LeakEvent]:
    """One event per leak column: first to last step above ``eps_m3h``."""
    events = []
    for col in leak_df.columns:
        q = leak_df[col].astype(float)
        on = q > eps_m3h
        if not bool(on.any()):
            continue
        idx = q.index[on]
        events.append(LeakEvent(link=str(col), start=idx[0].to_pydatetime(), end=idx[-1].to_pydatetime(), q_m3h=q))
    events.sort(key=lambda e: e.start)
    return events


def detect_mnf_and_bursts(
    flows_m3h: pd.DataFrame,
    *,
    mnf_excess_m3h: float = 2.0,
    persist_days: int = 2,
    burst_excess_m3h: float = 8.0,
    burst_persist_steps: int = 72,
    rolling_days: int = 7,
) -> list[datetime]:
    """Continuous-supply detector. Not the IWS leftover hook.

    Daily minimum-night-flow (02:00–04:00) vs a rolling median, plus a
    6-hour persist on the 7-day rolling residual of total DMA inflow.
    """
    q = flows_m3h.sum(axis=1).astype(float)
    times: list[datetime] = []

    night = q.between_time("02:00", "04:00")
    if len(night):
        mnf = night.resample("D").mean()
        base = mnf.rolling(rolling_days, min_periods=max(3, rolling_days // 2)).median()
        resid = mnf - base
        run = 0
        armed = True
        for t, r in resid.items():
            if pd.isna(r):
                run = 0
                continue
            if r > mnf_excess_m3h:
                run += 1
                if armed and run >= persist_days:
                    times.append(pd.Timestamp(t).to_pydatetime())
                    armed = False
                    run = 0
            else:
                run = 0
                if r < mnf_excess_m3h * 0.4:
                    armed = True

    win = rolling_days * 24 * 12
    baseline = q.rolling(win, min_periods=24 * 12).median()
    burst = q - baseline
    run = 0
    armed = True
    last_fire = None
    for t, r in burst.items():
        if pd.isna(r):
            run = 0
            continue
        if r > burst_excess_m3h:
            run += 1
            if armed and run >= burst_persist_steps:
                ts = pd.Timestamp(t).to_pydatetime()
                if last_fire is None or (ts - last_fire).total_seconds() > 3 * 86400:
                    times.append(ts)
                    last_fire = ts
                armed = False
                run = 0
        else:
            run = 0
            if r < burst_excess_m3h * 0.3:
                armed = True

    times = sorted(set(times))
    return times


def localise_link(
    pressures_m: pd.DataFrame,
    t: datetime,
    incident_links: dict[str, list[str]],
    *,
    lookback_steps: int = 12 * 24 * 7,
) -> str:
    """Loudest pressure drop vs the previous week → an incident pipe."""
    idx = pressures_m.index
    ts = pd.Timestamp(t)
    # nearest index
    pos = int(idx.searchsorted(ts))
    pos = min(max(pos, 1), len(idx) - 1)
    now = pressures_m.iloc[pos]
    prev = pressures_m.iloc[max(0, pos - lookback_steps) : pos]
    if prev.empty:
        sensor = str(now.idxmin())
    else:
        drop = prev.median() - now
        sensor = str(drop.idxmax())
    links = incident_links.get(sensor, [])
    if not links:
        # fallback: any known link
        for v in incident_links.values():
            if v:
                return v[0]
        return ""
    return sorted(links)[0]


def volume_saved_m3(event: LeakEvent, detected_at: datetime) -> float:
    q = event.q_m3h
    t0 = pd.Timestamp(detected_at)
    t1 = pd.Timestamp(event.end)
    if t0 > t1:
        return 0.0
    sl = q[(q.index >= t0) & (q.index <= t1)]
    if sl.empty:
        return 0.0
    return float(np.nansum(sl.to_numpy(dtype=float)) * (STEP_S / 3600.0))


def official_score(
    leaks: list[LeakEvent],
    detections: list[Detection],
    link_distance_m,
) -> ScoreCard:
    """Apply Table 3 rules. Detections in chronological order."""
    assigned: set[int] = set()
    economic = 0.0
    water = 0.0
    crew = 0.0
    tp = 0
    fp = 0
    repeats = 0
    rows = []
    ordered = sorted(detections, key=lambda d: d.time)
    for det in ordered:
        if det.time.year != 2019:
            continue
        best_i = None
        best_x = float("inf")
        for i, ev in enumerate(leaks):
            if not (ev.start <= det.time <= ev.end):
                continue
            x = float(link_distance_m(det.link, ev.link))
            if x < best_x:
                best_x = x
                best_i = i
        if best_i is None or best_x >= XMAX_M:
            economic -= CR_EUR
            crew += CR_EUR
            fp += 1
            rows.append(
                {
                    "t": det.time.isoformat(sep=" "),
                    "pred": det.link,
                    "true": None if best_i is None else leaks[best_i].link,
                    "x_m": None if best_i is None else best_x,
                    "result": "FP",
                }
            )
            continue
        if best_i in assigned:
            repeats += 1
            rows.append(
                {
                    "t": det.time.isoformat(sep=" "),
                    "pred": det.link,
                    "true": leaks[best_i].link,
                    "x_m": best_x,
                    "result": "repeat",
                }
            )
            continue
        vol = volume_saved_m3(leaks[best_i], det.time)
        crew_i = CR_EUR * (best_x / XMAX_M)
        economic += vol * CW_EUR_PER_M3 - crew_i
        water += vol
        crew += crew_i
        assigned.add(best_i)
        tp += 1
        rows.append(
            {
                "t": det.time.isoformat(sep=" "),
                "pred": det.link,
                "true": leaks[best_i].link,
                "x_m": best_x,
                "result": "TP",
                "saved_m3": vol,
            }
        )
    n = len(leaks)
    return ScoreCard(
        economic_eur=float(economic),
        n_leaks=n,
        n_detections=len(ordered),
        true_positives=tp,
        false_positives=fp,
        repeats_ignored=repeats,
        true_positive_rate=tp / max(n, 1),
        water_saved_m3=float(water),
        crew_cost_eur=float(crew),
        rows=rows,
    )
