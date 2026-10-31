"""If the 300-scenario library is on disk, check it is not a single-class toy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path("data/scenarios/index.json")


@pytest.mark.skipif(not DATA.exists(), reason="scenario library not generated on this machine")
def test_library_has_zero_leak_and_nonzero_leak_classes():
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    rows = payload["scenarios"]
    assert len(rows) >= 50
    n_zero = sum(1 for r in rows if r["n_leaks"] == 0)
    n_one = sum(1 for r in rows if r["n_leaks"] == 1)
    n_two = sum(1 for r in rows if r["n_leaks"] >= 2)
    assert n_zero >= 10
    assert n_one >= 10
    assert n_two >= 1
    residuals = [abs(r["water_balance_m3"]["residual"]) for r in rows]
    supplied = [r["water_balance_m3"]["supplied"] for r in rows]
    assert max(s > 0 for s in supplied)
    assert max(residuals) < 0.05 * max(supplied)


@pytest.mark.skipif(not Path("results/metrics.json").exists(), reason="metrics.json missing")
def test_reported_metrics_do_not_claim_gnn_beat_baseline():
    metrics = json.loads(Path("results/metrics.json").read_text(encoding="utf-8"))
    gnn = metrics["gnn_ensemble_budget_10"]
    assert gnn["beats_baseline_on_localisation"] is False
    assert metrics["battle_dim_official"]["status"] == "not_run"
    assert metrics["library"]["leak_q_ref_lps_range"][0] >= 0.8
