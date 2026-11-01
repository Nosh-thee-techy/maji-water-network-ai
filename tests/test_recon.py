from pathlib import Path

from model.recon import load_model, reconstruct_window


def test_recon_without_model_is_unavailable():
    out = reconstruct_window("demo-leak", Path("results/demo"), ["J07"], None)
    assert out["available"] is False
    assert out["snapshots"] == []


def test_trained_twin_reconstructs_demo_leak():
    model = load_model("cpu")
    assert model is not None, "run python -m model.recon first"
    out = reconstruct_window("demo-leak", Path("results/demo"), ["J01", "J07", "J12"], model)
    assert out["available"] is True
    assert out["leak_head_unused"] is True
    assert out["mae_m"] >= 0
    assert {s["window"] for s in out["snapshots"]} <= {"fill", "after"}
    assert "J07" in out["snapshots"][0]["p_hat_m"]
