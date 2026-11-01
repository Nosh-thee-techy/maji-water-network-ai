"""Sunday no-leak update: absorb a meter offset, refuse a leak."""

from __future__ import annotations

import numpy as np

from baseline.recalibrate import recalibrate_from_observations, sunday_update
from baseline.saturation import leftover_m3_per_day
from tests.test_saturation import _hydrograph, _times


def test_sunday_update_refuses_a_leak_sized_leftover():
    times = _times(12.0)
    after = (times >= 5 * 3600 + 75 * 60) & (times < 9 * 3600)
    noleak = np.zeros(len(times))
    obs = _hydrograph(times, leftover=1.4)
    rec = sunday_update(
        inlet_noleak_lps=noleak,
        inlet_obs_lps=obs,
        after_mask=after,
        leftover_lps=1.4,
    )
    assert rec.applied is False
    assert "refusing" in rec.reason
    assert np.allclose(rec.inlet_noleak_lps, noleak)


def test_sunday_update_absorbs_a_clean_offset():
    times = _times(12.0)
    after = (times >= 5 * 3600 + 75 * 60) & (times < 9 * 3600)
    noleak = np.zeros(len(times))
    obs = _hydrograph(times, leftover=0.12)  # below 0.35
    rec = sunday_update(
        inlet_noleak_lps=noleak,
        inlet_obs_lps=obs,
        after_mask=after,
        leftover_lps=0.12,
    )
    assert rec.applied is True
    leftover_after = float(np.nanmean(obs[after] - rec.inlet_noleak_lps[after]))
    assert abs(leftover_after) < 0.05


def test_recalibrate_from_observations_on_clean_hydrograph():
    times = _times(12.0)
    q = _hydrograph(times, leftover=0.0, noise=0.08, seed=2)
    noleak = np.zeros(len(times))
    # Frozen model sits 0.4 L/s low on the after-fill → looks like a leak.
    noleak[(times >= 5 * 3600) & (times < 9 * 3600)] = -0.40
    rec = recalibrate_from_observations(times, q, noleak, 12.0)
    # First pass: leftover vs biased model is large → refuse or clean?
    # detect_saturation leftover uses residual vs noleak, so ~0.4 → leak → refuse.
    assert rec.applied is False
    # Operator Sunday: leftover we *know* is clean (0.10).
    after = (times >= 5 * 3600 + 75 * 60) & (times < 9 * 3600)
    rec2 = sunday_update(
        inlet_noleak_lps=noleak,
        inlet_obs_lps=q,
        after_mask=after,
        leftover_lps=0.10,
    )
    assert rec2.applied is True
    new_left = float(np.nanmean(q[after] - rec2.inlet_noleak_lps[after]))
    assert abs(new_left) < 0.15


def test_leftover_m3_day_still_open_hours():
    assert abs(leftover_m3_per_day(1.0, 24.0, [(5 * 3600, 9 * 3600), (17 * 3600, 21 * 3600)]) - 28.8) < 0.05
