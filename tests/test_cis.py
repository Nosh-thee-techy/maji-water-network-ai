"""CIS ingest: leftover is real loss; apparent is not a leak alarm."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from baseline.cis import export_cis_from_scenario, ingest_cis, split_iwa, write_cis


def test_ingest_requires_billed_columns(tmp_path: Path):
    bad = tmp_path / "bad.csv"
    bad.write_text("name,amount\nA,1\n", encoding="utf-8")
    try:
        ingest_cis(bad)
        assert False, "should have raised"
    except ValueError as exc:
        assert "missing columns" in str(exc)


def test_split_does_not_alarm_on_apparent_residual():
    cis = pd.DataFrame(
        {
            "account_id": ["A1", "A2"],
            "node": ["J01", "J07"],
            "billed_m3": [8.0, 0.0],
            "account_class": ["metered", "unmetered"],
        }
    )
    split = split_iwa(supplied_m3=12.0, leftover_real_loss_m3=2.0, cis=cis)
    assert split.billed_m3 == 8.0
    assert split.leftover_real_loss_m3 == 2.0
    assert abs(split.apparent_residual_m3 - 2.0) < 1e-9
    assert split.alarms_from_apparent is False
    assert split.n_unmetered == 1
    assert "cannot split" in split.note.lower() or "cannot split theft" in split.note.lower()


def test_unmetered_tag_is_not_a_leak_count():
    cis = pd.DataFrame(
        {
            "account_id": ["U1"],
            "node": ["J11"],
            "billed_m3": [0.0],
            "account_class": ["unmetered"],
        }
    )
    split = split_iwa(supplied_m3=5.0, leftover_real_loss_m3=0.1, cis=cis)
    assert split.n_unmetered == 1
    assert split.alarms_from_apparent is False


def test_export_roundtrip_matches_hidden_billed(tmp_path: Path):
    idx = [0, 1000]
    customer = pd.DataFrame({"J01": [8.0, 0.0], "J07": [0.0, 0.0]}, index=idx)
    # J07 has no customer — skipped. J01 unmetered 25%, bias 10%.
    cis = export_cis_from_scenario(
        customer_lps=customer,
        unmetered_share={"J01": 0.25},
        meter_bias=0.10,
        timestep_s=1000.0,
    )
    path = write_cis(tmp_path / "cis.csv", cis)
    back = ingest_cis(path)
    assert list(back["account_id"]) == ["N-J01"]
    assert back.loc[0, "account_class"] == "unmetered"
    # customer 8 m³, unmetered 2, metered 6, billed 5.4
    assert abs(float(back.loc[0, "billed_m3"]) - 5.4) < 1e-9
    split = split_iwa(supplied_m3=10.0, leftover_real_loss_m3=2.0, cis=back)
    assert abs(split.billed_m3 - 5.4) < 1e-9
    assert split.alarms_from_apparent is False
