"""Official BattLeDIM 2019 score — labelled continuous negative control.

Downloads only the evaluation-year CSVs + nominal INP (~38 MB), not
L-TOWN_Real.inp or the xlsx bundles. Solvers see SCADA flows/pressures
and the published leak timeseries for *scoring*, not for detection.

    python -m benchmarks.battledim

This is not intermittent-supply evidence.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import networkx as nx
import wntr

from benchmarks.battledim_score import (
    CR_EUR,
    CW_EUR_PER_M3,
    PERFECT_SCORE_EUR,
    XMAX_M,
    Detection,
    detect_mnf_and_bursts,
    leak_events_from_timeseries,
    localise_link,
    official_score,
    read_battledim_csv,
)

ZENODO = "https://zenodo.org/records/4017659/files"
FILES = (
    "L-TOWN.inp",
    "2019_Leakages.csv",
    "2019_SCADA_Flows.csv",
    "2019_SCADA_Pressures.csv",
    "dataset_configuration.yaml",
    "README.txt",
)
RAW = Path("data/raw/battledim")
OUT = Path("results/battledim_2019.json")


def fetch(dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "mmaji-battledim/1.0")]
    urllib.request.install_opener(opener)
    for name in FILES:
        dest = dest_dir / name
        if dest.exists() and dest.stat().st_size > 500:
            print(f"  have {name} ({dest.stat().st_size} B)")
            continue
        url = f"{ZENODO}/{name}?download=1"
        print(f"  downloading {name}")
        urllib.request.urlretrieve(url, dest)
        print(f"    -> {dest.stat().st_size} B")
    return dest_dir


def pipe_graph(inp: Path):
    wn = wntr.network.WaterNetworkModel(str(inp))
    G = nx.Graph()
    incident: dict[str, list[str]] = {}
    for name, link in wn.links():
        a, b = link.start_node_name, link.end_node_name
        length = float(getattr(link, "length", 0.0) or 0.0)
        G.add_edge(a, b, length=length, link=name)
        incident.setdefault(a, []).append(name)
        incident.setdefault(b, []).append(name)
    return wn, G, incident


def link_distance_fn(wn, G):
    cache: dict[tuple[str, str], float] = {}

    def dist(a: str, b: str) -> float:
        if a == b:
            return 0.0
        key = (a, b) if a < b else (b, a)
        if key in cache:
            return cache[key]
        if a not in wn.link_name_list or b not in wn.link_name_list:
            cache[key] = 1e9
            return 1e9
        la, lb = wn.get_link(a), wn.get_link(b)
        na = (la.start_node_name, la.end_node_name)
        nb = (lb.start_node_name, lb.end_node_name)
        best = 1e9
        for u in na:
            if u not in G:
                continue
            for v in nb:
                if v not in G:
                    continue
                try:
                    best = min(best, float(nx.shortest_path_length(G, u, v, weight="length")))
                except nx.NetworkXNoPath:
                    continue
        cache[key] = best
        return best

    return dist


def run(raw: Path = RAW, out: Path = OUT) -> dict:
    print("fetching official 2019 files (not the 550 MB bundle)…")
    try:
        fetch(raw)
    except Exception as exc:
        payload = {"status": "not_run", "reason": f"download failed: {exc}", "label": "official BattLeDIM 2019"}
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("DOWNLOAD_FAILED", exc)
        return payload

    leaks_path = raw / "2019_Leakages.csv"
    flows_path = raw / "2019_SCADA_Flows.csv"
    press_path = raw / "2019_SCADA_Pressures.csv"
    inp = raw / "L-TOWN.inp"
    print("reading SCADA / leakages…")
    leak_df = read_battledim_csv(leaks_path)
    flows = read_battledim_csv(flows_path)
    press = read_battledim_csv(press_path)
    events = leak_events_from_timeseries(leak_df)
    print(f"  {len(events)} published 2019 leak events, {len(flows.columns)} flow sensors, {len(press.columns)} pressure sensors")

    print("building L-Town pipe graph…")
    wn, G, incident = pipe_graph(inp)
    dist = link_distance_fn(wn, G)

    print("detecting (MNF + burst persist — not the IWS leftover hook)…")
    when = detect_mnf_and_bursts(flows)
    detections = []
    for t in when:
        link = localise_link(press, t, incident)
        detections.append(Detection(t, link))
        print(f"  detect {t} -> {link}")

    print("scoring (official Table 3)…")
    card = official_score(events, detections, dist)
    payload = {
        "status": "ran",
        "year": 2019,
        "observation": "official SCADA flows + pressures",
        "detector": "daily MNF residual + 6 h inflow persist; localise = loudest pressure drop incident pipe",
        "xmax_m": XMAX_M,
        "cw_eur_per_m3": CW_EUR_PER_M3,
        "cr_eur": CR_EUR,
        "perfect_eur": PERFECT_SCORE_EUR,
        "n_leaks": card.n_leaks,
        "n_detections": card.n_detections,
        "true_positives": card.true_positives,
        "false_positives": card.false_positives,
        "repeats_ignored": card.repeats_ignored,
        "true_positive_rate": card.true_positive_rate,
        "economic_eur": card.economic_eur,
        "water_saved_m3": card.water_saved_m3,
        "crew_cost_eur": card.crew_cost_eur,
        "winner_tpr_range": [0.5652, 0.6522],
        "winner_economic_eur_range": [260562, 264873],
        "label": card.label,
        "note": (
            "Negative control. L-Town is continuously supplied. Do not blend "
            "with the IWS leftover-flow library. Winners used hybrid EPANET "
            "search; we used night-flow + pressure drop."
        ),
        "rows": card.rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, indent=2))
    print(f"wrote {out}")
    return payload


def main() -> None:
    p = argparse.ArgumentParser(description="Official BattLeDIM 2019 score (negative control)")
    p.add_argument("--raw", type=Path, default=RAW)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    run(args.raw, args.out)


if __name__ == "__main__":
    main()
