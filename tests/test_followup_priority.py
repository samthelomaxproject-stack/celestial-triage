from celestial_triage.scoring.followup import build_followup_priority


def test_followup_priority_assigns_high_for_strong_iso_signals():
    features = {
        "motion_rate_deg_per_hour": 1.3,
        "detection_span_hours": 40,
        "poor_catalog_fraction": 0.7,
        "hyperbolic_likelihood": 0.75,
    }
    score_map = {"iso_detector": 0.86, "neo_detector": 0.45, "kbo_detector": 0.32}
    out = build_followup_priority(features, score_map, "new")
    assert out["priority"] in {"high", "urgent"}
    assert out["priority_score"] >= 0.65
    assert len(out["reasons"]) > 0
