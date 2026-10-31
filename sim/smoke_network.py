"""Build the DMA, apply rationing, print a one-screen summary.

Run from the repo root:

    python -m sim.smoke_network
"""

from __future__ import annotations

from sim.network import assert_topology, build_dma, summarise
from sim.schedule import apply_rationing_schedule, expand_windows


def main() -> None:
    wn = build_dma()
    assert_topology(wn)
    windows = apply_rationing_schedule(wn)
    info = summarise(wn)
    print("M.A.J.I schematic DMA")
    print(f"  junctions          : {info['junctions']}")
    print(f"  pipes              : {info['pipes']}")
    print(f"  reservoirs         : {info['reservoirs']}")
    print(f"  inlet pipe         : {info['inlet_pipe']}")
    print(f"  loop excess pipes  : {info['loop_excess_pipes']}")
    print(f"  customer nodes     : {len(info['customer_junctions'])}")
    print(f"  demand model       : {wn.options.hydraulic.demand_model}")
    print(f"  duration (s)       : {wn.options.time.duration}")
    print(f"  report step (s)    : {wn.options.time.report_timestep}")
    print(f"  inlet initial      : {wn.get_link(info['inlet_pipe']).initial_status}")
    print(f"  controls           : {len(wn.control_name_list)}")
    print("  supply windows (s) :")
    for open_s, close_s in windows:
        print(f"    open {open_s:6d}  close {close_s:6d}")
    print("  clock windows     :")
    for open_s, close_s in expand_windows():
        print(f"    {open_s/3600:5.1f}h – {close_s/3600:5.1f}h")


if __name__ == "__main__":
    main()
