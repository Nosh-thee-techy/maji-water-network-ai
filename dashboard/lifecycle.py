"""TaKaDu-style event lifecycle: open → assign → repair → verify leftover.

The dig list is step one of four. Verify re-reads after-fill leftover.
A field crew does that on the inlet. The dashboard can also *simulate*
a successful repair by substituting the no-leak after-fill — that is
labelled simulated, not a field close-out.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from baseline.emitter_calibrate import DETECT_THRESHOLD_LPS


STATES = ("open", "assigned", "repaired", "verified", "failed_verify")
KINDS = ("leak", "valve_did_not_open", "sensor_failure")


@dataclass
class NetworkEvent:
    event_id: str
    scenario_id: str
    kind: str
    state: str
    leftover_open_lps: float
    leftover_open_m3_day: float
    leftover_verify_lps: float | None
    assigned_to: str
    nodes: list[str]
    t_sat_s: list[float]
    opened_at: str
    history: list[dict[str, Any]] = field(default_factory=list)
    simulated_repair: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "NetworkEvent":
        return cls(**row)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_event(
    *,
    scenario_id: str,
    kind: str,
    leftover_lps: float,
    leftover_m3_day: float,
    nodes: list[str],
    t_sat_s: list[float],
) -> NetworkEvent:
    if kind not in KINDS:
        kind = "leak"
    ev = NetworkEvent(
        event_id=uuid4().hex[:10],
        scenario_id=scenario_id,
        kind=kind,
        state="open",
        leftover_open_lps=float(leftover_lps),
        leftover_open_m3_day=float(leftover_m3_day),
        leftover_verify_lps=None,
        assigned_to="",
        nodes=list(nodes),
        t_sat_s=[float(t) for t in t_sat_s],
        opened_at=_now(),
        history=[{"at": _now(), "action": "open", "state": "open"}],
    )
    return ev


def assign_crew(event: NetworkEvent, name: str) -> NetworkEvent:
    if event.state not in {"open", "assigned"}:
        raise ValueError(f"cannot assign from {event.state}")
    event.assigned_to = name.strip()
    event.state = "assigned"
    event.history.append({"at": _now(), "action": "assign", "to": event.assigned_to, "state": "assigned"})
    return event


def mark_repaired(event: NetworkEvent, *, simulated: bool = False) -> NetworkEvent:
    if event.state not in {"assigned", "repaired", "failed_verify"}:
        raise ValueError(f"cannot repair from {event.state} — assign a crew first")
    event.state = "repaired"
    event.simulated_repair = simulated
    event.history.append({"at": _now(), "action": "repair", "simulated": simulated, "state": "repaired"})
    return event


def verify_repair(
    leftover_open_lps: float,
    leftover_now_lps: float,
    *,
    detect_threshold_lps: float = DETECT_THRESHOLD_LPS,
    drop_frac: float = 0.5,
) -> str:
    """``verified`` if leftover fell below threshold or by ``drop_frac``."""
    if leftover_now_lps < detect_threshold_lps:
        return "verified"
    if leftover_open_lps > 0 and leftover_now_lps <= leftover_open_lps * (1.0 - drop_frac):
        return "verified"
    return "failed_verify"


def close_with_verify(event: NetworkEvent, leftover_now_lps: float) -> NetworkEvent:
    if event.state != "repaired":
        raise ValueError("verify only after repair")
    event.leftover_verify_lps = float(leftover_now_lps)
    event.state = verify_repair(event.leftover_open_lps, leftover_now_lps)
    event.history.append(
        {
            "at": _now(),
            "action": "verify",
            "leftover_lps": event.leftover_verify_lps,
            "state": event.state,
            "simulated": event.simulated_repair,
        }
    )
    return event


def load_events(path: Path) -> list[NetworkEvent]:
    path = Path(path)
    if not path.exists():
        return []
    import json

    rows = json.loads(path.read_text(encoding="utf-8"))
    return [NetworkEvent.from_dict(r) for r in rows]


def save_events(path: Path, events: list[NetworkEvent]) -> None:
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([e.to_dict() for e in events], indent=2), encoding="utf-8")
