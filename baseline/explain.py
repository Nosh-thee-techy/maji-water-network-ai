"""Plain-language brief of one supply window.

This is not a leak detector. Detection is leftover litres per second after
t_sat. The brief only translates that number into crew/manager English.
"""

from __future__ import annotations

from dashboard.views import EVENT_LABELS


def explain_window(
    *,
    event: str,
    leftover_lps: float,
    leftover_m3_per_day: float,
    t_sat_s: list[float],
    used_change_point: bool,
    ranked: list[tuple[str, float]],
    fill_minutes: float | None = None,
) -> dict:
    t_sat_h = [round(t / 3600.0, 2) for t in t_sat_s if t is not None]
    sat = f"{t_sat_h[0]:.2f} h" if t_sat_h else "unknown"
    top = ranked[0][0] if ranked else None

    if event == "leak":
        headline = f"Leftover {leftover_lps:.2f} L/s after tanks filled — that is the leak."
        action = (
            f"Dig near {top} (±2 pipe segments). Close the job only when leftover "
            f"falls below 0.35 L/s or drops by half. PBC unit: {leftover_m3_per_day:.1f} m³/day."
        )
        beats = [
            {
                "title": "Valve opened",
                "body": "The inlet opened. Household tanks started drawing — a high plateau on the inlet, not a leak.",
            },
            {
                "title": f"Tanks full at {sat}",
                "body": (
                    "The hydrograph dropped and stayed down. That knee is t_sat, found on the inlet, "
                    "not a 75-minute clock."
                    if used_change_point
                    else "No clear knee — the clock fallback was used. Treat leftover with more caution."
                ),
            },
            {
                "title": "Leftover is leakage",
                "body": (
                    f"After t_sat the inlet should be ~0. It is {leftover_lps:.2f} L/s "
                    f"({leftover_m3_per_day:.1f} m³/day on open hours). Customers are no longer drawing."
                ),
            },
        ]
    elif event == "no_leak":
        headline = "Tanks filled. Inlet leftover is below the 0.35 L/s floor. No leak this window."
        action = "No dig. A Sunday update may absorb a tiny meter offset if leftover stays clean."
        beats = [
            {"title": "Valve opened", "body": "Fill surge on the inlet — tanks drawing."},
            {
                "title": f"Tanks full at {sat}",
                "body": "The knee is on the hydrograph." if used_change_point else "Clock fallback — no clear knee.",
            },
            {
                "title": "After-fill is quiet",
                "body": f"Leftover {leftover_lps:.2f} L/s is noise, not an orifice.",
            },
        ]
    elif event == "valve_did_not_open":
        headline = "This window was scheduled, but the inlet never filled the tanks."
        action = "Do not send a leak crew. Check the inlet valve and the duty-cycle uplink."
        beats = [
            {"title": "Schedule said open", "body": "A rationing window was on the clock."},
            {"title": "No fill surge", "body": "Inlet flow never rose. That is a valve or a dead logger, not leftover leakage."},
            {"title": "Not a leak", "body": "Leftover logic only runs after tanks saturate."},
        ]
    elif event == "sensor_failure":
        headline = "The after-fill record is missing. We cannot call this a clean DMA."
        action = "Fix the inlet logger before the next window. A hole on the leftover plateau is a sensor-failure event."
        beats = [
            {"title": "Fill may have happened", "body": "The window started."},
            {"title": "After-fill is a hole", "body": "Duty-cycle / radio dropped the one stretch that is the leak test."},
            {"title": "No all-clear", "body": "Missing leftover ≠ no leak."},
        ]
    else:
        headline = EVENT_LABELS.get(event, event)
        action = "Wait for the hydrograph to drop before calling leftover."
        beats = [
            {"title": "Still filling", "body": "Tanks have not saturated. Leftover is not defined yet."},
        ]

    return {
        "headline": headline,
        "beats": beats,
        "action": action,
        "label": EVENT_LABELS.get(event, event),
        "t_sat_h": t_sat_h,
        "fill_minutes": fill_minutes,
        "model_note": (
            "Detection is leftover flow, not a neural net. A graph net trained on this DMA "
            "reconstructed pressure (1.15 m MAE) but leak TPR was 0. It is not used for this decision."
        ),
    }


def explain_at_hour(
    *,
    hour: float,
    q_lps: float,
    t_sat_h: list[float],
    leftover_lps: float,
    event: str,
) -> dict:
    """What the inlet means at one clock time. Not a leak classifier."""
    h = hour % 24
    open_am = 5.0 <= h < 9.0
    open_pm = 17.0 <= h < 21.0
    sat = t_sat_h[0] if t_sat_h else None
    if event == "valve_did_not_open":
        return {
            "phase": "valve",
            "title": "No fill surge",
            "body": f"At {hour:.2f} h the inlet is {q_lps:.2f} L/s. The window was scheduled but tanks never drew. Check the valve, not a leak crew.",
        }
    if not (open_am or open_pm):
        return {
            "phase": "off",
            "title": "Inlet closed",
            "body": f"At {hour:.2f} h the DMA is slack. {q_lps:.2f} L/s is not leftover — leftover only exists while the valve is still open after tanks fill.",
        }
    if sat is None:
        return {
            "phase": "open",
            "title": "Window open, no knee yet",
            "body": f"{q_lps:.2f} L/s on an open inlet. We do not have t_sat, so this mix of tank draw and possible leftover is not a call.",
        }
    if hour < sat:
        return {
            "phase": "fill",
            "title": "Tanks still drawing",
            "body": (
                f"{q_lps:.2f} L/s before t_sat ({sat:.2f} h). That plateau is household storage, "
                "the reason classic night-flow fails on intermittent supply."
            ),
        }
    if leftover_lps >= 0.35 or event == "leak":
        return {
            "phase": "leftover",
            "title": "After tanks full — leftover is the leak test",
            "body": (
                f"{q_lps:.2f} L/s after {sat:.2f} h. Customers should have stopped. "
                f"Window leftover is {leftover_lps:.2f} L/s (floor 0.35). This is the scientific hook, not a neural net."
            ),
        }
    return {
        "phase": "quiet",
        "title": "After tanks full — inlet is quiet",
        "body": f"{q_lps:.2f} L/s after {sat:.2f} h. Below the 0.35 L/s floor. No leak this window.",
    }
