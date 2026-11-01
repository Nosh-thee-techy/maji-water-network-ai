from baseline.explain import explain_window


def test_leak_brief_mentions_leftover_and_dig():
    brief = explain_window(
        event="leak",
        leftover_lps=1.41,
        leftover_m3_per_day=40.6,
        t_sat_s=[6.25 * 3600],
        used_change_point=True,
        ranked=[("J07", 1.4)],
    )
    assert "1.41" in brief["headline"]
    assert "J07" in brief["action"]
    assert "neural net" in brief["model_note"]
    assert len(brief["beats"]) == 3


def test_valve_brief_is_not_a_dig():
    brief = explain_window(
        event="valve_did_not_open",
        leftover_lps=0.0,
        leftover_m3_per_day=0.0,
        t_sat_s=[],
        used_change_point=False,
        ranked=[],
    )
    assert "leak crew" in brief["action"].lower() or "valve" in brief["headline"].lower()


def test_hour_explain_separates_fill_from_leftover():
    from baseline.explain import explain_at_hour

    fill = explain_at_hour(hour=5.5, q_lps=5.4, t_sat_h=[6.25], leftover_lps=1.4, event="leak")
    after = explain_at_hour(hour=7.0, q_lps=1.4, t_sat_h=[6.25], leftover_lps=1.4, event="leak")
    off = explain_at_hour(hour=12.0, q_lps=0.0, t_sat_h=[6.25], leftover_lps=1.4, event="leak")
    assert fill["phase"] == "fill"
    assert after["phase"] == "leftover"
    assert off["phase"] == "off"
