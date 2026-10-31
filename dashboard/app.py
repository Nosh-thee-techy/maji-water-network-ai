"""M.A.J.I decision dashboard — Crew / Manager / Health.

    streamlit run dashboard/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from baseline.emitter_calibrate import estimate_leaks
from baseline.evaluate import build_noleak_and_sensitivity
from dashboard.views import (
    DEFAULT_INTRUSION_THRESHOLD_M,
    event_banner,
    intrusion_flags,
    intrusion_summary,
    ranked_dig_list,
    water_balance_view,
)
from sim.io import load_scenario
from sim.network import JUNCTION_NAMES, RESERVOIR_ID, RESERVOIR_XY, junction_coordinates, pipe_table
from sim.observe import make_observations, valve_open_for_solver


st.set_page_config(page_title="M.A.J.I", layout="wide")


@st.cache_resource
def _engine(duration_h: float):
    return build_noleak_and_sensitivity(duration_h)


@st.cache_data
def _index(data_dir: str):
    return json.loads(Path(data_dir).joinpath("index.json").read_text(encoding="utf-8"))


def _network_figure(sensors, leaks, risk_nodes, title):
    coords = junction_coordinates()
    coords[RESERVOIR_ID] = RESERVOIR_XY
    fig = go.Figure()
    for pid, a, b, _L, D in pipe_table():
        x0, y0 = coords[a]
        x1, y1 = coords[b]
        fig.add_trace(
            go.Scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line=dict(width=1.5 + 20 * D, color="#5d6d7e"),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    xs, ys, text, color = [], [], [], []
    for n, (x, y) in coords.items():
        xs.append(x)
        ys.append(y)
        text.append(n)
        if n == RESERVOIR_ID:
            color.append("#922b21")
        elif n in leaks:
            color.append("#f4d03f")
        elif n in risk_nodes:
            color.append("#c0392b")
        elif n in sensors:
            color.append("#27ae60")
        else:
            color.append("#aed6f1")
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=text,
            textposition="top center",
            marker=dict(size=14, color=color, line=dict(width=1, color="#1c2833")),
            name="nodes",
        )
    )
    fig.update_layout(
        title=title,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, scaleanchor="x"),
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="#fbfcfc",
        plot_bgcolor="#fbfcfc",
    )
    return fig


def main() -> None:
    st.title("M.A.J.I")
    st.caption(
        "Sparse-sensor twin for intermittent supply. All numbers on this page "
        "are **simulated**. Customer demand is storage-limited; a leak is an emitter."
    )
    data_dir = st.sidebar.text_input("Scenario library", "data/scenarios")
    index = _index(data_dir)
    ids = [row["scenario_id"] for row in index["scenarios"]]
    sid = st.sidebar.selectbox("Scenario", ids, index=0)
    budget = st.sidebar.selectbox("Sensor budget", [5, 10, 15, 20], index=1)
    threshold = st.sidebar.slider(
        "Intrusion-risk prior (m of head)",
        3.0,
        15.0,
        DEFAULT_INTRUSION_THRESHOLD_M,
        0.5,
        help="Starting prior from Kumpel & Nelson 2014 (~7 m). Change per district.",
    )
    st.sidebar.info(
        "Intrusion threshold is a **starting prior**, not a calibrated health standard."
    )

    meta, frames = load_scenario(Path(data_dir), sid)
    engine = _engine(meta["duration_h"])
    sensors = []
    # Prefer saved placement; fall back to greedy on the live engine.
    place_path = ROOT / "results" / "placement.json"
    if place_path.exists():
        sensors = json.loads(place_path.read_text(encoding="utf-8"))["placements"][str(budget)]["sensors"]
    else:
        from placement.greedy import greedy_place

        sensors = greedy_place(engine["signatures"], engine["junctions"], budget)

    obs = make_observations(
        frames["pressure_m"],
        frames["inlet_flow_lps"],
        sensors,
        seed=meta["seed"] + budget,
        duration_h=meta["duration_h"],
    )
    p0 = engine["noleak"].pressure_m.reindex(meta["times_s"]).interpolate().bfill().ffill()
    q0 = engine["noleak"].inlet_flow_lps.reindex(meta["times_s"]).interpolate().bfill().ffill()
    est = estimate_leaks(
        pressure_obs=obs["pressure_m"].to_numpy(dtype=float),
        inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
        sensors=sensors,
        times_s=np.asarray(meta["times_s"]),
        p_noleak=p0[list(JUNCTION_NAMES)].to_numpy(dtype=float),
        inlet_noleak_lps=q0.to_numpy(dtype=float),
        sensitivity=engine["signatures"],
        candidate_nodes=engine["leak_nodes"],
        duration_h=meta["duration_h"],
        valve_open=valve_open_for_solver(obs),
    )
    inlet = frames["inlet_flow_lps"].to_numpy(dtype=float)
    press_s = float(np.sum(inlet > 0.05) * meta["timestep_s"])
    leaked_hat = est.q_total_lps * press_s / 1000.0
    truth_leaks = [lk["node"] for lk in meta["leaks"]]
    flags = intrusion_flags(frames["pressure_m"], threshold_m=threshold)
    risk_nodes = [r["node"] for r in intrusion_summary(flags) if r["hours"] > 0.5]

    banner = event_banner(est.event, est.q_total_lps, est.leftover_m3_per_day)
    t_h = np.asarray(meta["times_s"]) / 3600.0
    crew, manager, health = st.tabs(["Crew — dig here", "Manager — water balance", "Health — intrusion risk"])

    with crew:
        st.subheader("Ranked dig list")
        if banner["is_leak"]:
            st.dataframe(pd.DataFrame(ranked_dig_list(est.ranked)), hide_index=True, width="stretch")
        elif banner["is_actionable_fault"]:
            st.warning(banner["label"])
        else:
            st.success(banner["label"])
        st.plotly_chart(
            _network_figure(sensors, truth_leaks, [n for n, _ in est.ranked[:2]], "DMA · sensors (green) · true leak (yellow) · predicted (red ring via rank)"),
            width="stretch",
        )
        sat_note = (
            f"t_sat from hydrograph at {[round(t / 3600, 2) for t in est.t_sat_s]} h"
            if est.used_change_point and est.t_sat_s
            else "clock fallback (75 min) — no knee on the inlet"
        )
        st.markdown(
            f"True leak nodes: `{truth_leaks or 'none (zero-leak scenario)'}` · "
            f"after-fill inlet residual **{est.q_total_lps:.2f} L/s** · {sat_note}"
        )
        fig = go.Figure()
        for s in sensors[:6]:
            fig.add_trace(go.Scatter(x=t_h, y=obs["pressure_m"][s], name=s, mode="lines"))
        fig.update_layout(
            height=280,
            title="Uplinked sensor pressure (IWS duty cycle — off-window is a 15 min heartbeat)",
            yaxis_title="m",
        )
        st.plotly_chart(fig, width="stretch")

    with manager:
        st.subheader("IWA-style water balance (simulated)")
        view = water_balance_view(meta["water_balance_m3"], leaked_hat)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Supplied", f"{view['supplied_m3']:.1f} m³")
        c2.metric("Leak (true)", f"{view['leaked_true_m3']:.1f} m³")
        c3.metric("Leak (estimate)", f"{view['leaked_hat_m3']:.1f} m³")
        c4.metric("Leftover (PBC)", f"{est.leftover_m3_per_day:.2f} m³/day")
        c5.metric("Billed", f"{view['billed_m3']:.1f} m³")
        st.caption(
            "Leftover m³/day is after-fill inlet residual × open hours, scaled to one day. "
            "That is the WASREB PBC unit (m³/day leakage reduced), not a 24 h always-on volume."
        )
        bal = pd.DataFrame(
            {
                "component": ["Leak (real loss)", "Unmetered (true)", "Meter error (true)", "Billed"],
                "m3": [
                    view["leaked_true_m3"],
                    view["unmetered_true_m3"],
                    view["meter_error_true_m3"],
                    view["billed_m3"],
                ],
            }
        )
        st.bar_chart(bal, x="component", y="m3", color="#1f4e79")
        st.caption(view["note"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t_h, y=frames["inlet_flow_lps"], name="inlet flow", line=dict(color="#1f4e79")))
        for t_sat in est.t_sat_s:
            fig.add_vline(
                x=t_sat / 3600.0,
                line_dash="dash",
                line_color="#c0392b",
                annotation_text="t_sat",
            )
        fig.update_layout(
            height=280,
            title="Inlet flow — knee is tank saturation; leftover after t_sat is the leak",
            yaxis_title="L/s",
        )
        st.plotly_chart(fig, width="stretch")

    with health:
        st.subheader("Intrusion-risk windows")
        st.caption(
            f"Flag = reconstructed (here: simulated true) pressure < **{threshold:.1f} m**. "
            "Kumpel & Nelson 2014 is the starting prior. Off-window slack is drained by construction."
        )
        summary = intrusion_summary(flags)
        if summary:
            st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")
        else:
            st.info("No node dropped below the prior in this scenario.")
        st.plotly_chart(
            _network_figure(sensors, truth_leaks, risk_nodes, "Nodes with low-pressure hours (red) · near-drain set is J11/J14–J17"),
            width="stretch",
        )
        node = st.selectbox("Pressure trace", list(JUNCTION_NAMES), index=5)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t_h, y=frames["pressure_m"][node], name=node))
        fig.add_hline(y=threshold, line_dash="dash", line_color="#8e44ad", annotation_text="prior")
        fig.update_layout(height=280, yaxis_title="m")
        st.plotly_chart(fig, width="stretch")


if __name__ == "__main__":
    main()
