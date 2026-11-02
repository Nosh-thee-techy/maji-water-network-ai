"""HTTP API for the operator web app.

    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from baseline.emitter_calibrate import estimate_leaks
from baseline.evaluate import engine_cache_dir, load_or_build_engine
from baseline.explain import explain_at_hour, explain_window
from model.recon import load_model, reconstruct_window
from dashboard.lifecycle import close_with_verify, load_events, mark_repaired, open_event, assign_crew, save_events
from dashboard.views import event_banner, ranked_dig_list, water_balance_view
from sim.demo_library import ensure_demo_library
from sim.io import load_scenario
from sim.network import JUNCTION_NAMES, RESERVOIR_ID, RESERVOIR_XY, junction_coordinates, pipe_table
from sim.observe import make_observations, valve_open_for_solver

EVENTS_PATH = ROOT / "results" / "events.json"
DEMO = ROOT / "results" / "demo"
PLACE = ROOT / "results" / "placement.json"

app = FastAPI(title="M.A.J.I", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ENGINE = None
_SENSORS: dict[str, list[str]] = {}
_GNN = None


@app.on_event("startup")
def _startup():
    global _ENGINE, _SENSORS, _GNN
    ensure_demo_library(DEMO)
    _ENGINE = load_or_build_engine(12.0, engine_cache_dir(12.0, ROOT / "results"))
    if PLACE.exists():
        raw = json.loads(PLACE.read_text(encoding="utf-8"))["placements"]
        _SENSORS = {k: v["sensors"] if isinstance(v, dict) else v for k, v in raw.items()}
    else:
        from placement.greedy import greedy_place

        _SENSORS = {str(b): greedy_place(_ENGINE["signatures"], _ENGINE["junctions"], b) for b in (5, 10, 15, 20)}
    _GNN = load_model("cpu")


def _index():
    path = DEMO / "index.json"
    if not path.exists():
        raise HTTPException(404, "demo library missing — run python -m sim.demo_library")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {"ok": True, "demo": (DEMO / "index.json").exists()}


@app.get("/api/scenarios")
def scenarios():
    return _index()


@app.get("/api/windows/{sid}")
def window(sid: str, budget: int = 10):
    ids = {r["scenario_id"] for r in _index()["scenarios"]}
    if sid not in ids:
        raise HTTPException(404, sid)
    meta, frames = load_scenario(DEMO, sid)
    sensors = _SENSORS.get(str(budget)) or _SENSORS.get("10") or []
    obs = make_observations(
        frames["pressure_m"],
        frames["inlet_flow_lps"],
        sensors,
        seed=meta["seed"] + budget,
        duration_h=meta["duration_h"],
    )
    p0 = _ENGINE["noleak"].pressure_m.reindex(meta["times_s"]).interpolate().bfill().ffill()
    q0 = _ENGINE["noleak"].inlet_flow_lps.reindex(meta["times_s"]).interpolate().bfill().ffill()
    est = estimate_leaks(
        pressure_obs=obs["pressure_m"].to_numpy(dtype=float),
        inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
        sensors=sensors,
        times_s=np.asarray(meta["times_s"]),
        p_noleak=p0[list(JUNCTION_NAMES)].to_numpy(dtype=float),
        inlet_noleak_lps=q0.to_numpy(dtype=float),
        sensitivity=_ENGINE["signatures"],
        candidate_nodes=_ENGINE["leak_nodes"],
        duration_h=meta["duration_h"],
        valve_open=valve_open_for_solver(obs),
    )
    inlet = frames["inlet_flow_lps"].to_numpy(dtype=float)
    press_s = float(np.sum(inlet > 0.05) * meta["timestep_s"])
    leaked_hat = est.q_total_lps * press_s / 1000.0
    view = water_balance_view(meta["water_balance_m3"], leaked_hat)
    banner = event_banner(est.event, est.q_total_lps, est.leftover_m3_per_day)
    story = explain_window(
        event=est.event,
        leftover_lps=est.q_total_lps,
        leftover_m3_per_day=est.leftover_m3_per_day,
        t_sat_s=est.t_sat_s,
        used_change_point=est.used_change_point,
        ranked=est.ranked,
        fill_minutes=meta.get("fill_minutes"),
    )
    def _num(v):
        f = float(v)
        return 0.0 if not np.isfinite(f) else f

    def _series(xs):
        return [_num(v) if np.isfinite(v) else None for v in np.asarray(xs, dtype=float)]

    times = np.asarray(meta["times_s"], dtype=float) / 3600.0
    q_obs = obs["inlet_flow_lps"].to_numpy(dtype=float)
    coords = junction_coordinates()
    coords[RESERVOIR_ID] = RESERVOIR_XY
    return {
        "id": sid,
        "label": next(r.get("label", sid) for r in _index()["scenarios"] if r["scenario_id"] == sid),
        "banner": banner,
        "story": story,
        "leftover_lps": _num(est.q_total_lps),
        "leftover_m3_per_day": _num(est.leftover_m3_per_day),
        "t_sat_s": [float(t) for t in est.t_sat_s],
        "event": est.event,
        "dig": ranked_dig_list(est.ranked) if banner["is_leak"] else [],
        "sensors": sensors,
        "hydrograph": {
            "t_h": _series(times),
            "q_clean_lps": _series(inlet),
            "q_uplink_lps": _series(q_obs),
            "t_sat_h": story["t_sat_h"],
        },
        "map": {
            "nodes": [{"id": n, "x": xy[0], "y": xy[1]} for n, xy in coords.items()],
            "pipes": [{"id": p, "a": a, "b": b} for p, a, b, _L, _D in pipe_table()],
            "sensors": sensors,
            "predicted": [n for n, _ in est.ranked[:2]] if banner["is_leak"] else [],
            "inlet": "J00",
        },
        "balance": {
            "supplied_m3": _num(view["supplied_m3"]),
            "leaked_hat_m3": _num(view["leaked_hat_m3"]),
            "billed_m3": _num(view["billed_m3"]),
            "note": view["note"],
        },
        "recon": reconstruct_window(sid, DEMO, sensors, _GNN),
    }


@app.get("/api/windows/{sid}/at")
def window_at(sid: str, hour: float, q: float, budget: int = 10):
    payload = window(sid, budget)
    return explain_at_hour(
        hour=hour,
        q_lps=q,
        t_sat_h=payload["hydrograph"]["t_sat_h"],
        leftover_lps=payload["leftover_lps"],
        event=payload["event"],
    )


@app.get("/api/events")
def events():
    return [e.to_dict() for e in load_events(EVENTS_PATH)]


@app.post("/api/events")
def events_open(payload: dict):
    ev = open_event(
        scenario_id=payload.get("scenario_id", ""),
        kind=payload.get("kind", "leak"),
        leftover_lps=float(payload.get("leftover_lps") or 0),
        leftover_m3_day=float(payload.get("leftover_m3_day") or 0),
        nodes=list(payload.get("nodes") or []),
        t_sat_s=list(payload.get("t_sat_s") or []),
    )
    store = load_events(EVENTS_PATH)
    store.append(ev)
    save_events(EVENTS_PATH, store)
    return ev.to_dict()


@app.post("/api/events/{eid}/{action}")
def events_act(eid: str, action: str, payload: dict | None = None):
    payload = payload or {}
    store = load_events(EVENTS_PATH)
    ev = next((e for e in store if e.event_id == eid), None)
    if ev is None:
        raise HTTPException(404, eid)
    if action == "assign":
        assign_crew(ev, str(payload.get("name") or "DMA crew"))
    elif action == "repair":
        mark_repaired(ev, simulated=bool(payload.get("simulated", True)))
    elif action == "verify":
        close_with_verify(ev, float(payload.get("leftover_now_lps") or 0.0))
    else:
        raise HTTPException(400, action)
    save_events(EVENTS_PATH, store)
    return ev.to_dict()


DIST = ROOT / "web" / "dist"


@app.get("/{path:path}")
def spa(path: str):
    """Serve the Vite build, including React Router paths like /network."""
    if not DIST.exists():
        raise HTTPException(404, "UI not built — run npm run build in web/")
    dist = DIST.resolve()
    candidate = (dist / path).resolve() if path else dist / "index.html"
    try:
        candidate.relative_to(dist)
    except ValueError as exc:
        raise HTTPException(404) from exc
    if path and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(dist / "index.html")
