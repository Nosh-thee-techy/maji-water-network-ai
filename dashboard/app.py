"""M.A.J.I operator console — Crew / Manager / Health / Events / CIS.

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

from baseline.cis import export_cis_from_scenario, ingest_cis, split_iwa
from baseline.emitter_calibrate import estimate_leaks
from baseline.evaluate import build_noleak_and_sensitivity
from baseline.recalibrate import sunday_update
from baseline.saturation import detect_saturation
from dashboard.lifecycle import (
    assign_crew,
    close_with_verify,
    load_events,
    mark_repaired,
    open_event,
    save_events,
)
from dashboard.views import (
    DEFAULT_INTRUSION_THRESHOLD_M,
    event_banner,
    intrusion_flags,
    intrusion_summary,
    ranked_dig_list,
    water_balance_view,
)
from sim.demo_library import write_demo
from sim.io import load_scenario
from sim.network import JUNCTION_NAMES, RESERVOIR_ID, RESERVOIR_XY, junction_coordinates, pipe_table
from sim.observe import make_observations, valve_open_for_solver

EVENTS_PATH = ROOT / "results" / "events.json"
DEMO_DIR = ROOT / "results" / "demo"

STATUS_TONE = {
    "leak": ("LEAK", "#9a3412", "#ffedd5"),
    "no_leak": ("CLEAN", "#047857", "#d1fae5"),
    "valve_did_not_open": ("VALVE", "#b91c1c", "#fee2e2"),
    "sensor_failure": ("SENSOR", "#b91c1c", "#fee2e2"),
    "still_filling": ("FILLING", "#1d4ed8", "#dbeafe"),
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: "IBM Plex Sans", "Segoe UI", sans-serif; }
.stApp { background: #f4f7f8; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.2rem; max-width: 1280px; }
.maji-top {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 1.5rem; margin-bottom: 0.4rem;
}
.maji-brand { font-size: 1.65rem; font-weight: 700; letter-spacing: 0.04em; color: #0f1720; margin: 0; }
.maji-sub { color: #475569; margin: 0.2rem 0 0; font-size: 0.95rem; max-width: 42rem; }
.maji-pill {
    font-family: "IBM Plex Mono", monospace; font-weight: 500; font-size: 0.82rem;
    letter-spacing: 0.08em; padding: 0.45rem 0.85rem; border-radius: 999px;
    border: 1px solid currentColor; white-space: nowrap;
}
.maji-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin: 0.9rem 0 1.1rem; }
.maji-kpi {
    background: #fff; border: 1px solid #d5dee3; border-radius: 12px; padding: 0.85rem 1rem;
}
.maji-kpi span { display: block; font-size: 0.75rem; color: #64748b; letter-spacing: 0.04em; text-transform: uppercase; }
.maji-kpi strong { display: block; font-size: 1.35rem; color: #0f1720; margin-top: 0.2rem; font-variant-numeric: tabular-nums; }
.maji-sim {
    font-size: 0.78rem; color: #b45309; background: #fffbeb; border: 1px solid #fde68a;
    border-radius: 8px; padding: 0.4rem 0.7rem; margin-bottom: 0.8rem;
}
[data-testid="stSidebar"] { background: #e8eef1; }
[data-testid="stTabs"] button { font-weight: 600; }
</style>
"""


st.set_page_config(page_title="M.A.J.I — leftover flow", layout="wide")


@st.cache_resource
def _engine(duration_h: float):
    return build_noleak_and_sensitivity(duration_h)


@st.cache_data
def _index(data_dir: str):
    return json.loads(Path(data_dir).joinpath("index.json").read_text(encoding="utf-8"))


def _resolve_library(raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    if (p / "index.json").exists():
        return p
    if not (DEMO_DIR / "index.json").exists():
        write_demo(DEMO_DIR)
        _index.clear()
    return DEMO_DIR


def _style_fig(fig: go.Figure, title: str, ytitle: str, height: int = 300) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#0f1720")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#f8fafb",
        font=dict(color="#334155", family="IBM Plex Sans, Segoe UI, sans-serif"),
        height=height,
        margin=dict(l=48, r=12, t=46, b=36),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
        xaxis=dict(gridcolor="#e2e8f0", zeroline=False),
        yaxis=dict(title=ytitle, gridcolor="#e2e8f0", zeroline=False),
    )
    return fig


