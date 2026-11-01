"""Event state machine: open → assign → repair → verify leftover."""

from __future__ import annotations

import pytest

from dashboard.lifecycle import (
    assign_crew,
    close_with_verify,
    mark_repaired,
    open_event,
    verify_repair,
)


def test_verify_repair_thresholds():
    assert verify_repair(1.4, 0.10) == "verified"
    assert verify_repair(1.4, 1.35) == "failed_verify"
    assert verify_repair(1.4, 0.60) == "verified"  # fell by >50%


def test_full_lifecycle_closes_when_leftover_falls():
    ev = open_event(
        scenario_id="s0001",
        kind="leak",
        leftover_lps=1.4,
        leftover_m3_day=40.0,
        nodes=["J07"],
        t_sat_s=[22500.0],
    )
    assert ev.state == "open"
    ev = assign_crew(ev, "DMA crew 2")
    assert ev.state == "assigned"
    ev = mark_repaired(ev, simulated=True)
    assert ev.state == "repaired"
    assert ev.simulated_repair is True
    ev = close_with_verify(ev, 0.08)
    assert ev.state == "verified"
    assert ev.leftover_verify_lps == 0.08


def test_cannot_repair_before_assign():
    ev = open_event(
        scenario_id="s0001",
        kind="leak",
        leftover_lps=1.4,
        leftover_m3_day=40.0,
        nodes=["J07"],
        t_sat_s=[],
    )
    with pytest.raises(ValueError):
        mark_repaired(ev)


def test_failed_verify_stays_open_for_another_dig():
    ev = open_event(
        scenario_id="s0001",
        kind="leak",
        leftover_lps=1.4,
        leftover_m3_day=40.0,
        nodes=["J07"],
        t_sat_s=[],
    )
    assign_crew(ev, "crew")
    mark_repaired(ev)
    close_with_verify(ev, 1.38)
    assert ev.state == "failed_verify"
    # Crew can mark repaired again after a failed verify.
    mark_repaired(ev)
    assert ev.state == "repaired"
