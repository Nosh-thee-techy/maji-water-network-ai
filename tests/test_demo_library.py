"""Demo pack is what the dashboard opens when the 300-row library is absent."""

from __future__ import annotations

from pathlib import Path

from sim.demo_library import DEFAULT_OUT


def test_checked_in_demo_index_has_four_windows():
    index = DEFAULT_OUT / "index.json"
    assert index.exists(), "run python -m sim.demo_library"
    import json

    payload = json.loads(index.read_text(encoding="utf-8"))
    ids = {r["scenario_id"] for r in payload["scenarios"]}
    assert {"demo-clean", "demo-leak", "demo-longfill", "demo-valve"} <= ids
    for sid in ids:
        assert (DEFAULT_OUT / f"{sid}.json").exists()
        assert (DEFAULT_OUT / f"{sid}.npz").exists()