def _network_figure(sensors, truth_leaks, predicted, title, *, show_truth: bool):
    coords = junction_coordinates()
    coords[RESERVOIR_ID] = RESERVOIR_XY
    fig = go.Figure()
    for _pid, a, b, _L, D in pipe_table():
        x0, y0 = coords[a]
        x1, y1 = coords[b]
        fig.add_trace(
            go.Scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line=dict(width=1.4 + 16 * D, color="#94a3b8"),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    xs, ys, text, color, size = [], [], [], [], []
    for n, (x, y) in coords.items():
        xs.append(x)
        ys.append(y)
        text.append(n)
        if n == RESERVOIR_ID:
            color.append("#0f172a")
            size.append(16)
        elif show_truth and n in truth_leaks:
            color.append("#eab308")
            size.append(16)
        elif n in predicted:
            color.append("#dc2626")
            size.append(16)
        elif n in sensors:
            color.append("#0d9488")
            size.append(14)
        else:
            color.append("#bae6fd")
            size.append(11)
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=text,
            textposition="top center",
            textfont=dict(size=10, color="#334155"),
            marker=dict(size=size, color=color, line=dict(width=1, color="#0f172a")),
            name="nodes",
            showlegend=False,
        )
    )
    return _style_fig(fig, title, "", height=400)


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)

    st.sidebar.markdown("**DMA control**")
    data_dir = st.sidebar.text_input("Scenario library", "results/demo")
    operator = st.sidebar.toggle(
        "Operator view",
        value=True,
        help="Hide ground-truth leak paint and true IWA splits. Lab view shows the simulated answers.",
    )
    budget = st.sidebar.selectbox("Pressure-sensor budget", [5, 10, 15, 20], index=1)
    threshold = st.sidebar.slider(
        "Intrusion prior (m of head)",
        3.0,
        15.0,
        DEFAULT_INTRUSION_THRESHOLD_M,
        0.5,
        help="Kumpel & Nelson 2014 (~7 m). Starting prior, not a health standard.",
    )
    st.sidebar.caption("Year-1 SKU is the inlet chamber, not this 10-node grid.")

    lib = _resolve_library(data_dir)
    if lib == DEMO_DIR and Path(data_dir) != DEMO_DIR and not (ROOT / data_dir / "index.json").exists():
        st.sidebar.warning("Library missing — opened the 12 h demo pack.")
    index = _index(str(lib))
    rows = index["scenarios"]
    labels = {r["scenario_id"]: r.get("label", r["scenario_id"]) for r in rows}
    ids = [r["scenario_id"] for r in rows]
    sid = st.sidebar.selectbox("Window", ids, format_func=lambda i: labels.get(i, i))

    meta, frames = load_scenario(lib, sid)
    engine = _engine(meta["duration_h"])
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
    q0_arr = q0.to_numpy(dtype=float)
    if st.session_state.get("noleak_q_override") is not None:
        ov = np.asarray(st.session_state["noleak_q_override"], dtype=float)
        if ov.shape == q0_arr.shape:
            q0_arr = ov
    est = estimate_leaks(
        pressure_obs=obs["pressure_m"].to_numpy(dtype=float),
        inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
        sensors=sensors,
        times_s=np.asarray(meta["times_s"]),
        p_noleak=p0[list(JUNCTION_NAMES)].to_numpy(dtype=float),
        inlet_noleak_lps=q0_arr,
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
    predicted = [n for n, _ in est.ranked[:2]] if banner["is_leak"] else []
    tone_label, tone_fg, tone_bg = STATUS_TONE.get(est.event, (est.event.upper(), "#334155", "#e2e8f0"))
    sat_note = (
        f"t_sat {[round(t / 3600, 2) for t in est.t_sat_s]} h"
        if est.used_change_point and est.t_sat_s
        else "no knee — clock fallback"
    )

    st.markdown(
        f"""
        <div class="maji-top">
          <div>
            <p class="maji-brand">M.A.J.I</p>
            <p class="maji-sub">Each supply window is a short night-flow test.
            After tanks saturate, leftover inlet flow is the leak.</p>
          </div>
          <div class="maji-pill" style="color:{tone_fg};background:{tone_bg}">{tone_label}</div>
        </div>
        <div class="maji-sim">Simulated schematic DMA · not a field measurement ·
        leftover is m³/day on open hours, not 24 h always-on</div>
        <div class="maji-kpis">
          <div class="maji-kpi"><span>After-fill leftover</span><strong>{est.q_total_lps:.2f} L/s</strong></div>
          <div class="maji-kpi"><span>PBC leftover</span><strong>{est.leftover_m3_per_day:.1f} m³/d</strong></div>
          <div class="maji-kpi"><span>Event</span><strong>{est.event.replace("_", " ")}</strong></div>
          <div class="maji-kpi"><span>Saturation</span><strong>{sat_note}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    crew, manager, health, events_tab, cis_tab = st.tabs(
        ["Crew", "Manager", "Health", "Events", "CIS"]
    )

    with crew:
        st.caption(banner["label"])
        if banner["is_leak"]:
            st.dataframe(pd.DataFrame(ranked_dig_list(est.ranked)), hide_index=True, width="stretch")
        elif banner["is_actionable_fault"]:
            st.warning(banner["label"])
        else:
            st.success(banner["label"])
        map_title = "DMA · teal sensors · red = dig rank"
        if not operator:
            map_title += " · yellow = true leak"
        st.plotly_chart(
            _network_figure(sensors, truth_leaks, predicted, map_title, show_truth=not operator),
            width="stretch",
        )
        if operator:
            st.caption(f"Dig near `{predicted or '—'}` · {sat_note}")
        else:
            st.caption(f"True leak `{truth_leaks or 'none'}` · residual **{est.q_total_lps:.2f} L/s** · {sat_note}")
        fig = go.Figure()
        for s in sensors[:6]:
            fig.add_trace(go.Scatter(x=t_h, y=obs["pressure_m"][s], name=s, mode="lines", line=dict(width=1.6)))
        st.plotly_chart(
            _style_fig(fig, "Uplinked pressure — off-window is a 15 min heartbeat", "m"),
            width="stretch",
        )

    with manager:
        view = water_balance_view(meta["water_balance_m3"], leaked_hat)
        if operator:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Supplied", f"{view['supplied_m3']:.1f} m³")
            c2.metric("Leak (estimate)", f"{view['leaked_hat_m3']:.1f} m³")
            c3.metric("Leftover (PBC)", f"{est.leftover_m3_per_day:.2f} m³/day")
            c4.metric("Billed", f"{view['billed_m3']:.1f} m³")
        else:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Supplied", f"{view['supplied_m3']:.1f} m³")
            c2.metric("Leak (true)", f"{view['leaked_true_m3']:.1f} m³")
            c3.metric("Leak (estimate)", f"{view['leaked_hat_m3']:.1f} m³")
            c4.metric("Leftover (PBC)", f"{est.leftover_m3_per_day:.2f} m³/day")
            c5.metric("Billed", f"{view['billed_m3']:.1f} m³")
        st.caption(
            "Leftover m³/day = after-fill residual × open hours, scaled to one day. "
            "WASREB PBC unit, not a 24 h always-on volume."
        )
        c_sun, c_reset = st.columns(2)
        if c_sun.button("Sunday update — teach the no-leak model this after-fill"):
            sat = detect_saturation(
                np.asarray(meta["times_s"], dtype=float),
                obs["inlet_flow_lps"].to_numpy(dtype=float),
                meta["duration_h"],
                valve_open=valve_open_for_solver(obs),
                inlet_noleak_lps=q0_arr,
            )
            rec = sunday_update(
                inlet_noleak_lps=q0_arr,
                inlet_obs_lps=obs["inlet_flow_lps"].to_numpy(dtype=float),
                after_mask=sat.after_mask,
                leftover_lps=sat.leftover_lps if sat.event == "no_leak" else max(sat.leftover_lps, 0.35),
            )
            if rec.applied:
                st.session_state["noleak_q_override"] = rec.inlet_noleak_lps
                st.success(rec.reason)
                st.rerun()
            else:
                st.warning(rec.reason)
        if st.session_state.get("noleak_q_override") is not None:
            if c_reset.button("Reset no-leak baseline"):
                st.session_state["noleak_q_override"] = None
                st.rerun()
            st.caption("No-leak inlet is a Sunday update of the frozen model, not a new EPANET run.")
        if operator:
            bal = pd.DataFrame(
                {
                    "component": ["Leak (estimate)", "Billed"],
                    "m3": [view["leaked_hat_m3"], view["billed_m3"]],
                }
            )
        else:
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
        st.bar_chart(bal, x="component", y="m3", color="#0e7490")
        st.caption(view["note"])
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(x=t_h, y=frames["inlet_flow_lps"], name="inlet flow", line=dict(color="#0e7490", width=2))
        )
        for t_sat in est.t_sat_s:
            fig.add_vline(x=t_sat / 3600.0, line_dash="dash", line_color="#c2410c", annotation_text="t_sat")
        st.plotly_chart(
            _style_fig(fig, "Inlet hydrograph — knee is tank saturation; leftover after t_sat is the leak", "L/s"),
            width="stretch",
        )

    with health:
        st.caption(
            f"Flag = pressure < **{threshold:.1f} m** (Kumpel & Nelson starting prior). "
            "Off-window slack is drained by construction."
        )
        summary = intrusion_summary(flags)
        if summary:
            st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")
        else:
            st.info("No node dropped below the prior in this window.")
        st.plotly_chart(
            _network_figure(
                sensors,
                truth_leaks,
                risk_nodes,
                "Low-pressure hours in red · near-drain set J11 / J14–J17",
                show_truth=not operator,
            ),
            width="stretch",
        )
        node = st.selectbox("Pressure trace", list(JUNCTION_NAMES), index=5)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t_h, y=frames["pressure_m"][node], name=node, line=dict(color="#0f766e")))
        fig.add_hline(y=threshold, line_dash="dash", line_color="#7c3aed", annotation_text="prior")
        st.plotly_chart(_style_fig(fig, f"Pressure at {node}", "m"), width="stretch")

    with events_tab:
        st.caption("Open → assign crew → repair → verify leftover fell. A simulated repair is labelled.")
        store = load_events(EVENTS_PATH)
        if banner["is_leak"] or banner["is_actionable_fault"]:
            if st.button("Open event from this window"):
                ev = open_event(
                    scenario_id=sid,
                    kind=est.event if est.event in {"leak", "valve_did_not_open", "sensor_failure"} else "leak",
                    leftover_lps=est.q_total_lps,
                    leftover_m3_day=est.leftover_m3_per_day,
                    nodes=predicted,
                    t_sat_s=est.t_sat_s,
                )
                store.append(ev)
                save_events(EVENTS_PATH, store)
                st.rerun()
        if not store:
            st.info("No events yet. Detect a leak and open one.")
        for ev in store:
            with st.expander(
                f"{ev.event_id} · {ev.kind} · {ev.state} · {ev.scenario_id}",
                expanded=ev.state != "verified",
            ):
                st.write(
                    f"Opened leftover **{ev.leftover_open_lps:.2f} L/s** "
                    f"({ev.leftover_open_m3_day:.1f} m³/day) · nodes `{ev.nodes}`"
                )
                if ev.state in {"open", "assigned"}:
                    name = st.text_input("Assign crew", value=ev.assigned_to, key=f"crew-{ev.event_id}")
                    if st.button("Assign", key=f"as-{ev.event_id}") and name.strip():
                        assign_crew(ev, name)
                        save_events(EVENTS_PATH, store)
                        st.rerun()
                if ev.state in {"assigned", "failed_verify"}:
                    sim = st.checkbox("Simulate successful repair", key=f"sim-{ev.event_id}")
                    if st.button("Mark repaired", key=f"rp-{ev.event_id}"):
                        mark_repaired(ev, simulated=sim)
                        save_events(EVENTS_PATH, store)
                        st.rerun()
                if ev.state == "repaired":
                    if st.button("Verify leftover", key=f"vf-{ev.event_id}"):
                        now_q = 0.0 if ev.simulated_repair else est.q_total_lps
                        close_with_verify(ev, now_q)
                        save_events(EVENTS_PATH, store)
                        st.rerun()
                if ev.leftover_verify_lps is not None:
                    st.write(
                        f"Verify leftover **{ev.leftover_verify_lps:.2f} L/s** → **{ev.state}**"
                        + (" (simulated)" if ev.simulated_repair else "")
                    )
                st.dataframe(pd.DataFrame(ev.history), hide_index=True, width="stretch")

    with cis_tab:
        st.caption(
            "Leftover is real loss. The billed file is the commercial residual. "
            "Pressure cannot split theft from meter error. Unmetered accounts are tagged, not alarmed."
        )
        generated = export_cis_from_scenario(
            customer_lps=frames["customer_lps"],
            unmetered_share=meta.get("unmetered_share") or {},
            meter_bias=float(meta.get("meter_bias") or 0.0),
            timestep_s=float(meta["timestep_s"]),
        )
        uploaded = st.file_uploader("CIS export (CSV)", type=["csv"])
        if uploaded is not None:
            cis = ingest_cis(uploaded)
            st.info("Using the uploaded billed file.")
        else:
            cis = generated
            st.caption("Simulated CIS extract from this window. Upload a utility file to replace it.")
        split = split_iwa(
            supplied_m3=float(meta["water_balance_m3"]["supplied"]),
            leftover_real_loss_m3=leaked_hat,
            cis=cis,
        )
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Billed (CIS)", f"{split.billed_m3:.1f} m³")
        d2.metric("Real loss (leftover)", f"{split.leftover_real_loss_m3:.1f} m³")
        d3.metric("Apparent residual", f"{split.apparent_residual_m3:.1f} m³")
        d4.metric("Unmetered accounts", f"{split.n_unmetered}")
        st.caption(split.note)
        if split.alarms_from_apparent:
            st.error("CIS residual must not open a leak event.")
        else:
            st.success("No leak event opened from the billed residual.")
        st.dataframe(cis, hide_index=True, width="stretch")
        st.download_button(
            "Download this CIS extract",
            cis.to_csv(index=False).encode("utf-8"),
            file_name=f"{sid}_cis.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
