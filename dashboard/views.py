"""Three decision views derived from a scenario + a leak estimate."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from sim.network import JUNCTION_NAMES, junction_coordinates, pipe_table


# Kumpel & Nelson 2014: indicator bacteria common below ~10 psi (≈7 m).
# This is a starting prior, not a universal constant.
DEFAULT_INTRUSION_THRESHOLD_M = 7.0

# Schematic "near drain / sewer" nodes for the demo map. A real
# deployment would take these from utility / municipal GIS.
NEAR_CONTAMINATION = {"J11", "J15", "J16", "J17", "J14"}


EVENT_LABELS = {
    "leak": "Leak — leftover inlet flow persisted after tanks saturated",
    "no_leak": "No leak — after-fill inlet residual below threshold",
    "valve_did_not_open": "Valve did not open — scheduled window, no fill surge",
    "sensor_failure": "Sensor failure — after-fill inlet record is missing",
    "still_filling": "Still filling — hydrograph never dropped; no leftover yet",
}


def event_banner(event: str, leftover_lps: float, leftover_m3_per_day: float) -> dict:
    """Crew/manager copy for the three IWS event types (+ still-filling)."""
    return {
        "event": event,
        "label": EVENT_LABELS.get(event, event),
        "leftover_lps": leftover_lps,
        "leftover_m3_per_day": leftover_m3_per_day,
        "is_leak": event == "leak",
        "is_actionable_fault": event in {"valve_did_not_open", "sensor_failure"},
    }


def ranked_dig_list(estimate_ranked: list[tuple[str, float]], hop_radius: int = 2) -> list[dict]:
    rows = []
    for i, (node, q) in enumerate(estimate_ranked):
        rows.append(
            {
                "rank": i + 1,
                "node": node,
                "q_lps": q,
                "uncertainty_radius_hops": hop_radius,
                "note": f"dig near {node} (±{hop_radius} pipe segments)",
            }
        )
    return rows


def water_balance_view(truth: dict, leaked_hat_m3: float) -> dict:
    supplied = truth["supplied"]
    return {
        "supplied_m3": supplied,
        "leaked_true_m3": truth["leaked"],
        "leaked_hat_m3": leaked_hat_m3,
        "customer_m3": truth["customer"],
        "unmetered_true_m3": truth["unmetered"],
        "billed_m3": truth["billed"],
        "meter_error_true_m3": truth["meter_error"],
        "apparent_true_m3": truth["unmetered"] + truth["meter_error"],
        "apparent_hat_m3": max(0.0, truth["customer"] - truth["billed"]),
        "note": (
            "Apparent loss (unmetered + meter error) is billing − hydraulics. "
            "Pressure + inlet flow separate the leak; they do not split unmetered from meter error."
        ),
    }


def intrusion_flags(
    pressure_m: pd.DataFrame,
    *,
    threshold_m: float = DEFAULT_INTRUSION_THRESHOLD_M,
    near: Iterable[str] = NEAR_CONTAMINATION,
) -> pd.DataFrame:
    """Per-node, per-time flag when reconstructed head is below the prior."""
    near = set(near)
    flags = pressure_m[list(JUNCTION_NAMES)] < threshold_m
    out = flags.copy()
    out.attrs["threshold_m"] = threshold_m
    out.attrs["near_contamination"] = sorted(near)
    return out


def intrusion_summary(flags: pd.DataFrame, near: Iterable[str] = NEAR_CONTAMINATION) -> list[dict]:
    near = set(near)
    rows = []
    for node in flags.columns:
        n = int(flags[node].sum())
        if n == 0:
            continue
        rows.append(
            {
                "node": node,
                "low_pressure_steps": n,
                "near_drain_or_sewer": node in near,
                "hours": n * 5 / 60.0,
            }
        )
    rows.sort(key=lambda r: (not r["near_drain_or_sewer"], -r["hours"]))
    return rows


def network_plot_frame():
    return {
        "coords": junction_coordinates(),
        "pipes": pipe_table(),
    }
