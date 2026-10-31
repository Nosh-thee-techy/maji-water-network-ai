"""Shared EPANET fixtures. One 12 h pair is reused so the suite stays short."""

from __future__ import annotations

import pytest

from sim.leaks import leaks_from_q_lps
from sim.network import build_dma
from sim.scenario import run_scenario

DURATION_H = 12.0
FILL_START = 5 * 3600
FILL_END = FILL_START + 75 * 60
WINDOW_END = 9 * 3600


@pytest.fixture(scope="session")
def noleak_12h():
    return run_scenario(scenario_id="test-none", leaks=[], duration_h=DURATION_H, meter_bias=0.04)


@pytest.fixture(scope="session")
def leak_j07_12h():
    wn = build_dma()
    leaks = leaks_from_q_lps(wn, [("J07", 1.5)])
    return run_scenario(
        scenario_id="test-leak",
        leaks=leaks,
        duration_h=DURATION_H,
        unmetered_share={"J15": 0.4},
        meter_bias=0.04,
    )


@pytest.fixture(scope="session")
def tiny_leak_12h():
    """~1% of peak DMA inflow (~0.056 L/s). Expected to sit under sensor noise."""
    wn = build_dma()
    leaks = leaks_from_q_lps(wn, [("J07", 0.056)])
    return run_scenario(scenario_id="test-tiny", leaks=leaks, duration_h=DURATION_H)


def fill_times(sc) -> list[int]:
    return [t for t in sc.times_s if FILL_START <= t < FILL_END]


def after_times(sc) -> list[int]:
    return [t for t in sc.times_s if FILL_END <= t < WINDOW_END]


def closed_times(sc) -> list[int]:
    return [t for t in sc.times_s if t < FILL_START]
