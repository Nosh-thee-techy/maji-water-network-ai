"""Official BattLeDIM Table 3 scorer — toy events, no 550 MB download."""

from __future__ import annotations

from datetime import datetime
from io import StringIO

import pandas as pd

from benchmarks.battledim_score import (
    CR_EUR,
    CW_EUR_PER_M3,
    Detection,
    LeakEvent,
    leak_events_from_timeseries,
    official_score,
    read_battledim_csv,
    volume_saved_m3,
)


def _q(start: str, hours: int, rate: float) -> pd.Series:
    idx = pd.date_range(start, periods=hours * 12, freq="5min")
    return pd.Series(rate, index=idx)


def test_read_european_scada_csv():
    raw = StringIO(
        "Timestamp;pA;pB\n"
        "2019-01-01 00:00:00;1,5;0\n"
        "2019-01-01 00:05:00;1,6;0,2\n"
    )
    # read_battledim_csv wants a path; use a tempfile via pandas-equivalent parse
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "f.csv"
        p.write_text(raw.getvalue(), encoding="utf-8")
        df = read_battledim_csv(p)
    assert list(df.columns) == ["pA", "pB"]
    assert abs(df.iloc[0]["pA"] - 1.5) < 1e-9
    assert abs(df.iloc[1]["pB"] - 0.2) < 1e-9


def test_leak_events_span_nonzero_window():
    idx = pd.date_range("2019-03-01", periods=20, freq="5min")
    q = pd.Series([0, 0, 3, 3, 3, 0] + [0] * 14, index=idx)
    ev = leak_events_from_timeseries(pd.DataFrame({"p10": q}))
    assert len(ev) == 1
    assert ev[0].link == "p10"
    assert ev[0].start == idx[2].to_pydatetime()
    assert ev[0].end == idx[4].to_pydatetime()


def test_perfect_on_time_exact_link_gets_water_credit():
    q = _q("2019-06-01", 24, 10.0)  # 10 m³/h for 24 h
    ev = LeakEvent("p1", q.index[0].to_pydatetime(), q.index[-1].to_pydatetime(), q)
    det = Detection(q.index[0].to_pydatetime(), "p1")
    card = official_score([ev], [det], lambda a, b: 0.0)
    assert card.true_positives == 1
    assert card.false_positives == 0
    vol = volume_saved_m3(ev, det.time)
    assert abs(card.water_saved_m3 - vol) < 1e-6
    assert abs(card.economic_eur - vol * CW_EUR_PER_M3) < 1e-6


def test_false_positive_costs_cr():
    q = _q("2019-06-01", 4, 5.0)
    ev = LeakEvent("p1", q.index[0].to_pydatetime(), q.index[-1].to_pydatetime(), q)
    # Detection outside the leak window
    det = Detection(datetime(2019, 8, 1, 12, 0), "p9")
    card = official_score([ev], [det], lambda a, b: 0.0)
    assert card.false_positives == 1
    assert card.true_positives == 0
    assert abs(card.economic_eur + CR_EUR) < 1e-9


def test_far_localisation_is_a_false_positive():
    q = _q("2019-06-01", 4, 5.0)
    ev = LeakEvent("p1", q.index[0].to_pydatetime(), q.index[-1].to_pydatetime(), q)
    det = Detection(q.index[10].to_pydatetime(), "p99")
    card = official_score([ev], [det], lambda a, b: 500.0)  # > 300 m
    assert card.false_positives == 1
    assert card.true_positives == 0


def test_repeat_detection_is_ignored():
    q = _q("2019-06-01", 24, 4.0)
    ev = LeakEvent("p1", q.index[0].to_pydatetime(), q.index[-1].to_pydatetime(), q)
    d1 = Detection(q.index[0].to_pydatetime(), "p1")
    d2 = Detection(q.index[100].to_pydatetime(), "p1")
    card = official_score([ev], [d1, d2], lambda a, b: 0.0)
    assert card.true_positives == 1
    assert card.repeats_ignored == 1


def test_pre_2019_detection_ignored():
    q = _q("2019-01-02", 4, 5.0)
    ev = LeakEvent("p1", q.index[0].to_pydatetime(), q.index[-1].to_pydatetime(), q)
    det = Detection(datetime(2018, 12, 31, 23, 0), "p1")
    card = official_score([ev], [det], lambda a, b: 0.0)
    assert card.n_detections == 1
    assert card.true_positives == 0
    assert card.false_positives == 0
