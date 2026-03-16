from celestial_triage.scoring.interpretation import build_interpretation_summary


def test_interpretation_summary_primary_and_competing():
    features = {
        "detection_count": 5,
        "orbit_fit_quality": 0.7,
        "poor_catalog_fraction": 0.3,
    }
    score_map = {
        "iso_detector": 0.82,
        "neo_detector": 0.76,
        "kbo_detector": 0.42,
    }
    s = build_interpretation_summary(features, score_map)
    assert s["primary_detector"] == "iso_detector"
    assert "neo-like" in s["competing_interpretations"]
    assert s["confidence"] in {"weak", "moderate", "strong"}
    assert s["conflict_severity"] in {"low", "medium", "high"}
